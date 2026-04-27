# Growth Marketing Skills

Reusable skills for executing InboxIQ's growth and marketing strategy consistently.
Each skill is a repeatable process. Use the right skill for the job — don't improvise.

---

## Structure

```text
skills/
  <skill-name>/
    skill.md          ← the process (steps, decisions, rules)
    templates/        ← static copy (email templates, message scripts)
    scripts/          ← DSPy-based scripts for any LLM calls
```

**Rule:** All LLM calls go through DSPy (`scripts/`). No raw prompts.

---

## Skills Index

### Research & Qualification

| Skill | When to use |
| ----- | ----------- |
| [lead_research](lead_research/skill.md) | Research an individual prospect before outreach |
| [lead_qualification](lead_qualification/skill.md) | Score a lead against ICP before spending time on them |
| [seo_research](seo_research/skill.md) | Find what your ICP searches for before writing content |

### Outreach

| Skill | When to use |
| ----- | ----------- |
| [cold_email](cold_email/skill.md) | Write a personalised first-touch email to a prospect |
| [outreach_sequencing](outreach_sequencing/skill.md) | Design a full multi-touch outreach sequence |
| [follow_up](follow_up/skill.md) | Follow up after no reply — tone, timing, when to stop |
| [linkedin_cadence](linkedin_cadence/skill.md) | Run the 3-message LinkedIn DM sequence for a prospect |

### Content

| Skill | When to use |
| ----- | ----------- |
| [content_linkedin](content_linkedin/skill.md) | Write LinkedIn posts for thought leadership and awareness |
| [blog_publishing](blog_publishing/skill.md) | Generate, quality-check, and publish a blog post |

### Analysis

| Skill | When to use |
| ----- | ----------- |
| [campaign_analysis](campaign_analysis/skill.md) | Review what's working — opens, replies, conversions |

---

## Traffic Strategy

Three-phase plan to drive qualified traffic and convert trials:

- **Phase 1** — Fix the destination: blog publishing + landing page credibility *(implemented, evaluating)*
- **Phase 2** — Activate outreach: systematic LinkedIn cadence
- **Phase 3** — Amplify with paid: targeted LinkedIn Ads *(starts only after Phase 1 proven)*

Full spec: `docs/superpowers/specs/2026-04-24-traffic-conversion-design.md`

---

## ICP Priority

1. B2B SaaS (Founder, Head of Support, Operations Lead — 10–50 employees, UK + US)
2. E-commerce
3. Healthcare *(blocked on FHIR integration — do not prioritise)*
