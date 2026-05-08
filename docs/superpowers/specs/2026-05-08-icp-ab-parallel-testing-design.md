# ICP A/B Parallel Testing — Design Spec

**Date:** 2026-05-08
**Author:** Kofi + Claude
**Status:** Approved (ready for implementation plan)

---

## Problem

Today, each account has at most one `ICPConfig` row. Changing it overwrites the previous targeting and loses any ability to compare. The user can't run "Founder titles" against "Co-founder titles" simultaneously and see which produces leads that convert better.

Stated user goal: *"The idea of the model is to be flexible — change ICP at a moment and test if it works in production. Test one ICP against another."*

The framing is **parallel A/B**, not sequential change-and-observe.

## Goals

1. Run two ICP variants (A and B) for the same account in parallel — each with its own LinkedIn discovery filters.
2. Tag every discovered lead with the variant that produced it, so downstream conversion (connected → replied → booked) can be attributed cleanly.
3. Show live A/B metrics in Settings → LinkedIn → Experiment, with a one-click winner-declaration action.
4. Preserve back-compat: accounts with no experiment continue to use existing `ICPConfig`.

## Non-goals (v1)

- 3+-way variants. Variant label is `String(1)` enforced to "A" or "B".
- Multiple concurrent experiments per account. Server returns 409 if a second experiment is started while one is running.
- Statistical significance / Bayesian credibility intervals. Conversion is reported as a raw percentage; declaring winner is a manual user action.
- Auto-promote-winner. The system does not automatically end an experiment when one variant pulls ahead.

## Data model

Three new tables in `src/models/marketing.py`. All use the codebase convention of `String(64)` UUID primary keys (matching existing `ICPConfig`, `Lead`); FK to `accounts.id` (Integer) — no Account model changes.

```python
class ICPExperiment(db.Model):
    """One A/B test of two ICP variants. At most one running per account at a time."""
    __tablename__ = "icp_experiments"
    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()))
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    status = db.Column(db.String(30), nullable=False, server_default="running")
    # status ∈ {"running", "paused", "completed"}
    traffic_split = db.Column(db.JSON, nullable=False, default=lambda: {"A": 50, "B": 50})
    winner_variant = db.Column(db.String(1), nullable=True)  # set only when status="completed"
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ICPVariant(db.Model):
    """One arm of an experiment — A or B."""
    __tablename__ = "icp_variants"
    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()))
    experiment_id = db.Column(
        db.String(64),
        db.ForeignKey("icp_experiments.id", ondelete="CASCADE"),
        nullable=False,
    )
    label = db.Column(db.String(1), nullable=False)  # "A" | "B"
    titles = db.Column(db.JSON, nullable=False)              # list[str]
    industries = db.Column(db.JSON, nullable=False)          # list[str]
    company_size_min = db.Column(db.Integer, nullable=True)
    company_size_max = db.Column(db.Integer, nullable=True)
    geographies = db.Column(db.JSON, nullable=False)         # list[str]
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        db.UniqueConstraint("experiment_id", "label", name="uq_experiment_variant_label"),
        db.CheckConstraint("label IN ('A', 'B')", name="ck_variant_label_a_or_b"),
    )


class ICPLeadAssignment(db.Model):
    """A lead -> variant tag inside an experiment. lead_id is UNIQUE so the
    conversion math is unambiguous (no double-counting)."""
    __tablename__ = "icp_lead_assignments"
    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()))
    experiment_id = db.Column(
        db.String(64),
        db.ForeignKey("icp_experiments.id", ondelete="CASCADE"),
        nullable=False,
    )
    variant_id = db.Column(
        db.String(64),
        db.ForeignKey("icp_variants.id", ondelete="CASCADE"),
        nullable=False,
    )
    lead_id = db.Column(
        db.String(64),
        db.ForeignKey("leads.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    status = db.Column(db.String(50), nullable=False, server_default="discovered")
    # status ∈ {"discovered", "connected", "replied", "booked", "disqualified"}
    score = db.Column(db.Integer, nullable=False, server_default="0")
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

## Discovery flow

`linkedin.discover_prospects` (existing Celery task) is updated:

1. For each `account_id`:
   1. Look up the running experiment: `ICPExperiment.query.filter_by(account_id=..., status='running').first()`.
   2. **Branch A — running experiment found**:
      - Pull both variants (A, B) ordered by label.
      - Compute per-variant cycle quota from `traffic_split` and the env-configured per-cycle budget (`LEAD_DISCOVERY_MAX_LEADS`, default 50). E.g. `traffic_split={"A":60,"B":40}` × budget 50 → A_quota=30, B_quota=20.
      - For each variant in order [A, B]:
        - Query LinkedIn (existing search call site in `src/tasks/linkedin.discover_prospects` — same function that today reads `ICPConfig`) using that variant's `titles`/`industries`/`company_size`/`geographies`.
        - Skip prospects whose Lead already has an `ICPLeadAssignment` row (in any experiment, any variant).
        - Take up to `quota` new prospects, promote each to a Lead (existing logic), then write `ICPLeadAssignment(experiment_id, variant_id, lead_id, status='discovered')`.
      - Quota under-fill: if a variant's filters return fewer prospects than its quota, the cycle ends without re-allocating the remainder to the other variant. Each variant's discovery is independent — under-fill on A does not boost B. Keeps the conversion math fair (split ratios reflect actual market reach, not pool dynamics).
      - Overlap edge case: a prospect matches both A's and B's filters → A claims it (because A runs first). Acceptable v1 behaviour; documented in code.
   3. **Branch B — no running experiment**: fall back to existing `ICPConfig`-driven discovery, unchanged.

## Status progression / backfill

`ICPLeadAssignment.status` is the source of truth for the metrics panel. Updated by a new periodic task `linkedin.refresh_experiment_metrics` running every 15 min via Celery beat. Pseudocode:

```python
@shared_task(name="linkedin.refresh_experiment_metrics")
def refresh_experiment_metrics():
    for assignment in ICPLeadAssignment.query.filter(
        ICPLeadAssignment.status != "disqualified"
    ).all():
        new_status = derive_status(assignment.lead_id)
        if new_status != assignment.status:
            assignment.status = new_status
    db.session.commit()


def derive_status(lead_id: str) -> str:
    # Most-progressed wins. Booking > replied > connected > discovered.
    if Booking.query.filter_by(lead_id=lead_id).first():
        return "booked"
    if LeadEngagementEvent.query.filter_by(lead_id=lead_id, event_type="reply").first():
        return "replied"
    prospect = LinkedInProspect.query.filter_by(lead_id=lead_id).first()
    if prospect and prospect.status == "connected":
        return "connected"
    return "discovered"
```

Reasoning: instrumenting every status-changing code path is intrusive and error-prone. A 15-min backfill is fast enough for an A/B dashboard and keeps the diff small. `disqualified` is set manually via PATCH and never overwritten by the backfill.

## API surface

All endpoints under `/api/v1/linkedin/experiments`, decorated with `@login_required_settings`, account-scoped via `g.current_account_id`. New blueprint or extension of the existing `linkedin_api_bp`.

| Method | Path | Body | Returns |
|---|---|---|---|
| `GET` | `/experiments` | — | `{experiments: [{id, name, status, created_at}, ...]}` |
| `GET` | `/experiments/:id` | — | full experiment + both variants + computed metrics block |
| `POST` | `/experiments` | `{name, traffic_split, variants: [{label, titles, industries, company_size_min, company_size_max, geographies}, ...]}` | created experiment |
| `PATCH` | `/experiments/:id` | partial — `{status?, traffic_split?, winner_variant?}` | updated experiment |
| `DELETE` | `/experiments/:id` | — | 204; cascade-deletes variants + assignments |

**Server-side validation:**
- POST or PATCH-to-running with another running experiment for the same account → `409 Conflict`.
- POST must include exactly two variants with labels A and B.
- `winner_variant` only settable when `status='completed'` (otherwise 422).
- `traffic_split` must sum to 100; both keys (A, B) required and non-negative.

**Live metrics block** (computed on each GET, no caching v1):

```json
{
  "metrics": {
    "A": {"discovered": 120, "connected": 28, "replied": 9, "booked": 3, "conversion_pct": 2.5},
    "B": {"discovered": 115, "connected": 41, "replied": 15, "booked": 6, "conversion_pct": 5.2},
    "current_leader": "B",
    "lead_margin_pct": 2.7
  }
}
```

`conversion_pct = booked / discovered * 100`. `current_leader = argmax(conversion_pct)`. `lead_margin_pct = abs(A.conversion_pct - B.conversion_pct)`.

## UI

Lives in the existing **`/marketing/linkedin` page**, not in Settings. The current single-ICP form is the block called "ICP Settings" inside [src/templates/admin/section_linkedin.html](src/templates/admin/section_linkedin.html) (lines 53–83), which is `{% include %}`'d into [src/templates/marketing_ops.html:175](src/templates/marketing_ops.html#L175). JS handlers (e.g. `saveICP()` at line 200) live in the same template file, following the project's "co-located vanilla JS" pattern. The CSRF helper pattern is referenced in [section_youtube.html:156](src/templates/admin/section_youtube.html#L156).

**The "ICP Settings" block evolves into "ICP Experiment".** Behaviour is driven by experiment state:

- **No active experiment** → block renders the existing single-pane ICP Settings form **plus** a prominent "Start an A/B experiment" CTA above it. CTA opens an inline create-experiment form that pre-fills variant A from the current `ICPConfig` row and shows an empty variant B for the user to fill in. POST creates the experiment.
- **Active (running/paused) experiment** → block renders a two-pane editable layout (variant A left, variant B right) with traffic-split slider, status pill, results panel, and "Declare winner" buttons. The legacy single-form is hidden.
- **Completed experiment** → block renders the experiment results as read-only with a "Start a new experiment" button that pre-fills the new POST form using the winner's filters.

Layout (matches user-supplied mockup, replacing/wrapping the existing ICP Settings block):

```
┌───────────────────────────────────────────────────┐
│ ICP Experiment: "Founder vs Co-founder Q2"        │
│ Status: ● running        Traffic: A 50 / B 50     │
├──────────────────────────┬────────────────────────┤
│ ICP A                    │ ICP B                  │
│ Job titles    [editable] │ Job titles  [editable] │
│ Industries    [editable] │ Industries  [editable] │
│ Size min/max  [editable] │ Size min/max[editable] │
│ Geographies   [editable] │ Geographies [editable] │
├───────────────────────────────────────────────────┤
│ A/B Results (refreshed every 15 min)              │
│   ICP A: 120 found, 28 conn, 9 rep, 3 booked      │
│   ICP B: 115 found, 41 conn, 15 rep, 6 booked     │
│   Conversion: A 2.5%  •  B 5.2%                   │
│   Current leader: ICP B   [Declare winner: B]     │
└───────────────────────────────────────────────────┘
```

**Implementation pattern:**
- Edit `src/templates/admin/section_linkedin.html` directly. Keep the existing `#icp-form` block intact (used as variant A in the no-experiment fallback) and add a new `#icp-experiment-block` that the JS shows/hides based on the experiment state fetched on page load.
- Reuse the existing CSRF helper. Add new fetch calls to the new endpoints: `GET /api/v1/linkedin/experiments`, `POST`, `PATCH /experiments/:id`, `DELETE`.
- Metrics auto-refresh every 60 s via `setInterval(fetchExperiment, 60000)` while a running experiment is on screen — light enough; heavier polling not justified.
- Save action: an explicit "Save Experiment" button at the bottom of the two-pane layout (matching the user's mockup and the existing `Save ICP` UX). PATCHes both variants' filters in one request. No auto-save on blur — the 7am discovery cadence makes instant save unnecessary, and an explicit button avoids accidental edits going live.
- Declaring a winner → confirmation modal (existing modal pattern is used elsewhere in the file, e.g. `add-prospect-modal`), then PATCH `{status:"completed", winner_variant:"B"}`.

## Testing approach

TDD per task, RED-first. New test files:

| Layer | Test file | Coverage |
|---|---|---|
| Models | `tests/marketing/test_icp_experiment_models.py` | Cascade delete, label A/B check constraint, traffic_split JSON shape, lead_id uniqueness across assignments |
| Discovery flow | `tests/linkedin/test_discover_with_experiment.py` | When experiment running: variant filters drive search, quota respected, leads tagged. When none running: legacy ICPConfig path fires. Overlap edge case → A wins. |
| Status backfill | `tests/linkedin/test_experiment_metrics_backfill.py` | derive_status returns most-progressed value; disqualified is never overwritten; backfill is idempotent. |
| API | `tests/linkedin/test_experiment_api.py` | POST 2 variants OK / 1 or 3 variants 422 / 2nd running 409, PATCH winner_variant gated on status, DELETE cascades, GET returns metrics block. |
| UI smoke | `tests/linkedin/test_experiment_settings_page.py` | Page renders with logged-in user, form submit POSTs, declare-winner button PATCHes. |

Target ≈ 25–35 new tests. No real LinkedIn API calls — mock the search at the same layer existing linkedin tests do.

## Migration & rollback

**Migration**: I update model files only. You run locally:

```bash
flask db migrate -m "ICP A/B experiments — variants + lead assignments"
```

Review the generated file, then deploy via the CI workflow with the **Force run migrations** option. Three new tables; no changes to existing tables — safe.

**Rollback**: if anything misbehaves on the live system:

```sql
UPDATE icp_experiments SET status = 'paused';
```

Every account immediately reverts to legacy `ICPConfig` discovery. No DDL needed; data is preserved.

To fully remove: rollback the alembic migration. Tables go away. Existing `ICPConfig` rows are unaffected throughout.

## Out of scope (potential follow-ups)

- Multiple concurrent experiments per account (relax 409).
- 3+-way (multivariate) testing.
- Statistical significance / confidence intervals on the metrics block.
- Auto-promotion of winner when significance threshold reached.
- Per-experiment messaging/template variation (today, only filter parameters vary).
- Cross-account experiment templates (one user can clone another's experiment).
