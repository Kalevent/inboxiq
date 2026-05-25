"""
Celery tasks for Content Generation Agent

Automated tasks for:
- Weekly blog post generation
- On-demand content creation
- SEO optimization
- Publishing automation
"""
import logging
import os
import json
from datetime import datetime
from celery import shared_task
import markdown

from src.extensions import db
from src.models.content import BlogPost, GeneratedContent

logger = logging.getLogger(__name__)


def _safe_seo_score(raw) -> float:
    """Parse DSPy seo_score which may arrive as '85', '85%', '85/100', or '85% / 100'."""
    import re
    try:
        s = str(raw).strip()
        # Extract first numeric token
        m = re.search(r'[\d.]+', s)
        if not m:
            return 0.0
        val = float(m.group())
        # If it looks like a 0–1 float already, keep it; otherwise divide by 100
        return val / 100.0 if val > 1 else val
    except Exception:
        return 0.0


def _determine_post_status(seo_score_raw) -> str:
    """Return 'ready' if SEO quality score >= 0.70, else 'draft' for manual review."""
    score = _safe_seo_score(seo_score_raw)
    return "ready" if score >= 0.70 else "draft"


# Import DSPy modules
try:
    import dspy
    from src.dspy.content import (
        SEOOptimizerModule,
    )
    from src.dspy.content.faq_generator import BlogFAQGeneratorModule
    from src.dspy import _configure_dspy
    DSPY_AVAILABLE = True
except ImportError:
    DSPY_AVAILABLE = False
    BlogFAQGeneratorModule = None  # type: ignore[assignment,misc]
    _configure_dspy = None  # type: ignore[assignment]


def initialize_dspy():
    """Initialize DSPy with LLM configuration for content generation."""
    if not DSPY_AVAILABLE:
        raise RuntimeError("DSPy not available")

    # Configure DSPy with content-generation-specific settings
    # (higher max_tokens than the centralized config which is for triage)
    provider = os.getenv("DSPY_PROVIDER", "openai").strip().lower()
    model = os.getenv("DSPY_MODEL", "gpt-4o-mini")

    # Use DSPy 3.x LM API with content-appropriate settings
    if "/" not in model:
        model = f"{provider}/{model}"

    lm = dspy.LM(model=model, max_tokens=3000, temperature=0.7)
    dspy.settings.configure(lm=lm)


def _generate_hero_image(title: str, topic: dict) -> tuple[str, str]:
    """
    Generate hero image using DALL-E 3 and upload to S3.

    Args:
        title: Blog post title
        topic: Topic object with keywords and context

    Returns:
        Tuple of (image_url, alt_text)
    """
    import openai
    import requests
    from src.uploads import upload_bytes, build_public_url
    from src.dspy import _configure_dspy
    from src.dspy.content.hero_prompt import HeroImagePromptModule

    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        raise RuntimeError("OPENAI_API_KEY not configured")

    # Use DSPy to generate an optimized DALL-E prompt
    _configure_dspy()
    prompt_module = HeroImagePromptModule()
    prompt_result = prompt_module(
        post_title=title,
        primary_keyword=topic.get("target_keyword", "business automation"),
        funnel_stage=topic.get("target_stage", "awareness"),
        industry="B2B SaaS",
    )
    image_prompt = prompt_result.dalle_prompt
    alt_text = prompt_result.alt_text or f"Hero image for {title}"

    client = openai.OpenAI(api_key=openai_api_key)

    # Generate image with DALL-E 3 — 1792x1024 for proper 16:9 landscape hero
    response = client.images.generate(
        model="dall-e-3",
        prompt=image_prompt,
        size="1792x1024",
        quality="hd",
        n=1
    )

    image_url = response.data[0].url

    # Download image — validate URL before fetching (defense-in-depth against rogue API responses)
    from src.mcp.enrichment_v2_mcp import _safe_external_url
    img_response = requests.get(_safe_external_url(image_url), timeout=30)
    img_response.raise_for_status()
    image_bytes = img_response.content

    # Upload to S3
    from datetime import datetime
    slug_safe = title.lower().replace(" ", "-")[:50]
    key = f"blog/heroes/{datetime.now().strftime('%Y%m%d')}-{slug_safe}.png"

    upload_bytes(
        key=key,
        data=image_bytes,
        content_type="image/png",
        content_disposition=f'inline; filename="{slug_safe}.png"'
    )

    public_url = build_public_url(key)
    return public_url, alt_text


@shared_task(name="content.generate_blog_post", queue="content")
def generate_blog_post(
    niche: str = "Revenue Operations",
    audience: str = "VP Revenue Operations, B2B SaaS, 100-500 employees",
    topic_index: int = 0,
    auto_publish: bool = False,
    account_id: int = None,
):
    """Generate a full blog post using the ContentWriterAgent pipeline."""
    if account_id:
        try:
            from src.features import feature_enabled
            from src.billing.quota import check_and_increment, FeatureDisabled
            if not feature_enabled("content_gen", account_id):
                return {"status": "error", "error": "Content generation is not available on your current plan."}
            check_and_increment("content_posts", account_id)
        except FeatureDisabled as _fd:
            return {"status": "error", "error": str(_fd)}
        except Exception as _qe:
            import logging as _log
            _log.getLogger(__name__).warning("Quota check failed for content_gen account=%s: %s", account_id, _qe)

    from src.agents.content_writer import ContentWriterAgent  # deferred to avoid circular import risk

    goal = json.dumps({
        "mode": "auto",
        "niche": niche,
        "audience": audience,
        "topic_index": topic_index,
        "account_id": account_id,
    })
    return ContentWriterAgent(account_id=account_id or 1).execute(goal)  # 1 = system account for scheduled runs


@shared_task(name="content.generate_weekly_posts", queue="content")
def generate_weekly_posts(num_posts: int = 3):
    """
    Scheduled task: Generate weekly blog posts.

    Runs every Monday at 6 AM.

    Args:
        num_posts: Number of posts to generate (default: 3)

    Returns:
        Dict with list of generated posts
    """
    results = {
        "timestamp": datetime.now().isoformat(),
        "num_posts_requested": num_posts,
        "posts_generated": [],
        "errors": []
    }

    for i in range(num_posts):
        try:
            result = generate_blog_post(
                topic_index=i,
                auto_publish=False  # Always require review
            )

            if "error" not in result:
                results["posts_generated"].append(result)
            else:
                results["errors"].append(result["error"])

        except Exception as e:
            results["errors"].append(f"Post {i+1}: {str(e)}")

    return results


@shared_task(name="content.optimize_existing_post", queue="content")
def optimize_existing_post(blog_post_id: str):
    """
    Re-optimize existing blog post for SEO.

    Args:
        blog_post_id: BlogPost UUID

    Returns:
        Dict with optimization results
    """
    initialize_dspy()

    blog_post = db.session.query(BlogPost).filter(BlogPost.id == blog_post_id).first()
    if not blog_post:
        return {"error": f"Blog post {blog_post_id} not found"}

    try:
        seo_module = SEOOptimizerModule()

        target_keywords = json.dumps([{
            "keyword": blog_post.primary_keyword,
            "volume": 1000,
            "difficulty": 50,
            "priority": 1
        }])

        result = seo_module(
            edited_post=blog_post.markdown or blog_post.content_html or "",
            target_keywords=target_keywords
        )

        # Update blog post
        blog_post.markdown = result.optimized_post
        blog_post.meta_description = result.meta_description
        blog_post.slug = result.slug
        blog_post.dspy_quality_score = _safe_seo_score(result.seo_score)
        blog_post.updated_at = datetime.now()

        db.session.commit()

        return {
            "success": True,
            "blog_post_id": blog_post_id,
            "seo_score": result.seo_score,
            "meta_title": result.meta_title,
            "meta_description": result.meta_description,
            "optimization_notes": result.optimization_notes
        }

    except Exception as e:
        db.session.rollback()
        return {"error": str(e)}


@shared_task(name="content.expand_short_blog_posts", queue="content")
def expand_short_blog_posts(min_word_count: int = 800):
    """
    Expand all blog posts (any status) whose word_count is below min_word_count.
    Uses DSPy to add depth to existing content without changing structure or tone.
    """
    import logging
    from src.publishing.service import expand_blog_post

    log = logging.getLogger(__name__)
    posts = BlogPost.query.filter(
        (BlogPost.word_count < min_word_count) | (BlogPost.word_count == None)
    ).all()

    results = {"expanded": [], "skipped": [], "failed": []}
    for post in posts:
        wc = post.word_count or 0
        log.info("Expanding %s (current: %d words)", post.slug, wc)
        try:
            success = expand_blog_post(post, target_word_count=min_word_count)
            if success:
                try:
                    db.session.commit()
                    results["expanded"].append({"slug": post.slug, "new_wc": post.word_count})
                    log.info("Expanded %s → %d words", post.slug, post.word_count)
                except Exception:
                    db.session.rollback()
                    results["failed"].append(post.slug)
            else:
                results["skipped"].append(post.slug)
        except Exception as exc:
            db.session.rollback()
            log.exception("Failed to expand %s: %s", post.slug, exc)
            results["failed"].append(post.slug)

    log.info("expand_short_blog_posts done: %s", results)
    return results


@shared_task(name="content.content_generation_job", queue="content")
def content_generation_job():
    """
    Main content generation orchestration job.

    Runs scheduled content generation tasks.
    """
    results = {
        "timestamp": datetime.now().isoformat(),
        "weekly_posts": None,
        "errors": []
    }

    try:
        # Generate weekly posts (only on Mondays)
        if datetime.now().weekday() == 0:  # Monday
            results["weekly_posts"] = generate_weekly_posts(num_posts=3)

        return results

    except Exception as e:
        results["errors"].append(str(e))
        return results


@shared_task(name="content.generate_blog_from_pitched_topic", queue="content")
def generate_blog_from_pitched_topic(topic_id: str):
    """Generate blog post from a manually pitched topic via ContentWriterAgent."""
    from src.agents.content_writer import ContentWriterAgent  # deferred to avoid circular import risk

    goal = json.dumps({"mode": "pitched", "topic_id": topic_id})
    return ContentWriterAgent(account_id=1).execute(goal)  # 1 = system account; pitched topics are admin-triggered


def enrich_blog_posts_for_geo() -> dict:
    """
    One-time task: append a FAQ section to published blog posts that lack one.

    Run manually:
        kubectl exec -n kaley deploy/inboxiq -- python -c "
        from src.app import create_app; app = create_app()
        with app.app_context():
            from src.content.tasks import enrich_blog_posts_for_geo
            print(enrich_blog_posts_for_geo())
        "

    Not intended for recurring scheduling.
    Returns dict with counts: enriched, skipped, errors.
    """
    from datetime import timezone
    from src.sanitize import sanitize_html

    all_posts = BlogPost.query.filter(
        BlogPost.status == "published",
        BlogPost.markdown.isnot(None),
    ).all()

    counts = {"enriched": 0, "skipped": 0, "errors": 0}

    # Filter eligible posts before initialising DSPy (avoids unnecessary LLM setup)
    # Posts already containing a FAQ section or below quality threshold are skipped
    eligible = [
        p for p in all_posts
        if "## Frequently Asked Questions" not in (p.markdown or "")
        and (p.dspy_quality_score or 0) >= 0.5
    ]
    counts["skipped"] += len(all_posts) - len(eligible)

    if not eligible:
        logger.info("enrich_blog_posts_for_geo complete: %s", counts)
        return counts

    _configure_dspy(max_tokens=1000, temperature=0.5)
    module = BlogFAQGeneratorModule()

    for post in eligible:
        try:
            prediction = module(
                post_content=post.markdown,
                post_title=post.title or "",
                primary_keyword=post.primary_keyword or "",
            )
            faq_section = prediction.faq_markdown.strip()
            if not faq_section:
                counts["skipped"] += 1
                continue

            post.markdown = post.markdown.rstrip() + "\n\n" + faq_section
            converter = markdown.Markdown(extensions=["extra", "codehilite", "toc"])
            raw_html = converter.convert(post.markdown)
            post.content_html = sanitize_html(raw_html)
            if hasattr(post, "rendered_html"):
                post.rendered_html = post.content_html
            post.updated_at = datetime.now(timezone.utc)

            try:
                db.session.commit()
                counts["enriched"] += 1
            except Exception:
                db.session.rollback()
                counts["errors"] += 1

        except Exception as exc:
            logger.warning("enrich_blog_posts_for_geo: failed for post %s: %s", post.id, exc)
            counts["errors"] += 1

    logger.info("enrich_blog_posts_for_geo complete: %s", counts)
    return counts
