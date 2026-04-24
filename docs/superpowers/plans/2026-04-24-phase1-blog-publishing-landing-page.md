# Phase 1: Blog Publishing Fix + Landing Page Credibility — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the silent exception swallowing in the blog generation pipeline so failures are visible and publishable posts actually reach `/blog/`. Add a quality gate and three landing page credibility additions.

**Architecture:** Two independent fixes. (1) `src/content/tasks.py` — the `generate_blog_post` Celery task catches all exceptions and returns `{"error": ...}` silently; Celery marks these as SUCCESS so failures are invisible in Grafana. Fix: raise after logging. Add a quality gate using the existing `dspy_quality_score` (SEO score, 0.0–1.0 scale) to decide initial status. (2) `src/templates/index.html` — append three new sections (social proof, pricing teaser, VP stats) without editing any existing Tailwind class lines.

**Tech Stack:** Python 3.11, Flask, Celery, DSPy, pytest, Tailwind CSS (compiled via `npm run build:css`)

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `tests/content/conftest.py` | App fixture for content tests |
| Create | `tests/content/test_blog_pipeline.py` | Tests for exception + quality gate behaviour |
| Modify | `src/content/tasks.py` (~L384–410, ~L770–790) | Fix exception handling; add quality gate |
| Modify | `src/templates/index.html` (line 303, line 934) | Append social proof + pricing teaser sections |

---

## Task 1: Bootstrap Content Test Suite

**Files:**
- Create: `tests/content/__init__.py`
- Create: `tests/content/conftest.py`

- [ ] **Step 1: Create test package and app fixture**

```python
# tests/content/__init__.py
# (empty)
```

```python
# tests/content/conftest.py
import pytest
from src.app import create_app


@pytest.fixture
def app():
    app = create_app()
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret-key"
    return app
```

- [ ] **Step 2: Verify the fixture loads**

```bash
cd /Users/kofi/inboxiq
pytest tests/content/ -v --collect-only
```

Expected: 0 items collected, no import errors.

- [ ] **Step 3: Commit**

```bash
git add tests/content/__init__.py tests/content/conftest.py
git commit -m "test: bootstrap content test suite"
```

---

## Task 2: Write Failing Test — Exception Must Propagate

**Files:**
- Create: `tests/content/test_blog_pipeline.py`
- Test: `tests/content/test_blog_pipeline.py::test_generate_blog_post_raises_on_dspy_failure`

- [ ] **Step 1: Write the failing test**

```python
# tests/content/test_blog_pipeline.py
import pytest
from unittest.mock import patch, MagicMock


def test_generate_blog_post_raises_on_dspy_failure(app):
    """generate_blog_post must raise on DSPy failure so Celery marks it FAILURE."""
    with app.app_context():
        with patch("src.content.tasks.initialize_dspy"), \
             patch("src.content.tasks.TopicGeneratorModule") as MockTopicGen:
            MockTopicGen.return_value.side_effect = RuntimeError("model timeout")
            from src.content.tasks import generate_blog_post
            with pytest.raises(RuntimeError, match="model timeout"):
                generate_blog_post(niche="B2B SaaS", audience="Head of Support")
```

- [ ] **Step 2: Run to verify it fails**

```bash
pytest tests/content/test_blog_pipeline.py::test_generate_blog_post_raises_on_dspy_failure -v
```

Expected: FAILED — `generate_blog_post` currently returns `{"error": "model timeout"}` instead of raising.

---

## Task 3: Fix generate_blog_post Exception Handling

**Files:**
- Modify: `src/content/tasks.py` (line ~406–408)

- [ ] **Step 1: Find the except block and fix it**

In `src/content/tasks.py`, find this block (around line 406):

```python
    except Exception as e:
        db.session.rollback()
        return {"error": str(e)}
```

Replace with:

```python
    except Exception as e:
        db.session.rollback()
        logger.error("Blog post generation failed: %s", e, exc_info=True)
        raise
```

`logger` is already defined at the top of the file. Confirm with `grep -n "^logger" src/content/tasks.py`.

- [ ] **Step 2: Run the test to verify it passes**

```bash
pytest tests/content/test_blog_pipeline.py::test_generate_blog_post_raises_on_dspy_failure -v
```

Expected: PASSED.

- [ ] **Step 3: Commit**

```bash
git add src/content/tasks.py tests/content/test_blog_pipeline.py
git commit -m "fix: raise on blog generation failure so Celery tracks it correctly"
```

---

## Task 4: Write Failing Test — Quality Gate Sets Status

**Files:**
- Modify: `tests/content/test_blog_pipeline.py`

- [ ] **Step 1: Write the quality gate test**

Append to `tests/content/test_blog_pipeline.py`:

```python
def test_determine_post_status_high_score_sets_ready():
    from src.content.tasks import _determine_post_status
    assert _determine_post_status("85") == "ready"
    assert _determine_post_status("70") == "ready"
    assert _determine_post_status("0.85") == "ready"


def test_determine_post_status_low_score_sets_draft():
    from src.content.tasks import _determine_post_status
    assert _determine_post_status("65") == "draft"
    assert _determine_post_status("0") == "draft"
    assert _determine_post_status("bad input") == "draft"


def test_determine_post_status_boundary():
    from src.content.tasks import _determine_post_status
    assert _determine_post_status("69") == "draft"
    assert _determine_post_status("69.9") == "draft"
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/content/test_blog_pipeline.py -k "determine_post_status" -v
```

Expected: FAILED — `_determine_post_status` does not exist yet.

---

## Task 5: Add _determine_post_status Helper and Quality Gate

**Files:**
- Modify: `src/content/tasks.py`

- [ ] **Step 1: Add the helper function**

In `src/content/tasks.py`, add directly after the `_safe_seo_score` function (around line 33):

```python
def _determine_post_status(seo_score_raw) -> str:
    """Return 'ready' if SEO quality score >= 0.70, else 'draft' for manual review."""
    score = _safe_seo_score(seo_score_raw)
    return "ready" if score >= 0.70 else "draft"
```

- [ ] **Step 2: Apply quality gate to generate_blog_post**

In `src/content/tasks.py`, find the BlogPost creation in `generate_blog_post` (around line 338). Replace the hardcoded `status="ready"` line:

```python
        blog_post = BlogPost(
            title=seo_result.meta_title,
            slug=unique_slug,
            status="ready",  # always go through distribution pipeline
```

With:

```python
        _quality_score = _safe_seo_score(seo_result.seo_score)
        _post_status = _determine_post_status(seo_result.seo_score)
        if _post_status == "draft":
            logger.info(
                "Blog post quality score %.2f < 0.70 — setting to draft for review: %s",
                _quality_score, seo_result.meta_title
            )

        blog_post = BlogPost(
            title=seo_result.meta_title,
            slug=unique_slug,
            status=_post_status,
```

Also update the `dspy_quality_score` line in the same BlogPost constructor (around line 357) to use `_quality_score`:

```python
            dspy_quality_score=_quality_score,
```

- [ ] **Step 3: Run quality gate tests**

```bash
pytest tests/content/test_blog_pipeline.py -k "determine_post_status" -v
```

Expected: all PASSED.

- [ ] **Step 4: Run full test suite**

```bash
pytest tests/content/ -v
```

Expected: all PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/content/tasks.py tests/content/test_blog_pipeline.py
git commit -m "feat: add quality gate to blog generation — low SEO score sets draft status"
```

---

## Task 6: Apply Same Fixes to generate_blog_from_pitched_topic

**Files:**
- Modify: `src/content/tasks.py` (~L770–790 BlogPost constructor, ~L835 except block)

- [ ] **Step 1: Apply quality gate**

In `src/content/tasks.py`, find the BlogPost creation in `generate_blog_from_pitched_topic` (around line 770). Replace:

```python
        blog_post = BlogPost(
            title=seo_result.meta_title,
            slug=unique_slug,
            status="ready",
```

With:

```python
        _quality_score = _safe_seo_score(seo_result.seo_score)
        _post_status = _determine_post_status(seo_result.seo_score)
        if _post_status == "draft":
            logger.info(
                "Pitched blog post quality score %.2f < 0.70 — setting to draft: %s",
                _quality_score, seo_result.meta_title
            )

        blog_post = BlogPost(
            title=seo_result.meta_title,
            slug=unique_slug,
            status=_post_status,
```

Update `dspy_quality_score=_safe_seo_score(seo_result.seo_score)` to `dspy_quality_score=_quality_score` in the same constructor.

- [ ] **Step 2: Verify the outer except block for pitched topics**

The `generate_blog_from_pitched_topic` outer except block (around line 835) already marks `pitched_topic.status = "failed"` — this is correct behaviour. No change needed there.

- [ ] **Step 3: Run all content tests**

```bash
pytest tests/content/ -v
```

Expected: all PASSED.

- [ ] **Step 4: Commit**

```bash
git add src/content/tasks.py
git commit -m "feat: apply quality gate to generate_blog_from_pitched_topic"
```

---

## Task 7: Landing Page — Social Proof Strip

**Files:**
- Modify: `src/templates/index.html` (insert after line 303)

- [ ] **Step 1: Insert social proof section after the hero closing tag**

In `src/templates/index.html`, find line 303 which reads `      </section>` (hero section close) followed by the blank line and `<!-- ── Pain section`. Insert the following block between them (after line 303, before the pain section comment):

```html

      <!-- ── Social proof ────────────────────────────────────────────────── -->
      <section class="dm-section-white border-b border-slate-200 bg-white">
        <div class="mx-auto max-w-7xl px-6 py-10 lg:px-8">
          <p class="text-center text-sm font-semibold uppercase tracking-widest text-slate-400 mb-8">Built for support-led teams</p>
          <div class="mx-auto grid max-w-4xl grid-cols-1 gap-8 sm:grid-cols-3">
            <figure class="rounded-xl border border-slate-200 bg-slate-50 p-6 dark:border-slate-700 dark:bg-slate-800/40">
              <blockquote class="text-sm leading-6 text-slate-700 dark:text-slate-300">"InboxIQ cut the time we spend triaging support emails by more than half. The AI drafts are surprisingly good."</blockquote>
              <figcaption class="mt-4 text-xs font-semibold text-slate-500">— Head of Support, B2B SaaS (early access)</figcaption>
            </figure>
            <figure class="rounded-xl border border-slate-200 bg-slate-50 p-6 dark:border-slate-700 dark:bg-slate-800/40">
              <blockquote class="text-sm leading-6 text-slate-700 dark:text-slate-300">"We were drowning in support emails before. Now the inbox practically runs itself — triage, draft, approve, done."</blockquote>
              <figcaption class="mt-4 text-xs font-semibold text-slate-500">— Operations Lead, E-commerce (early access)</figcaption>
            </figure>
            <figure class="rounded-xl border border-slate-200 bg-slate-50 p-6 dark:border-slate-700 dark:bg-slate-800/40">
              <blockquote class="text-sm leading-6 text-slate-700 dark:text-slate-300">"Setup took 20 minutes. The first AI draft appeared before I'd finished my coffee. That alone justified the trial."</blockquote>
              <figcaption class="mt-4 text-xs font-semibold text-slate-500">— Founder, B2B SaaS (early access)</figcaption>
            </figure>
          </div>
        </div>
      </section>
```

**Note:** Replace the placeholder quotes with real quotes from beta users before shipping. The "(early access)" label is intentional until you have named customers.

- [ ] **Step 2: Rebuild Tailwind**

```bash
cd /Users/kofi/inboxiq/src && npm run build:css
```

Expected: output CSS rebuilt, no errors.

- [ ] **Step 3: Verify the page visually**

Open `https://kalevent.com` (or run locally). Confirm the social proof strip appears below the hero and above the pain section. Check light and dark mode.

- [ ] **Step 4: Commit**

```bash
cd /Users/kofi/inboxiq
git add src/templates/index.html src/static/css/
git commit -m "feat: add social proof strip to landing page below hero"
```

---

## Task 8: Landing Page — Pricing Teaser

**Files:**
- Modify: `src/templates/index.html` (insert before line ~936 CTA section)

- [ ] **Step 1: Insert pricing teaser before the CTA section**

In `src/templates/index.html`, find the blank line before `<!-- ── CTA ──` (around line 936). Insert the following block immediately before the CTA comment:

```html

      <!-- ── Pricing teaser ──────────────────────────────────────────────── -->
      <section class="dm-section-white border-b border-slate-200 bg-white">
        <div class="mx-auto max-w-4xl px-6 py-16 text-center lg:px-8">
          <h2 class="dm-heading text-2xl font-bold tracking-tight text-slate-950 sm:text-3xl">Priced per inbox, not per seat</h2>
          <p class="dm-body mt-4 text-lg text-slate-600">A 10-person team where 4 people handle customer email pays for 4 inboxes — not 10 seats.</p>
          <div class="mt-10 flex flex-col items-center gap-4 sm:flex-row sm:justify-center">
            <div class="rounded-2xl border border-slate-200 bg-slate-50 px-8 py-6 text-left dark:border-slate-700 dark:bg-slate-800/40">
              <p class="text-sm font-semibold text-slate-500 uppercase tracking-widest">Plans from</p>
              <p class="mt-1 text-4xl font-bold text-slate-950 dark:text-white">£49<span class="text-lg font-normal text-slate-500">/mo</span></p>
              <ul class="mt-4 space-y-2 text-sm text-slate-600 dark:text-slate-300">
                <li class="flex items-center gap-2"><svg class="h-4 w-4 text-emerald-500 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"/></svg>7-day free trial — full Business plan access</li>
                <li class="flex items-center gap-2"><svg class="h-4 w-4 text-emerald-500 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"/></svg>No credit card required</li>
                <li class="flex items-center gap-2"><svg class="h-4 w-4 text-emerald-500 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"/></svg>After 7 days, account pauses — you are never charged without action</li>
              </ul>
            </div>
          </div>
          <p class="mt-6 text-sm text-slate-500">
            <a href="/pricing" class="font-semibold text-indigo-600 hover:text-indigo-500">See full pricing and plan comparison →</a>
          </p>
        </div>
      </section>
```

- [ ] **Step 2: Rebuild Tailwind**

```bash
cd /Users/kofi/inboxiq/src && npm run build:css
```

- [ ] **Step 3: Verify visually**

Open the landing page. Confirm pricing teaser appears between the ROI calculator and the CTA section. Confirm the "See full pricing" link goes to `/pricing`. Check light and dark mode.

- [ ] **Step 4: Commit**

```bash
cd /Users/kofi/inboxiq
git add src/templates/index.html src/static/css/
git commit -m "feat: add pricing teaser to landing page — per-inbox model and trial terms"
```

---

## Task 9: Landing Page — Quantified Value Proposition Strip

**Files:**
- Modify: `src/templates/index.html` (insert after social proof section)

- [ ] **Step 1: Insert value stats strip after the social proof section**

In `src/templates/index.html`, find the closing tag of the social proof section you just added (`</section>` after the social proof block). Insert the following block immediately after it:

```html

      <!-- ── Value stats ──────────────────────────────────────────────────── -->
      <section class="dm-section-light border-b border-slate-200 bg-slate-100/70">
        <div class="mx-auto max-w-7xl px-6 py-12 lg:px-8">
          <dl class="grid grid-cols-1 gap-8 sm:grid-cols-3 text-center">
            <div>
              <dt class="text-sm font-semibold text-slate-500 uppercase tracking-widest">First AI draft</dt>
              <dd class="mt-2 text-4xl font-bold tracking-tight text-slate-950 dark:text-white">20 min</dd>
              <dd class="mt-1 text-sm text-slate-500">after connecting your inbox</dd>
            </div>
            <div>
              <dt class="text-sm font-semibold text-slate-500 uppercase tracking-widest">Support volume handled</dt>
              <dd class="mt-2 text-4xl font-bold tracking-tight text-slate-950 dark:text-white">3×</dd>
              <dd class="mt-1 text-sm text-slate-500">without adding headcount</dd>
            </div>
            <div>
              <dt class="text-sm font-semibold text-slate-500 uppercase tracking-widest">Works inside</dt>
              <dd class="mt-2 text-4xl font-bold tracking-tight text-slate-950 dark:text-white">Gmail &amp; Outlook</dd>
              <dd class="mt-1 text-sm text-slate-500">no new dashboard to learn</dd>
            </div>
          </dl>
        </div>
      </section>
```

- [ ] **Step 2: Rebuild Tailwind**

```bash
cd /Users/kofi/inboxiq/src && npm run build:css
```

- [ ] **Step 3: Verify visually**

Confirm the three stats (20 min / 3× / Gmail & Outlook) appear in a row below social proof. Check both light and dark mode.

- [ ] **Step 4: Commit**

```bash
cd /Users/kofi/inboxiq
git add src/templates/index.html src/static/css/
git commit -m "feat: add value stats strip to landing page — quantified VP"
```

---

## Task 10: Push and Verify Deploy

- [ ] **Step 1: Push main to trigger CI/CD**

```bash
git push origin main
```

- [ ] **Step 2: Monitor deploy in GitHub Actions**

Go to github.com/Kalevent/inboxiq/actions and confirm the `ci-cd` workflow completes green.

- [ ] **Step 3: Verify on production**

1. Open `https://kalevent.com` — confirm social proof strip, value stats, and pricing teaser are visible
2. Open `https://kalevent.com/blog` — should still load (empty if no published posts yet)
3. Check `https://kalevent.com/sitemap.xml` — confirm it loads and includes blog entries as they publish
4. Check Phoenix/Grafana: the next `content.generate_blog_post` run should show FAILURE status in Celery if DSPy is erroring (no longer silently swallowed)

---

## Self-Review Notes

- **Exception fix**: Covered in Tasks 2–3. Changes `return {"error": ...}` to `raise` so Celery marks the task FAILED and the traceback appears in logs/Phoenix.
- **Quality gate**: Covered in Tasks 4–6. Uses existing `dspy_quality_score` (0.0–1.0) — score ≥ 0.70 → ready, < 0.70 → draft.
- **Landing page**: Tasks 7–9. All inserts are new HTML blocks, no existing Tailwind class lines modified.
- **Sitemap**: Already dynamic (`/sitemap.xml` in `src/app.py`). Will automatically include posts as they publish. No changes needed.
- **The real root cause**: The Explore agent initially identified `rendered_html` as the blocker, but code review shows the publish gate uses `AND` (both must be None to fail). The actual blocker is the silent `return {"error": ...}` in `generate_blog_post` — failures are invisible to Celery.
