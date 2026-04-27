---
name: linkedin-cadence
description: Standards and workflow for InboxIQ's LinkedIn outreach cadence — agent-driven prospect discovery, message drafting, and daily digest
type: process
---

# LinkedIn Cadence

Use this skill when modifying the LinkedIn outreach pipeline:
`src/tasks/linkedin.py`, `src/api/v1/linkedin.py`, `src/models/campaigns.py` (LinkedInProspect),
`src/models/marketing.py` (ICPConfig), or either DSPy script below.

## Scripts

| Script | Purpose |
| --- | --- |
| [scripts/draft_messages.py](scripts/draft_messages.py) | Drafts all 3 LinkedIn messages in one DSPy call |
| [scripts/match_post.py](scripts/match_post.py) | Selects the best blog post for message 2 |

Run standalone: `python -m skills.linkedin_cadence.scripts.draft_messages`

## Daily Pipeline (Celery beat)

| Time | Task | What it does |
| --- | --- | --- |
| 7:00am | `linkedin.discover_prospects` | Promotes qualifying Leads into LinkedInProspect queue |
| 7:30am | `linkedin.draft_messages` | Drafts 3 messages + selects blog post for each pending prospect |
| 8:00am | `linkedin.send_digest` | Emails the day's due actions to ADMIN_EMAILS |

## Cadence Rules

- **Message 1:** Connection request only. No pitch, no product mention. Max 300 chars.
- **Message 2:** Value only. Share matched blog post. No ask. Max 500 chars. Never send before `connected_at` is set.
- **Message 3:** One soft ask — "would a 15-min call make sense?" Max 400 chars. Never before message 2 is marked sent.
- **Disqualify** after 14 days with no response to message 3.

## Status Flow

```
pending -> connection_sent -> connected -> message_2_sent -> message_3_sent -> replied -> qualified -> disqualified
```

`_advance_prospect()` in `src/api/v1/linkedin.py` handles all transitions and computes due dates:
- `connected_at` set -> `message_2_due_at = connected_at + 3 days`
- `message_2_sent_at` set -> `message_3_due_at = message_2_sent_at + 5 days`

## ICP

Stored in `ICPConfig` (`src/models/marketing.py`). Never hardcoded in task code.
Edit via Marketing Ops -> LinkedIn -> ICP Settings, or `POST /api/v1/linkedin/icp`.

Defaults: Founder / Head of Support / Operations Lead / Customer Success Lead, B2B SaaS / Software, 10-50 employees, UK / US / Nigeria.

## Funnel Integration

| Status reached | Lead action |
| --- | --- |
| `replied` | `lead.current_funnel_stage = "consideration"` |
| `qualified` | `lead.current_funnel_stage = "conversion"` |

Handled inside `_advance_lead_stage()` in `src/api/v1/linkedin.py`.

## Checklist Before Changing the Pipeline

- [ ] All DB writes wrapped in try/except with `db.session.rollback()` on failure
- [ ] `discover_prospects` queries scoped by `account_id`
- [ ] `_advance_prospect` handles all 7 status transitions without skipping
- [ ] DSPy scripts import `_configure_dspy()` before instantiating modules
- [ ] New Celery tasks registered in `src/celery_inboxiq.py` beat_schedule AND the autodiscover list
