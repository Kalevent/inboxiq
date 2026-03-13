# How InboxIQ learns from corrections

InboxIQ improves automatically as you use it. Every time you correct a classification, InboxIQ records it and adjusts future behaviour.

## How corrections work

When InboxIQ misclassifies an email:

- **Gmail** — move the email to the correct `InboxIQ/` label in the sidebar. InboxIQ detects the move on the next poll.
- **Outlook** — right-click → Categorize → select the correct `InboxIQ/` category.

No forms to fill in. No buttons to click. The correction happens through your normal inbox workflow.

## What InboxIQ learns

Each correction updates two things:

1. **Sender profile** — InboxIQ builds a profile for each sender domain. After a few corrections from the same domain, it classifies future emails from that domain more accurately.

2. **DSPy training data** — Corrections are collected and used to periodically retrain the underlying classification model. This improves accuracy across all emails, not just from corrected senders.

## How long before improvements show?

- **Sender profiles** — you'll notice improvement after 3–5 corrections from the same sender domain, often within a few days.
- **Model retraining** — happens periodically (not in real-time). Improvements from retraining are typically visible after 2–4 weeks of regular use.

## Related articles

- [How emails are classified](/kb/triage-and-ai/how-emails-are-classified)
- [Adjusting your confidence threshold](/kb/triage-and-ai/confidence-threshold)
