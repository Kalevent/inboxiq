---
name: blog-publishing
description: Standards and workflow for InboxIQ blog post generation — enforces minimum quality gates before any post is published or auto-distributed
type: process
---

# Blog Publishing Standards

Use this skill whenever you are modifying blog generation code, DSPy content signatures, SEO quality gates, or the publishing pipeline (`src/content/tasks.py`, `src/publishing/service.py`, `src/dspy/content/`).

## Quality Gates — Non-Negotiable

| Gate | Threshold | Action on fail |
|------|-----------|----------------|
| Word count | ≥ 1,200 words | Trigger `expand_blog_post` before saving |
| SEO score | ≥ 70% | Set status `draft` for manual review |
| Title length | 40–65 characters | Log warning; still publish |
| Meta description | 120–155 characters | Log warning; still publish |

Target word count passed to the outline/writer pipeline is **1,500 words**. The 1,200 minimum is the floor after expansion.

## Expansion Logic

When a generated post is below the minimum word count:

1. Call `expand_blog_post(post, target_word_count=1200)` from `src/publishing/service.py`
2. The `_TmpPost` shim **must** include `primary_keyword` and `slug` — without them the expander silently returns `False` and leaves the post short
3. If expansion fails, log a warning but do not fail the task — save the short post as `draft` regardless of SEO score

## DSPy Scripts

All LLM calls for this skill live in `scripts/` — no raw prompts anywhere else.

| Script | Purpose | When to use |
|--------|---------|-------------|
| [scripts/evaluate.py](scripts/evaluate.py) | Quality evaluator | Run on any `draft` post before deciding to publish, expand, or rewrite |
| [scripts/brief.py](scripts/brief.py) | Content brief generator | Validate a pitched topic before sending it through the 5-stage pipeline |
| [scripts/hero_prompt.py](scripts/hero_prompt.py) | Hero image prompt generator | Produces the optimized prompt passed to the image generation API for hero images |

Run standalone from the project root: `python -m skills.blog_publishing.scripts.evaluate`

## DSPy Content Pipeline (Production)

Five-stage pipeline in `src/dspy/content/`: `TopicGenerator → OutlineCreator → ContentWriter → Editor → SEOOptimizer`

When modifying a stage signature:
- Add fields to the module file in `src/dspy/content/`
- Never remove existing output fields — downstream stages may depend on them
- All modules use `dspy.ChainOfThought`; do not switch to `dspy.Predict` without testing

The **ContentWriter** stage receives `target_word_count` via the outline. If posts are consistently short, check that `OutlineCreatorModule` is passing `target_word_count=1500` and that the LLM model (`DSPY_MODEL`) has sufficient context/output token capacity.

## SEO Score Parsing

`_safe_seo_score()` in `src/content/tasks.py` normalizes scores that arrive as `"85"`, `"85%"`, `"85/100"`, or `"85% / 100"`. Do not bypass this function — raw comparisons against DSPy output will break.

## Auto-Publish vs Draft

Posts with SEO score ≥ 70% are saved as `ready` and auto-published by the scheduler. Posts below 70% land in `draft` and appear in the Content & Publishing UI for manual review.

**Do not raise the auto-publish threshold above 80%** without also fixing DSPy training data — the current model scores most posts at 85%, so a higher threshold would block all output.

## Distributing Posts

After publishing, `Distribute` in the Content UI triggers social/newsletter distribution. Do not wire auto-distribution to the generation pipeline itself — always keep it a manual step until a content review workflow exists.

## Checklist Before Changing the Pipeline

- [ ] Both `_TmpPost` shims (auto-generate and pitched-topic paths) have `primary_keyword` and `slug`
- [ ] `_MIN_WORDS` is ≥ 1,200 in both paths
- [ ] `target_word_count` passed to `OutlineCreatorModule` is ≥ 1,500
- [ ] SEO quality gate (`_determine_post_status`) uses 0.70 as the threshold
- [ ] `expand_blog_post` return value is checked — a `False` return means expansion failed, post should be set to `draft`
- [ ] No bare `db.session.commit()` — every commit has a paired `rollback()` on exception
