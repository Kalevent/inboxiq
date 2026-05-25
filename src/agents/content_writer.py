"""Content writing agent — sequential 5-stage DSPy blog pipeline."""
from __future__ import annotations

import json
import logging
import math
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

import dspy
import markdown

from src.agents.base import BaseAgent
from src.extensions import db
from src.sanitize import sanitize_html

log = logging.getLogger(__name__)

_MIN_WORDS = 1200
_TARGET_WORDS = 1500


class ContentWriterAgent(BaseAgent):
    """
    Runs the 5-stage DSPy blog content pipeline sequentially.
    Overrides execute() — does NOT use dspy.ReAct.

    Goal JSON shapes:
      {"mode": "auto",    "niche": str, "audience": str, "topic_index": int, "account_id": int|None}
      {"mode": "pitched", "topic_id": str}
    """

    agent_name = "content_writer"
    mcp_server_labels: List[str] = []

    def execute(self, goal: str) -> Dict[str, Any]:  # type: ignore[override]
        self.goal = goal
        self.execution_log = []
        start = time.time()
        success = False
        result_text = ""
        error_msg = None
        try:
            params = json.loads(goal)
            mode = params.get("mode", "auto")
            if mode == "pitched":
                result = self._run_pitched(params["topic_id"])
            else:
                result = self._run_auto(
                    niche=params.get("niche", "B2B SaaS"),
                    audience=params.get("audience", "Head of Support, B2B SaaS"),
                    topic_index=int(params.get("topic_index", 0)),
                    account_id=params.get("account_id"),
                )
            success = True
            result_text = (
                f"Generated: {result.get('title', '')} "
                f"({result.get('word_count', 0)} words, status={result.get('status', '')})"
            )
            return result
        except Exception as exc:
            error_msg = str(exc)
            log.exception("ContentWriterAgent failed")
            raise
        finally:
            latency_ms = int((time.time() - start) * 1000)
            self._store_event(success, result_text, error_msg, latency_ms)

    def _get_tools(self) -> List:
        return []  # sequential pipeline — ReAct not used

    @staticmethod
    def _init_dspy() -> None:
        from src.dspy.config import _configure_dspy
        _configure_dspy(max_tokens=3000, temperature=0.7)

    def _run_auto(self, niche: str, audience: str, topic_index: int, account_id) -> Dict[str, Any]:
        from src.dspy.content import TopicGeneratorModule
        self._init_dspy()
        from src.models.content import BlogPost
        existing_slugs = [
            r[0] for r in db.session.query(BlogPost.slug).filter_by(status="published").all()
        ]
        topics_result = TopicGeneratorModule()(
            blog_niche=niche,
            target_audience=audience,
            num_topics=5,
            existing_topics=json.dumps(existing_slugs),
        )
        topics = json.loads(topics_result.topics)
        if topic_index >= len(topics):
            topic_index = 0
        selected_topic = topics[topic_index]
        self.log(f"Topic selected: {selected_topic.get('target_keyword', '')}")
        return self._write_pipeline(selected_topic, audience)

    def _run_pitched(self, topic_id: str) -> Dict[str, Any]:
        from src.models.content import PitchedBlogTopic
        topic_obj = db.session.get(PitchedBlogTopic, topic_id)
        if not topic_obj:
            raise LookupError(f"PitchedBlogTopic {topic_id} not found")

        topic_obj.status = "generating"
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        selected_topic = {
            "target_keyword": topic_obj.target_keyword or "",
            "secondary_keywords": topic_obj.secondary_keywords or [],
            "target_stage": topic_obj.funnel_stage or "discovery",
            "title": topic_obj.title or "",
        }
        audience = topic_obj.target_audience or "Head of Support, B2B SaaS"
        self.log(f"Pitched topic: {topic_obj.title}")
        self._init_dspy()

        try:
            result = self._write_pipeline(selected_topic, audience)
        except Exception as exc:
            topic_obj.status = "failed"
            topic_obj.pitch_notes = (
                f"{(topic_obj.pitch_notes or '').strip()}\n\nGeneration failed: {exc}"
            ).strip()
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
            raise

        # Mark as generated regardless — generated_content_id is not set here
        # because the pipeline produces a BlogPost (blog_posts table), not a
        # GeneratedContent (generated_content table), and the FK would violate.
        topic_obj.status = "generated"
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        return result

    def _write_pipeline(self, selected_topic: dict, audience: str) -> Dict[str, Any]:
        from src.dspy.content import (
            OutlineCreatorModule,
            ContentWriterModule,
            EditorModule,
            SEOOptimizerModule,
        )
        from src.dspy.signatures import build_blog_quality_check
        from src.models.content import BlogPost
        from src.publishing.service import expand_blog_post

        # 1. Outline
        outline_result = OutlineCreatorModule()(
            topic=json.dumps(selected_topic),
            target_word_count=_TARGET_WORDS,
            content_depth="intermediate",
        )
        self.log("Outline created")

        # 2. Write
        write_result = ContentWriterModule()(
            outline=outline_result.outline,
            tone="professional",
            include_examples=True,
            include_stats=True,
        )
        self.log(f"Draft: ~{len(write_result.blog_post_draft.split())} words")

        # 3. Edit
        edit_result = EditorModule()(
            draft=write_result.blog_post_draft,
            editing_focus="all",
        )

        # 4. SEO optimize
        target_keywords = json.dumps([{
            "keyword": selected_topic["target_keyword"],
            "volume": selected_topic.get("estimated_monthly_searches", 1000),
            "difficulty": selected_topic.get("estimated_difficulty", 50),
            "priority": 1,
        }])
        seo_result = SEOOptimizerModule()(
            edited_post=edit_result.edited_post,
            target_keywords=target_keywords,
        )
        self.log("SEO pass complete")

        # Strip DSPy meta artifacts and convert to HTML
        optimized = re.sub(
            r"^Meta Description:.*\n*",
            "",
            seo_result.optimized_post.strip(),
            flags=re.IGNORECASE | re.MULTILINE,
        )
        word_count = len(optimized.split())
        md_converter = markdown.Markdown(extensions=["extra", "codehilite", "toc"])
        content_html = sanitize_html(md_converter.convert(optimized))

        # 5. Quality gate
        qc = build_blog_quality_check(dspy)(
            title=seo_result.meta_title,
            content=optimized[:3000],
            target_audience=audience,
        )
        raw_score = str(qc.quality_score).strip().split("/")[0]
        try:
            quality_score = float(raw_score) / 10
        except ValueError:
            quality_score = 0.0
        post_status = "ready" if str(qc.publish_decision).strip().lower() == "ready" else "draft"
        self.log(f"Quality score: {qc.quality_score} → {post_status}")

        # Expand if under minimum word count
        if word_count < _MIN_WORDS:
            self.log(f"Word count {word_count} < {_MIN_WORDS}, expanding to {_TARGET_WORDS}…")

            class _TmpPost:
                pass

            tmp = _TmpPost()
            tmp.markdown = optimized
            tmp.word_count = word_count
            tmp.content_html = content_html
            tmp.rendered_html = None
            tmp.excerpt = seo_result.meta_description
            tmp.primary_keyword = selected_topic.get("target_keyword", "")
            tmp.slug = seo_result.slug
            try:
                expanded = expand_blog_post(tmp, target_word_count=_TARGET_WORDS)
                if expanded:
                    optimized = tmp.markdown
                    content_html = tmp.content_html
                    word_count = len(optimized.split())
                    self.log(f"Expanded to {word_count} words")
                else:
                    self.log("Expansion returned False — proceeding with original length")
            except Exception as exp_err:
                log.warning("Expansion failed: %s", exp_err)

        read_time = math.ceil(word_count / 200) or 1

        # Hero image
        hero_image_url = None
        hero_image_alt = None
        try:
            from src.content.tasks import _generate_hero_image
            hero_image_url, hero_image_alt = _generate_hero_image(
                title=seo_result.meta_title, topic=selected_topic
            )
            self.log("Hero image uploaded")
        except Exception as img_err:
            log.warning("Hero image generation failed: %s", img_err)

        # Duplicate check
        base_slug = seo_result.slug
        existing = db.session.query(BlogPost).filter(
            BlogPost.slug == base_slug,
            BlogPost.status.in_(["published", "ready"]),
        ).first()
        if existing:
            return {"status": "skipped", "reason": "duplicate", "existing_slug": existing.slug}

        unique_slug = base_slug
        suffix = 1
        while db.session.query(BlogPost).filter(BlogPost.slug == unique_slug).first():
            if suffix > 50:
                raise RuntimeError(f"Cannot find unique slug for base: {base_slug}")
            unique_slug = f"{base_slug}-{suffix}"
            suffix += 1

        # Persist
        blog_post = BlogPost(
            title=seo_result.meta_title,
            slug=unique_slug,
            status=post_status,
            funnel_stage=selected_topic.get("target_stage", "discovery"),
            primary_keyword=selected_topic["target_keyword"],
            secondary_keywords=selected_topic.get("secondary_keywords", []),
            content_html=content_html,
            rendered_html=content_html,
            markdown=optimized,
            meta_description=seo_result.meta_description,
            excerpt=seo_result.meta_description,
            hero_image_url=hero_image_url,
            hero_image_alt=hero_image_alt,
            word_count=word_count,
            read_time_minutes=read_time,
            auto_generated=True,
            dspy_quality_score=quality_score,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.session.add(blog_post)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        self.log(f"Saved: {blog_post.id} ({post_status})")

        if post_status == "ready":
            from src.marketing.content_distribution import publish_blog_post
            publish_blog_post.delay(blog_post.id)
            self.log(f"publish_blog_post queued for {blog_post.id}")

        return {
            "success": True,
            "blog_post_id": blog_post.id,
            "title": seo_result.meta_title,
            "slug": unique_slug,
            "word_count": word_count,
            "status": post_status,
            "quality_score": str(qc.quality_score),
        }
