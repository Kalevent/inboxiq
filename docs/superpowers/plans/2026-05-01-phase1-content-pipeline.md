# Phase 1 Content Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the 5-stage DSPy blog content pipeline into `ContentWriterAgent(BaseAgent)`, add a `BlogQualityCheckSignature` gate, and fix word count targeting — replacing two verbose Celery tasks with thin agent wrappers.

**Architecture:** `ContentWriterAgent` extends `BaseAgent` but overrides `execute()` directly (sequential pipeline, not ReAct) so each stage runs in guaranteed order. The agent writes one `AgentEvent` row per run for telemetry. `BlogQualityCheckSignature` replaces the raw SEO score gate with a structured quality check (score 0–10, decision ready/draft). Celery tasks become 3-line wrappers.

**Tech Stack:** Python 3.11, Flask, SQLAlchemy, Celery, DSPy (`dspy.ChainOfThought`), `BaseAgent` (src/agents/base.py), pytest + SQLite in-memory.

**Note — Phase 1B (landing page):** Social proof, pricing teaser, and quantified VP are **already live** on index.html (lines 305–324, 985–1000, 239). No template changes needed.

---

## File Map

| File | Action |
|---|---|
| `src/dspy/signatures.py` | **Modify** — add `build_blog_quality_check` |
| `src/agents/content_writer.py` | **Create** — `ContentWriterAgent` |
| `src/content/tasks.py` | **Modify** — replace `generate_blog_post` and `generate_blog_from_pitched_topic` bodies with wrappers |
| `tests/agents/test_content_writer.py` | **Create** — agent unit tests |

---

### Task 1: Add `build_blog_quality_check` to `src/dspy/signatures.py`

**Files:**
- Modify: `src/dspy/signatures.py` (append after `build_blog_expander`, currently ends ~line 530)

- [ ] **Step 1.1: Write the failing test**

```python
# tests/agents/test_content_writer.py
import pytest
from unittest.mock import MagicMock, patch


def test_build_blog_quality_check_returns_ready_for_high_score(app):
    """build_blog_quality_check module returns 'ready' when quality_score >= 7."""
    from src.dspy.signatures import build_blog_quality_check

    mock_dspy = MagicMock()
    mock_result = MagicMock()
    mock_result.quality_score = "8"
    mock_result.publish_decision = "ready"
    mock_result.reason = "Well-structured post."

    mock_module = MagicMock(return_value=mock_result)
    mock_dspy.ChainOfThought.return_value = mock_module

    checker = build_blog_quality_check(mock_dspy)
    result = checker(title="Test", content="body text", target_audience="Head of Support")

    assert result.publish_decision == "ready"
    assert result.quality_score == "8"
```

- [ ] **Step 1.2: Run test to verify it fails**

```bash
cd /Users/kofi/inboxiq && python -m pytest tests/agents/test_content_writer.py::test_build_blog_quality_check_returns_ready_for_high_score -v
```

Expected: `ImportError` or `AttributeError` — `build_blog_quality_check` does not exist yet.

- [ ] **Step 1.3: Add `build_blog_quality_check` to `src/dspy/signatures.py`**

Append this function at the end of the file (after `build_blog_expander`):

```python
def build_blog_quality_check(dspy: Any) -> Any:
    """DSPy module that scores a blog post and decides ready vs draft."""

    class BlogQualityCheckSignature(dspy.Signature):
        """
        Evaluate a blog post draft for publishing quality.
        Score 0–10 across relevance, depth, clarity, and audience fit.
        Decide 'ready' when score >= 7, 'draft' when score < 7.
        """
        title = dspy.InputField(desc="Blog post title.")
        content = dspy.InputField(desc="First 3,000 characters of the blog post in Markdown.")
        target_audience = dspy.InputField(desc="Intended reader — e.g. 'Head of Support, B2B SaaS'.")
        quality_score = dspy.OutputField(desc="Quality score as an integer 0–10.")
        publish_decision = dspy.OutputField(desc="'ready' if score >= 7, else 'draft'.")
        reason = dspy.OutputField(desc="One sentence explaining the decision.")

    class BlogQualityCheckModule(dspy.Module):
        def __init__(self) -> None:
            super().__init__()
            self.check = dspy.ChainOfThought(BlogQualityCheckSignature)

        def forward(self, title: str, content: str, target_audience: str) -> Any:
            return self.check(title=title, content=content, target_audience=target_audience)

    return BlogQualityCheckModule()
```

- [ ] **Step 1.4: Run test to verify it passes**

```bash
python -m pytest tests/agents/test_content_writer.py::test_build_blog_quality_check_returns_ready_for_high_score -v
```

Expected: PASS

- [ ] **Step 1.5: Commit**

```bash
git add src/dspy/signatures.py tests/agents/test_content_writer.py
git commit -m "feat(content): add BlogQualityCheck DSPy signature"
```

---

### Task 2: Create `ContentWriterAgent`

**Files:**
- Create: `src/agents/content_writer.py`
- Modify: `tests/agents/test_content_writer.py`

- [ ] **Step 2.1: Write the failing tests**

Add these to `tests/agents/test_content_writer.py`:

```python
import json
from unittest.mock import MagicMock, patch


def test_content_writer_agent_execute_stores_agent_event(app):
    """execute() writes an AgentEvent row on success."""
    from src.agents.content_writer import ContentWriterAgent

    fake_result = {
        "success": True,
        "blog_post_id": "abc-123",
        "title": "Test Post",
        "slug": "test-post",
        "word_count": 1500,
        "status": "ready",
        "quality_score": "8",
    }
    with patch.object(ContentWriterAgent, "_run_auto", return_value=fake_result), \
         patch.object(ContentWriterAgent, "_store_event") as mock_store:
        agent = ContentWriterAgent(account_id=1)
        goal = json.dumps({"mode": "auto", "niche": "B2B SaaS", "audience": "Head of Support"})
        result = agent.execute(goal)

    assert result["status"] == "ready"
    mock_store.assert_called_once()
    args = mock_store.call_args[0]
    assert args[0] is True   # success=True


def test_content_writer_agent_execute_stores_event_on_failure(app):
    """execute() writes a failed AgentEvent row when _run_auto raises."""
    from src.agents.content_writer import ContentWriterAgent

    with patch.object(ContentWriterAgent, "_run_auto", side_effect=RuntimeError("boom")), \
         patch.object(ContentWriterAgent, "_store_event") as mock_store:
        agent = ContentWriterAgent(account_id=1)
        goal = json.dumps({"mode": "auto", "niche": "B2B SaaS", "audience": "Head of Support"})
        with pytest.raises(RuntimeError):
            agent.execute(goal)

    mock_store.assert_called_once()
    args = mock_store.call_args[0]
    assert args[0] is False   # success=False
    assert "boom" in (args[2] or "")  # error_msg


def test_content_writer_agent_dispatches_pitched_mode(app):
    """execute() with mode=pitched calls _run_pitched, not _run_auto."""
    from src.agents.content_writer import ContentWriterAgent

    fake_result = {"success": True, "blog_post_id": "xyz", "title": "Pitched", "slug": "pitched", "word_count": 1300, "status": "ready", "quality_score": "7"}
    with patch.object(ContentWriterAgent, "_run_pitched", return_value=fake_result) as mock_pitched, \
         patch.object(ContentWriterAgent, "_store_event"):
        agent = ContentWriterAgent(account_id=1)
        goal = json.dumps({"mode": "pitched", "topic_id": "topic-uuid"})
        agent.execute(goal)

    mock_pitched.assert_called_once_with("topic-uuid")
```

- [ ] **Step 2.2: Run tests to verify they fail**

```bash
python -m pytest tests/agents/test_content_writer.py -v -k "content_writer_agent"
```

Expected: `ImportError` — `ContentWriterAgent` does not exist yet.

- [ ] **Step 2.3: Create `src/agents/content_writer.py`**

```python
"""Content writing agent — sequential 5-stage DSPy blog pipeline."""
from __future__ import annotations

import json
import logging
import math
import os
import re
import time
from datetime import datetime
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

    # ------------------------------------------------------------------ #
    # DSPy initialisation — content pipeline needs max_tokens=3000        #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _init_dspy() -> None:
        provider = os.getenv("DSPY_PROVIDER", "openai").strip().lower()
        model = os.getenv("DSPY_MODEL", "gpt-4o-mini")
        if "/" not in model:
            model = f"{provider}/{model}"
        lm = dspy.LM(model=model, max_tokens=3000, temperature=0.7)
        dspy.settings.configure(lm=lm)

    # ------------------------------------------------------------------ #
    # Two entry modes                                                      #
    # ------------------------------------------------------------------ #

    def _run_auto(self, niche: str, audience: str, topic_index: int, account_id) -> Dict[str, Any]:
        from src.dspy.content import TopicGeneratorModule
        self._init_dspy()
        topics_result = TopicGeneratorModule()(
            blog_niche=niche,
            target_audience=audience,
            num_topics=5,
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
        selected_topic = {
            "target_keyword": topic_obj.target_keyword or "",
            "secondary_keywords": topic_obj.secondary_keywords or [],
            "target_stage": topic_obj.funnel_stage or "discovery",
            "title": topic_obj.title or "",
        }
        audience = topic_obj.target_audience or "Head of Support, B2B SaaS"
        self.log(f"Pitched topic: {topic_obj.title}")
        self._init_dspy()
        return self._write_pipeline(selected_topic, audience)

    # ------------------------------------------------------------------ #
    # Core 5-stage pipeline                                               #
    # ------------------------------------------------------------------ #

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

        # 5. Quality gate — replaces raw SEO score check
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

        # Enforce minimum word count — expand to _TARGET_WORDS if short
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
                expand_blog_post(tmp, target_word_count=_TARGET_WORDS)
                optimized = tmp.markdown
                content_html = tmp.content_html
                word_count = len(optimized.split())
                self.log(f"Expanded to {word_count} words")
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
            rendered_html=content_html,   # explicit: ensures publish gate passes
            markdown=optimized,
            meta_description=seo_result.meta_description,
            excerpt=seo_result.meta_description,
            hero_image_url=hero_image_url,
            hero_image_alt=hero_image_alt,
            word_count=word_count,
            read_time_minutes=read_time,
            auto_generated=True,
            dspy_quality_score=quality_score,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        db.session.add(blog_post)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        self.log(f"Saved: {blog_post.id} ({post_status})")
        return {
            "success": True,
            "blog_post_id": blog_post.id,
            "title": seo_result.meta_title,
            "slug": unique_slug,
            "word_count": word_count,
            "status": post_status,
            "quality_score": str(qc.quality_score),
        }
```

- [ ] **Step 2.4: Run tests to verify they pass**

```bash
python -m pytest tests/agents/test_content_writer.py -v
```

Expected: all 4 tests pass (1 from Task 1 + 3 from Task 2).

- [ ] **Step 2.5: Commit**

```bash
git add src/agents/content_writer.py tests/agents/test_content_writer.py
git commit -m "feat(agents): add ContentWriterAgent — 5-stage DSPy pipeline with quality gate"
```

---

### Task 3: Replace `generate_blog_post` task body

**Files:**
- Modify: `src/content/tasks.py` lines 145–468

- [ ] **Step 3.1: Write the failing test**

Add to `tests/agents/test_content_writer.py`:

```python
def test_generate_blog_post_task_delegates_to_agent(app):
    """generate_blog_post Celery task is a thin wrapper around ContentWriterAgent."""
    from src.agents.content_writer import ContentWriterAgent

    fake_result = {"success": True, "blog_post_id": "x", "title": "T", "slug": "t", "word_count": 1500, "status": "ready", "quality_score": "8"}
    with patch.object(ContentWriterAgent, "execute", return_value=fake_result) as mock_exec, \
         patch.object(ContentWriterAgent, "_store_event"):
        from src.content.tasks import generate_blog_post
        result = generate_blog_post(niche="B2B SaaS", audience="Head of Support", topic_index=0)

    mock_exec.assert_called_once()
    goal = json.loads(mock_exec.call_args[0][0])
    assert goal["mode"] == "auto"
    assert goal["niche"] == "B2B SaaS"
```

- [ ] **Step 3.2: Run test to verify it fails**

```bash
python -m pytest tests/agents/test_content_writer.py::test_generate_blog_post_task_delegates_to_agent -v
```

Expected: FAIL — task currently runs the inline pipeline, not via ContentWriterAgent.

- [ ] **Step 3.3: Replace `generate_blog_post` body in `src/content/tasks.py`**

Find the function starting at line 145. Keep the `@shared_task(name="content.generate_blog_post")` decorator and the signature unchanged. Replace everything from the docstring body through the final `return` with:

```python
    from src.agents.content_writer import ContentWriterAgent
    import json as _json

    goal = _json.dumps({
        "mode": "auto",
        "niche": niche,
        "audience": audience,
        "topic_index": topic_index,
        "account_id": account_id,
    })
    return ContentWriterAgent(account_id=account_id or 1).execute(goal)
```

Keep the function signature exactly as-is:
```python
def generate_blog_post(
    niche: str = "Revenue Operations",
    audience: str = "VP Revenue Operations, B2B SaaS, 100-500 employees",
    topic_index: int = 0,
    auto_publish: bool = False,
    account_id: int = None,
):
```

- [ ] **Step 3.4: Run test to verify it passes**

```bash
python -m pytest tests/agents/test_content_writer.py::test_generate_blog_post_task_delegates_to_agent -v
```

Expected: PASS

- [ ] **Step 3.5: Run full test suite**

```bash
python -m pytest tests/ -v 2>&1 | tail -15
```

Expected: same pass count as before (45+), no new failures.

- [ ] **Step 3.6: Commit**

```bash
git add src/content/tasks.py
git commit -m "feat(content): replace generate_blog_post body with ContentWriterAgent wrapper"
```

---

### Task 4: Replace `generate_blog_from_pitched_topic` task body

**Files:**
- Modify: `src/content/tasks.py` lines 589–876

- [ ] **Step 4.1: Write the failing test**

Add to `tests/agents/test_content_writer.py`:

```python
def test_generate_blog_from_pitched_topic_delegates_to_agent(app):
    """generate_blog_from_pitched_topic is a thin wrapper around ContentWriterAgent."""
    from src.agents.content_writer import ContentWriterAgent

    fake_result = {"success": True, "blog_post_id": "y", "title": "P", "slug": "p", "word_count": 1400, "status": "draft", "quality_score": "6"}
    with patch.object(ContentWriterAgent, "execute", return_value=fake_result) as mock_exec, \
         patch.object(ContentWriterAgent, "_store_event"):
        from src.content.tasks import generate_blog_from_pitched_topic
        result = generate_blog_from_pitched_topic(topic_id="some-uuid")

    mock_exec.assert_called_once()
    goal = json.loads(mock_exec.call_args[0][0])
    assert goal["mode"] == "pitched"
    assert goal["topic_id"] == "some-uuid"
```

- [ ] **Step 4.2: Run test to verify it fails**

```bash
python -m pytest tests/agents/test_content_writer.py::test_generate_blog_from_pitched_topic_delegates_to_agent -v
```

Expected: FAIL — task currently runs inline pipeline.

- [ ] **Step 4.3: Replace `generate_blog_from_pitched_topic` body in `src/content/tasks.py`**

Find the function starting at line 589. Keep its `@shared_task(name="content.generate_blog_from_pitched_topic")` decorator and signature unchanged. Replace the entire body with:

```python
    from src.agents.content_writer import ContentWriterAgent
    import json as _json

    goal = _json.dumps({"mode": "pitched", "topic_id": topic_id})
    return ContentWriterAgent(account_id=1).execute(goal)
```

The signature to keep:
```python
def generate_blog_from_pitched_topic(topic_id: str):
```

- [ ] **Step 4.4: Verify `generate_blog_post` feature gate is preserved**

The `account_id` quota gate from `generate_blog_post` is now inside `ContentWriterAgent` — but wait: the quota gate (`check_and_increment("content_posts", account_id)`) was in the old task body and is NOT in `ContentWriterAgent._run_auto`. Add it back to the `generate_blog_post` task wrapper so it runs before the agent:

```python
@shared_task(name="content.generate_blog_post")
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

    from src.agents.content_writer import ContentWriterAgent
    import json as _json

    goal = _json.dumps({
        "mode": "auto",
        "niche": niche,
        "audience": audience,
        "topic_index": topic_index,
        "account_id": account_id,
    })
    return ContentWriterAgent(account_id=account_id or 1).execute(goal)
```

- [ ] **Step 4.5: Remove now-unused imports from `src/content/tasks.py`**

After the replacements, the following top-of-file imports are no longer used in either task function. Remove them:

```python
# Remove these lines from the top-level import block if no other function uses them:
from src.dspy.content import (
    TopicGeneratorModule,
    OutlineCreatorModule,
    ContentWriterModule,
    EditorModule,
    SEOOptimizerModule
)
```

Check first: `grep -n "TopicGeneratorModule\|OutlineCreatorModule\|ContentWriterModule\|EditorModule\|SEOOptimizerModule" src/content/tasks.py`

If the count after Task 3 and 4 is zero, remove the import block. If any function still uses them (e.g. `optimize_existing_post`), leave the imports in place.

- [ ] **Step 4.6: Run full test suite**

```bash
python -m pytest tests/ -v 2>&1 | tail -15
```

Expected: all tests passing (same count as before). Count the content writer tests: should be 6 total.

- [ ] **Step 4.7: Commit**

```bash
git add src/content/tasks.py tests/agents/test_content_writer.py
git commit -m "feat(content): replace generate_blog_from_pitched_topic with ContentWriterAgent wrapper"
```

---

### Task 5: Deploy

- [ ] **Step 5.1: Push to dev**

```bash
git push origin dev
```

- [ ] **Step 5.2: Merge dev → main and confirm CI passes**

Watch `.github/workflows/inbox-ci.yml`. All steps must be green.

- [ ] **Step 5.3: Smoke test on the live cluster**

After deployment, trigger one generation to verify end-to-end:

```bash
kubectl exec -n kaley deploy/inboxiq -- celery -A src.celery_inboxiq:celery call content.generate_blog_from_pitched_topic --args='["<a-real-pitched-topic-id>"]'
```

Check the result: the returned JSON should include `word_count >= 1200`, `status` = `"ready"` or `"draft"`, and no error key.

---

## Self-Review

**Spec coverage:**

| Spec requirement | Task |
|---|---|
| `ContentWriterAgent(BaseAgent)` extraction | Task 2 |
| Move 5-stage DSPy chain into agent | Task 2 (`_write_pipeline`) |
| Celery tasks become thin wrappers | Tasks 3, 4 |
| Fix `rendered_html` gate — set `rendered_html = content_html` | Task 2 (`_write_pipeline`, line `rendered_html=content_html`) |
| Fix word count target — expand to 1500 not 1200 | Task 2 (`_TARGET_WORDS = 1500`, `expand_blog_post(tmp, target_word_count=_TARGET_WORDS)`) |
| `BlogQualityCheck` DSPy signature (score ≥ 7 → ready) | Task 1 |
| Quality gate replaces raw SEO score check | Task 2 (`qc = build_blog_quality_check(dspy)(...)`) |
| Account quota gate preserved | Task 4, Step 4.4 |
| Phase 1B landing page | Already live — no tasks needed |

**Placeholder scan:** None found — all steps contain complete code.

**Type consistency:**
- `ContentWriterAgent.execute(goal: str)` matches `BaseAgent.execute(goal: str)` — correct override with `# type: ignore[override]` not needed since signature matches.
- `expand_blog_post(tmp, target_word_count=_TARGET_WORDS)` — `_TmpPost` has `.markdown`, `.word_count`, `.content_html`, `.rendered_html`, `.excerpt`, `.primary_keyword`, `.slug` — all fields accessed by `expand_blog_post` in `src/publishing/service.py:200–228`.
- `build_blog_quality_check(dspy)` returns a `BlogQualityCheckModule` instance — called with keyword args `title`, `content`, `target_audience` — matches `BlogQualityCheckSignature` InputField names.
