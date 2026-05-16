# Security & Privacy Page Redesign — Spec

**Date:** 2026-05-16
**Status:** Approved

---

## Goal

Rewrite `src/templates/security.html` to enterprise standard, matching the visual quality and brand fidelity of `src/templates/marketing/features.html`. The page must serve as a trust-building centrepiece for enterprise, healthcare, and finance buyers evaluating whether to trust InboxIQ with sensitive email data.

---

## Context

The current `security.html` is a standalone dark-themed page that does not extend `marketing/base.html`. It uses raw Tailwind colours, not brand tokens, and lacks the visual hierarchy and polish of the features page. Key content exists (deployment models, security feature badges) but is presented as a flat list rather than a structured trust narrative.

**Reference template:** `src/templates/marketing/features.html`
**Base template:** `src/templates/marketing/base.html`
**Brand tokens** (defined in `src/tailwind.config.js`):
- `brand-lavender: #F1ECFF` — section backgrounds
- `brand-ink: #0A0A14` — primary text
- `brand-ink-soft: #3F3D5C` — secondary text
- `brand-accent: #5B5BD6` — primary interactive / highlighted state
- `brand-accent-soft: #8B82F0` — accent hover / muted accent
- `brand-success: #10B981` — positive/live status indicators

**Route:** `src/app.py:404` — `return render_template("security.html")`, no explicit vars needed (`current_year` injected via context processor).

---

## Page Structure

### 1. Template wrapper

`security.html` MUST:
- `{% extends "marketing/base.html" %}`
- `{% block body_class %}marketing-body-light{% endblock %}`
- `{% block title %}Security & Privacy — InboxIQ{% endblock %}`

The page renders in the light theme matching the features page.

### 2. Hero section

- **Eyebrow:** `<span class="text-xs font-semibold uppercase tracking-widest text-brand-accent">Security & Privacy</span>`
- **H1:** "You decide where your data lives and which AI touches it."
- **Subtext:** "InboxIQ gives you three deployment models and explicit control over which AI provider processes your emails. No surprises. No lock-in."
- **CTAs:** Primary "Start free trial" (brand-accent background) + Secondary "Configure BYOL in Settings →" (text-brand-accent, no background)
- **Trust strip** (3 items, same pattern as index.html CTA trust strip added in Task 3):
  - Shield icon + "GDPR Ready"
  - Lock icon + "Encrypted in transit & at rest"
  - Key icon + "Use your own LLM key"
- Layout: `text-center`, `max-w-3xl mx-auto`, `space-y-7`, matching features page hero proportions

### 3. Deployment models — centrepiece section

Section heading pattern (eyebrow + H2):
- Eyebrow: "Deployment Models"
- H2: "Pick the deployment that fits your security requirements"
- Subtext: "All plans start on Cloud. BYOL is available today. Self-hosted and Air-gapped are on the roadmap for compliance-heavy industries."

4-column card grid (`grid sm:grid-cols-2 lg:grid-cols-4 gap-6`):

| Card | State | Visual treatment |
|------|-------|-----------------|
| Cloud | Active | Muted/default — white card, `border border-gray-200` |
| BYOL | **Featured/recommended** | `border-2 border-brand-accent bg-brand-lavender` — "Most Popular" badge |
| Self-hosted | Coming soon | Dimmed — `opacity-60`, "Coming soon" pill |
| Air-gapped | Coming soon | Dimmed — `opacity-60`, "Coming soon" pill |

Each card contains: icon (SVG), title, 2-line description, and a feature list (3–4 bullets). BYOL card adds: "Configure in Settings →" link in `text-brand-accent`.

**Card copy:**

*Cloud*
- Title: "Cloud"
- Description: "InboxIQ manages infrastructure. Your emails are processed in our secure multi-tenant environment."
- Features: TLS 1.3 in transit, AES-256 at rest, EU/US region selection, SOC 2 (in progress)

*BYOL (Bring Your Own LLM)*
- Title: "BYOL — Bring Your Own LLM"
- Description: "Connect your own OpenAI, Anthropic, or Azure OpenAI key. AI calls go from your browser to your provider — we never see the payload."
- Features: Zero data retention at InboxIQ for AI payloads, works with any OpenAI-compatible endpoint, rotate or revoke keys at any time, per-inbox key isolation

*Self-hosted*
- Title: "Self-hosted"
- Description: "Deploy InboxIQ inside your own VPC or private cloud. Full control over data residency and network egress."
- Features: Docker + Kubernetes manifests, bring your own Postgres & Redis, no outbound calls except to configured AI provider

*Air-gapped*
- Title: "Air-gapped"
- Description: "Fully isolated deployment with no internet connectivity. Purpose-built for regulated industries and government."
- Features: Offline AI model support (Ollama compatible), signed artefact bundles, audit-ready installation guide

### 4. Security posture grid

Section heading:
- Eyebrow: "Security Posture"
- H2: "Built for teams that take security seriously"

Four 3-column feature groups (2-column on mobile), replacing the current flat badge strip:

**Infrastructure**
- Encryption in transit (TLS 1.3)
- Encryption at rest (AES-256)
- Isolated file serving (files.kalevent.com)

**Access Control**
- JWT-based authentication
- Passkey / WebAuthn support
- Role-scoped API credentials

**Application Security**
- Dependency scanning (Dependabot)
- Secret scanning (GitHub Advanced Security)
- Container image scanning
- SAST / code analysis

**Compliance & Observability**
- Audit log (all authenticated actions)
- Rate limiting on all public endpoints
- GDPR-ready data controls
- Vulnerability disclosure programme

Each feature item: checkmark SVG (`text-brand-success`) + feature name + optional one-line description in `text-brand-ink-soft`.

Layout: `grid md:grid-cols-2 gap-12` for the four groups; within each group, `space-y-4` list.

### 5. AI transparency section

Section heading:
- Eyebrow: "AI Sub-processors"
- H2: "We tell you exactly which AI sees your emails"

Two-column layout: sub-processor table left, explanatory callout right.

**Sub-processor table:**

| Provider | Used for | Data retention | Opt-out |
|----------|----------|---------------|---------|
| OpenAI (default) | Email triage, draft replies | 0 days (Zero Data Retention policy) | Use BYOL to replace |
| Your provider (BYOL) | All AI features | Your own policy | N/A — you control it |

**Right callout box** (`bg-brand-lavender rounded-2xl p-8`):
- Icon + heading: "OpenAI Zero Data Retention"
- Body: "InboxIQ calls OpenAI's API with ZDR enabled. OpenAI does not use your emails to train models and retains no data after responding. [OpenAI ZDR policy →](https://platform.openai.com/docs/models/how-we-use-your-data) (external link)"

### 6. Compliance roadmap + Disclosure + Contact

Three items in a single row (`grid md:grid-cols-3 gap-8`), styled as simple card blocks:

**Compliance roadmap**
- Heading: "Compliance Roadmap"
- Items with status pills: SOC 2 Type I (In progress), GDPR (Ready), HIPAA (Planned), ISO 27001 (Planned)

**Vulnerability disclosure**
- Heading: "Vulnerability Disclosure"
- Body: "We operate a responsible disclosure programme. If you discover a vulnerability, please report it to security@kalevent.com. We aim to acknowledge within 24 hours and resolve critical issues within 72 hours."
- CTA: "Report a vulnerability →" (mailto link)

**Security contact**
- Heading: "Security Team"
- Body: "Questions about our security posture, penetration test results, or compliance documentation? Reach our security team directly."
- CTA: "security@kalevent.com" (mailto link)

### 7. CTA footer block

Matches features page CTA footer:
- Background: `bg-brand-lavender`
- H2: "Ready to take control of your inbox data?"
- Subtext: "Start free — no credit card required. Configure BYOL in under 5 minutes."
- CTA buttons: "Start free trial" (brand-accent) + "Talk to sales" (outline/ghost)

---

## Implementation Notes

- Remove all raw hex colours (`#0A0A14`, `#5B5BD6` etc.) — use brand token classes only
- Remove old `<nav>` — `marketing/base.html` provides the nav
- Remove old `<footer>` — `marketing/base.html` provides the footer
- `current_year` does not need to be passed from the route — the context processor in `src/app.py:222–246` injects it
- After editing `security.html`, run `cd src && npm run build:css` to pick up any new brand token classes
- SVG icons should be inline (no external requests) — reuse icon patterns from `features.html`
- "Coming soon" cards should NOT be links — no `<a>` wrapping, no hover state, just the dimmed card

---

## Out of Scope

- No backend changes
- No new routes
- No actual BYOL configuration UI changes
- No content changes to deployment logic — this is presentation only
