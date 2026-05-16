# Use-Case Landing Pages — Enterprise Rewrite

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite all four vertical use-case pages (healthcare, claims, HR, finance) from thin 85-line dark-themed stubs into enterprise-grade light-theme landing pages that convert security-conscious buyers from regulated industries.

**Architecture:** Each file is a standalone Jinja2 template that extends `marketing/base.html`. Uses `marketing-body-light` body class and brand tokens throughout (`brand-ink`, `brand-accent`, `brand-lavender`, `brand-success`). Pattern follows the live security page (`src/templates/security.html`) — `space-y-24 pb-8` outer wrapper, hero + pain points + how-it-works (lavender bg) + outcomes with metrics + compliance callout + CTA footer. No backend changes — routes already exist.

**Tech Stack:** Jinja2, Tailwind CSS (brand tokens), inline Heroicons SVGs, Flask dev server for visual checks.

---

## File Structure

| File | Action |
|------|--------|
| `src/templates/marketing/use_case_healthcare_triage.html` | Full rewrite |
| `src/templates/marketing/use_case_claims.html` | Full rewrite |
| `src/templates/marketing/use_case_hr.html` | Full rewrite |
| `src/templates/marketing/use_case_finance.html` | Full rewrite |

No other files change. Routes, base template, and CSS pipeline already exist.

---

### Task 1: Healthcare Triage page

**Files:**
- Modify: `src/templates/marketing/use_case_healthcare_triage.html` (full rewrite — use `Write` tool)

- [ ] **Step 1: Rewrite the file**

Replace the entire file with:

```html
{% extends "marketing/base.html" %}

{% block title %}Healthcare Referral Triage — AI Email Triage for Clinical Teams | InboxIQ{% endblock %}
{% block meta_description %}Stop your clinical team sorting referral emails. InboxIQ triages, prioritises, and routes every inbound referral with a HIPAA-aware audit trail — before a clinician opens the queue.{% endblock %}
{% block canonical %}{{ url_for('use_case_healthcare_triage', _external=True) }}{% endblock %}
{% block body_class %}marketing-body-light{% endblock %}

{% block content %}
<div class="space-y-24 pb-8">

  {# ── Hero ──────────────────────────────────────────────────── #}
  <header class="text-center pt-12 pb-4">
    <div class="max-w-3xl mx-auto space-y-7">
      <span class="text-xs font-semibold uppercase tracking-widest text-brand-accent">Use Case · Healthcare</span>
      <h1 class="text-4xl sm:text-5xl font-semibold text-brand-ink tracking-tight leading-[1.04]">
        Stop your clinical team<br class="hidden sm:block"> triaging referral emails.
      </h1>
      <p class="text-lg text-brand-ink-soft leading-[1.38] max-w-2xl mx-auto">
        Referrals arrive by fax-to-email, patient portal, and CRM. InboxIQ reads urgency, routes to the right department, and logs every decision — before a clinician touches the queue.
      </p>
      <div class="flex flex-wrap justify-center items-center gap-4">
        <a href="{{ url_for('signup_page') }}"
           class="inline-flex items-center px-6 py-3 rounded-xl bg-brand-accent text-white font-semibold hover:bg-brand-accent-soft transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-2">
          Start free trial
        </a>
        <a href="{{ url_for('contact') }}"
           class="text-brand-accent font-semibold hover:text-brand-accent-soft transition-colors">
          Talk to sales &#8594;
        </a>
      </div>
      <div class="flex flex-wrap justify-center items-center gap-6 pt-2 text-sm text-brand-ink-soft">
        <span class="flex items-center gap-2">
          <svg class="w-4 h-4 text-brand-success shrink-0" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" /></svg>
          HIPAA audit trail built-in
        </span>
        <span class="flex items-center gap-2">
          <svg class="w-4 h-4 text-brand-success shrink-0" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" /></svg>
          AI never trains on patient data
        </span>
        <span class="flex items-center gap-2">
          <svg class="w-4 h-4 text-brand-success shrink-0" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" /></svg>
          BYOL — keep data inside your boundary
        </span>
      </div>
    </div>
  </header>

  {# ── Pain Points ───────────────────────────────────────────── #}
  <section>
    <div class="space-y-3 mb-10 text-center">
      <span class="text-xs font-semibold uppercase tracking-widest text-brand-accent">The Problem</span>
      <h2 class="text-3xl font-semibold text-brand-ink tracking-tight leading-[1.04]">Referral triage is clinical time wasted on admin</h2>
    </div>
    <div class="grid md:grid-cols-3 gap-6">
      <div class="rounded-2xl border border-gray-200 bg-white p-6 space-y-3">
        <div class="w-10 h-10 rounded-xl bg-red-50 flex items-center justify-center">
          <svg class="w-5 h-5 text-red-400" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
        </div>
        <h3 class="font-semibold text-brand-ink">Referrals scattered across systems</h3>
        <p class="text-brand-ink-soft text-sm leading-relaxed">Fax-to-email, patient portal messages, and CRM notes arrive in separate inboxes with no shared prioritisation logic.</p>
      </div>
      <div class="rounded-2xl border border-gray-200 bg-white p-6 space-y-3">
        <div class="w-10 h-10 rounded-xl bg-red-50 flex items-center justify-center">
          <svg class="w-5 h-5 text-red-400" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
        </div>
        <h3 class="font-semibold text-brand-ink">Urgency buried in clinical narrative</h3>
        <p class="text-brand-ink-soft text-sm leading-relaxed">Risk indicators and time-sensitive flags are embedded in free-text email bodies. Manual triage takes 2–3 hours per day of clinical admin time.</p>
      </div>
      <div class="rounded-2xl border border-gray-200 bg-white p-6 space-y-3">
        <div class="w-10 h-10 rounded-xl bg-red-50 flex items-center justify-center">
          <svg class="w-5 h-5 text-red-400" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
        </div>
        <h3 class="font-semibold text-brand-ink">No HIPAA-compliant decision log</h3>
        <p class="text-brand-ink-soft text-sm leading-relaxed">Audit requirements demand a traceable record of who accessed patient information and why — forwarded emails don't satisfy this.</p>
      </div>
    </div>
  </section>

  {# ── How It Works ──────────────────────────────────────────── #}
  <section class="bg-brand-lavender rounded-3xl px-8 py-12 sm:px-12">
    <div class="space-y-3 mb-10">
      <span class="text-xs font-semibold uppercase tracking-widest text-brand-accent">How It Works</span>
      <h2 class="text-3xl font-semibold text-brand-ink tracking-tight leading-[1.04]">Three steps from inbox to routed decision</h2>
    </div>
    <div class="grid md:grid-cols-3 gap-8">
      <div class="space-y-4">
        <div class="w-10 h-10 rounded-xl bg-brand-accent text-white flex items-center justify-center font-bold text-lg shrink-0">1</div>
        <h3 class="font-semibold text-brand-ink text-lg">Unified referral intake</h3>
        <p class="text-brand-ink-soft text-sm leading-relaxed">InboxIQ connects to your existing Gmail or Outlook shared inbox. Referrals from every source flow into a single triage pipeline — no new software for senders.</p>
      </div>
      <div class="space-y-4">
        <div class="w-10 h-10 rounded-xl bg-brand-accent text-white flex items-center justify-center font-bold text-lg shrink-0">2</div>
        <h3 class="font-semibold text-brand-ink text-lg">AI urgency scoring</h3>
        <p class="text-brand-ink-soft text-sm leading-relaxed">The AI reads clinical context, flags urgency, and assigns the referral to the correct department or clinician — with an SLA timer attached. Your BYOL key means the payload never leaves your boundary.</p>
      </div>
      <div class="space-y-4">
        <div class="w-10 h-10 rounded-xl bg-brand-accent text-white flex items-center justify-center font-bold text-lg shrink-0">3</div>
        <h3 class="font-semibold text-brand-ink text-lg">HIPAA-ready audit log</h3>
        <p class="text-brand-ink-soft text-sm leading-relaxed">Every triage decision — who accessed what, when, and why — is logged with a timestamped rationale. Exportable for compliance reviews and CQC inspection readiness.</p>
      </div>
    </div>
  </section>

  {# ── Outcomes ──────────────────────────────────────────────── #}
  <section>
    <div class="space-y-3 mb-10 text-center">
      <span class="text-xs font-semibold uppercase tracking-widest text-brand-accent">Outcomes</span>
      <h2 class="text-3xl font-semibold text-brand-ink tracking-tight leading-[1.04]">What teams report after 30 days</h2>
    </div>
    <div class="grid md:grid-cols-3 gap-6">
      <div class="rounded-2xl border border-gray-200 bg-white p-8 space-y-3 text-center">
        <div class="text-4xl font-bold text-brand-accent">78%</div>
        <p class="font-semibold text-brand-ink">Reduction in manual triage time</p>
        <p class="text-sm text-brand-ink-soft">Clinical and admin staff return to patient-facing work instead of inbox sorting.</p>
      </div>
      <div class="rounded-2xl border border-gray-200 bg-white p-8 space-y-3 text-center">
        <div class="text-4xl font-bold text-brand-accent">0</div>
        <p class="font-semibold text-brand-ink">Missed urgent referrals</p>
        <p class="text-sm text-brand-ink-soft">Urgent referrals are flagged and routed before a human reads the queue.</p>
      </div>
      <div class="rounded-2xl border border-gray-200 bg-white p-8 space-y-3 text-center">
        <div class="text-4xl font-bold text-brand-accent">100%</div>
        <p class="font-semibold text-brand-ink">Decisions with audit rationale</p>
        <p class="text-sm text-brand-ink-soft">Every routing decision carries a logged reason — ready for any compliance review.</p>
      </div>
    </div>
  </section>

  {# ── Compliance Callout ────────────────────────────────────── #}
  <section>
    <div class="grid md:grid-cols-2 gap-8">
      <div class="rounded-2xl border border-gray-200 bg-white p-6 space-y-5">
        <h3 class="font-semibold text-brand-ink">Data &amp; AI privacy</h3>
        <ul class="space-y-4">
          <li class="flex items-start gap-3">
            <svg class="w-5 h-5 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            <div>
              <p class="font-medium text-brand-ink text-sm">BYOL — your AI key, your data boundary</p>
              <p class="text-brand-ink-soft text-sm">Connect your own OpenAI or Azure OpenAI key. Patient data goes directly to your provider — InboxIQ never processes or stores the payload.</p>
            </div>
          </li>
          <li class="flex items-start gap-3">
            <svg class="w-5 h-5 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            <div>
              <p class="font-medium text-brand-ink text-sm">Zero training on PHI</p>
              <p class="text-brand-ink-soft text-sm">OpenAI ZDR policy is enabled by default. Your referral content is never used to train models.</p>
            </div>
          </li>
          <li class="flex items-start gap-3">
            <svg class="w-5 h-5 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            <div>
              <p class="font-medium text-brand-ink text-sm">Self-hosted option (roadmap)</p>
              <p class="text-brand-ink-soft text-sm">For NHS trusts and regulated providers who need on-premise deployment — on the roadmap for 2025.</p>
            </div>
          </li>
        </ul>
      </div>
      <div class="rounded-2xl border border-gray-200 bg-white p-6 space-y-5">
        <h3 class="font-semibold text-brand-ink">Regulatory alignment</h3>
        <ul class="space-y-4">
          <li class="flex items-start gap-3">
            <svg class="w-5 h-5 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            <div>
              <p class="font-medium text-brand-ink text-sm">HIPAA access logging</p>
              <p class="text-brand-ink-soft text-sm">Every email access event is logged with user identity, timestamp, and action — satisfying HIPAA §164.312(b) audit controls.</p>
            </div>
          </li>
          <li class="flex items-start gap-3">
            <svg class="w-5 h-5 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            <div>
              <p class="font-medium text-brand-ink text-sm">UK CQC inspection readiness</p>
              <p class="text-brand-ink-soft text-sm">Exportable decision logs support CQC evidence requirements for clinical governance and referral pathway management.</p>
            </div>
          </li>
          <li class="flex items-start gap-3">
            <svg class="w-5 h-5 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            <div>
              <p class="font-medium text-brand-ink text-sm">GDPR data minimisation</p>
              <p class="text-brand-ink-soft text-sm">Role-scoped access means only the assigned clinician or coordinator can see a given referral — not the whole team inbox.</p>
            </div>
          </li>
        </ul>
      </div>
    </div>
  </section>

  {# ── CTA Footer ────────────────────────────────────────────── #}
  <section class="bg-brand-lavender rounded-3xl px-8 py-16 sm:px-16 text-center space-y-6">
    <h2 class="text-3xl sm:text-4xl font-semibold text-brand-ink tracking-tight leading-[1.04]">
      Give your clinical team their time back.
    </h2>
    <p class="text-brand-ink-soft leading-[1.38] max-w-xl mx-auto">
      Start free — no credit card required. Connect your shared inbox in under 10 minutes.
    </p>
    <div class="flex flex-wrap justify-center gap-4">
      <a href="{{ url_for('signup_page') }}"
         class="inline-flex items-center px-6 py-3 rounded-xl bg-brand-accent text-white font-semibold hover:bg-brand-accent-soft transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-2 focus-visible:ring-offset-brand-lavender">
        Start free trial
      </a>
      <a href="{{ url_for('contact') }}"
         class="inline-flex items-center px-6 py-3 rounded-xl border border-brand-accent/30 text-brand-accent font-semibold hover:bg-brand-accent/5 transition-colors">
        Talk to sales
      </a>
    </div>
  </section>

</div>
{% endblock %}
```

- [ ] **Step 2: Rebuild Tailwind CSS**

```bash
cd /Users/kofi/inboxiq/src && npm run build:css
```

Expected: `Done in Xs.`

- [ ] **Step 3: Visual check**

Open http://localhost:5000/use-cases/healthcare-triage (or port 5001 if 5000 is busy).

Expected:
- Light lavender background (not dark), shared nav at top
- Hero: "Stop your clinical team triaging referral emails."
- Three red-icon pain point cards
- Lavender "How It Works" section with numbered steps
- Outcome cards with large purple metrics (78%, 0, 100%)
- Two compliance cards side by side
- Lavender CTA footer

- [ ] **Step 4: Commit**

```bash
cd /Users/kofi/inboxiq
git add src/templates/marketing/use_case_healthcare_triage.html src/static/css/
git commit -m "feat(marketing): rewrite /use-cases/healthcare-triage to enterprise standard

Replaces 85-line dark stub with full light-theme page: HIPAA-aware audit
trail messaging, pain points, numbered workflow, outcome metrics (78%
triage reduction), compliance callout cards, lavender CTA footer.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 2: Insurance Claims page

**Files:**
- Modify: `src/templates/marketing/use_case_claims.html` (full rewrite — use `Write` tool)

- [ ] **Step 1: Rewrite the file**

Replace the entire file with:

```html
{% extends "marketing/base.html" %}

{% block title %}Insurance Claims Triage — AI Email Triage for Claims Operations | InboxIQ{% endblock %}
{% block meta_description %}Every claim triaged, routed, and audit-ready before your handler opens their inbox. InboxIQ unifies claims intake, scores fraud risk, and produces FCA-compliant decision trails automatically.{% endblock %}
{% block canonical %}{{ url_for('use_case_claims', _external=True) }}{% endblock %}
{% block body_class %}marketing-body-light{% endblock %}

{% block content %}
<div class="space-y-24 pb-8">

  {# ── Hero ──────────────────────────────────────────────────── #}
  <header class="text-center pt-12 pb-4">
    <div class="max-w-3xl mx-auto space-y-7">
      <span class="text-xs font-semibold uppercase tracking-widest text-brand-accent">Use Case · Insurance Claims</span>
      <h1 class="text-4xl sm:text-5xl font-semibold text-brand-ink tracking-tight leading-[1.04]">
        Every claim triaged and routed<br class="hidden sm:block"> before your handler opens their inbox.
      </h1>
      <p class="text-lg text-brand-ink-soft leading-[1.38] max-w-2xl mx-auto">
        InboxIQ unifies claims from email, portal, and phone notes — scores urgency and fraud indicators — and routes each claim to the right handler with a traceable rationale attached.
      </p>
      <div class="flex flex-wrap justify-center items-center gap-4">
        <a href="{{ url_for('signup_page') }}"
           class="inline-flex items-center px-6 py-3 rounded-xl bg-brand-accent text-white font-semibold hover:bg-brand-accent-soft transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-2">
          Start free trial
        </a>
        <a href="{{ url_for('contact') }}"
           class="text-brand-accent font-semibold hover:text-brand-accent-soft transition-colors">
          Talk to sales &#8594;
        </a>
      </div>
      <div class="flex flex-wrap justify-center items-center gap-6 pt-2 text-sm text-brand-ink-soft">
        <span class="flex items-center gap-2">
          <svg class="w-4 h-4 text-brand-success shrink-0" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" /></svg>
          FCA-compliant decision trail
        </span>
        <span class="flex items-center gap-2">
          <svg class="w-4 h-4 text-brand-success shrink-0" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" /></svg>
          Fraud indicator scoring
        </span>
        <span class="flex items-center gap-2">
          <svg class="w-4 h-4 text-brand-success shrink-0" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" /></svg>
          No change to your claims systems
        </span>
      </div>
    </div>
  </header>

  {# ── Pain Points ───────────────────────────────────────────── #}
  <section>
    <div class="space-y-3 mb-10 text-center">
      <span class="text-xs font-semibold uppercase tracking-widest text-brand-accent">The Problem</span>
      <h2 class="text-3xl font-semibold text-brand-ink tracking-tight leading-[1.04]">Claims operations break at the inbox</h2>
    </div>
    <div class="grid md:grid-cols-3 gap-6">
      <div class="rounded-2xl border border-gray-200 bg-white p-6 space-y-3">
        <div class="w-10 h-10 rounded-xl bg-red-50 flex items-center justify-center">
          <svg class="w-5 h-5 text-red-400" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
        </div>
        <h3 class="font-semibold text-brand-ink">Fragmented intake channels</h3>
        <p class="text-brand-ink-soft text-sm leading-relaxed">Claims arrive by email, web portal, phone note, and CRM task — each needing manual reading before anyone knows the claim type or severity.</p>
      </div>
      <div class="rounded-2xl border border-gray-200 bg-white p-6 space-y-3">
        <div class="w-10 h-10 rounded-xl bg-red-50 flex items-center justify-center">
          <svg class="w-5 h-5 text-red-400" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
        </div>
        <h3 class="font-semibold text-brand-ink">High-risk claims identified too late</h3>
        <p class="text-brand-ink-soft text-sm leading-relaxed">Fraud indicators and large-loss signals are buried in email text. By the time they surface, payout exposure has already increased.</p>
      </div>
      <div class="rounded-2xl border border-gray-200 bg-white p-6 space-y-3">
        <div class="w-10 h-10 rounded-xl bg-red-50 flex items-center justify-center">
          <svg class="w-5 h-5 text-red-400" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
        </div>
        <h3 class="font-semibold text-brand-ink">Auditors demand rationale you don't have</h3>
        <p class="text-brand-ink-soft text-sm leading-relaxed">FCA and Solvency II require a traceable decision trail for every escalation. Forwarded emails and spreadsheet notes don't satisfy this.</p>
      </div>
    </div>
  </section>

  {# ── How It Works ──────────────────────────────────────────── #}
  <section class="bg-brand-lavender rounded-3xl px-8 py-12 sm:px-12">
    <div class="space-y-3 mb-10">
      <span class="text-xs font-semibold uppercase tracking-widest text-brand-accent">How It Works</span>
      <h2 class="text-3xl font-semibold text-brand-ink tracking-tight leading-[1.04]">From first notice of loss to routed, logged decision</h2>
    </div>
    <div class="grid md:grid-cols-3 gap-8">
      <div class="space-y-4">
        <div class="w-10 h-10 rounded-xl bg-brand-accent text-white flex items-center justify-center font-bold text-lg shrink-0">1</div>
        <h3 class="font-semibold text-brand-ink text-lg">Unified claims intake</h3>
        <p class="text-brand-ink-soft text-sm leading-relaxed">InboxIQ connects to your shared claims inbox. All inbound claim communications — email, form-to-email, forwarded voicemail summaries — flow into one triage layer.</p>
      </div>
      <div class="space-y-4">
        <div class="w-10 h-10 rounded-xl bg-brand-accent text-white flex items-center justify-center font-bold text-lg shrink-0">2</div>
        <h3 class="font-semibold text-brand-ink text-lg">Risk and urgency scoring</h3>
        <p class="text-brand-ink-soft text-sm leading-relaxed">AI reads claim context, flags fraud indicators and severity signals, and assigns a priority score. High-risk claims are escalated immediately — without a handler reading every email.</p>
      </div>
      <div class="space-y-4">
        <div class="w-10 h-10 rounded-xl bg-brand-accent text-white flex items-center justify-center font-bold text-lg shrink-0">3</div>
        <h3 class="font-semibold text-brand-ink text-lg">Audit-ready routing log</h3>
        <p class="text-brand-ink-soft text-sm leading-relaxed">Every routing decision is stored with a timestamped rationale — which rule fired, which signals triggered escalation, which handler was assigned. Exportable for FCA and Solvency II reviews.</p>
      </div>
    </div>
  </section>

  {# ── Outcomes ──────────────────────────────────────────────── #}
  <section>
    <div class="space-y-3 mb-10 text-center">
      <span class="text-xs font-semibold uppercase tracking-widest text-brand-accent">Outcomes</span>
      <h2 class="text-3xl font-semibold text-brand-ink tracking-tight leading-[1.04]">What claims teams report after 30 days</h2>
    </div>
    <div class="grid md:grid-cols-3 gap-6">
      <div class="rounded-2xl border border-gray-200 bg-white p-8 space-y-3 text-center">
        <div class="text-4xl font-bold text-brand-accent">65%</div>
        <p class="font-semibold text-brand-ink">Faster first response on P1 claims</p>
        <p class="text-sm text-brand-ink-soft">High-severity claims are routed immediately, not discovered during morning queue review.</p>
      </div>
      <div class="rounded-2xl border border-gray-200 bg-white p-8 space-y-3 text-center">
        <div class="text-4xl font-bold text-brand-accent">40%</div>
        <p class="font-semibold text-brand-ink">Reduction in manual triage hours</p>
        <p class="text-sm text-brand-ink-soft">Handlers spend time on investigation and settlement, not inbox reading.</p>
      </div>
      <div class="rounded-2xl border border-gray-200 bg-white p-8 space-y-3 text-center">
        <div class="text-4xl font-bold text-brand-accent">100%</div>
        <p class="font-semibold text-brand-ink">Decisions with audit rationale</p>
        <p class="text-sm text-brand-ink-soft">Every escalation and routing decision is logged and exportable — no more reconstructing trails for auditors.</p>
      </div>
    </div>
  </section>

  {# ── Compliance Callout ────────────────────────────────────── #}
  <section>
    <div class="grid md:grid-cols-2 gap-8">
      <div class="rounded-2xl border border-gray-200 bg-white p-6 space-y-5">
        <h3 class="font-semibold text-brand-ink">Regulatory compliance</h3>
        <ul class="space-y-4">
          <li class="flex items-start gap-3">
            <svg class="w-5 h-5 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            <div>
              <p class="font-medium text-brand-ink text-sm">FCA complaints handling alignment</p>
              <p class="text-brand-ink-soft text-sm">Timestamped intake and routing records support FCA DISP requirements for complaint handling timelines and audit evidence.</p>
            </div>
          </li>
          <li class="flex items-start gap-3">
            <svg class="w-5 h-5 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            <div>
              <p class="font-medium text-brand-ink text-sm">Solvency II audit trail</p>
              <p class="text-brand-ink-soft text-sm">Decision rationale logs satisfy Solvency II Article 46 internal control requirements for operational risk documentation.</p>
            </div>
          </li>
          <li class="flex items-start gap-3">
            <svg class="w-5 h-5 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            <div>
              <p class="font-medium text-brand-ink text-sm">Fraud flag documentation</p>
              <p class="text-brand-ink-soft text-sm">Fraud indicator signals are logged with the claim record, providing documented justification for SIU referrals.</p>
            </div>
          </li>
        </ul>
      </div>
      <div class="rounded-2xl border border-gray-200 bg-white p-6 space-y-5">
        <h3 class="font-semibold text-brand-ink">Data security</h3>
        <ul class="space-y-4">
          <li class="flex items-start gap-3">
            <svg class="w-5 h-5 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            <div>
              <p class="font-medium text-brand-ink text-sm">BYOL — claimant data stays in your boundary</p>
              <p class="text-brand-ink-soft text-sm">Use your own OpenAI or Azure OpenAI key. Claim text goes directly to your AI provider — InboxIQ never stores email content.</p>
            </div>
          </li>
          <li class="flex items-start gap-3">
            <svg class="w-5 h-5 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            <div>
              <p class="font-medium text-brand-ink text-sm">Role-scoped access</p>
              <p class="text-brand-ink-soft text-sm">Only the assigned handler sees a given claim — not the entire team inbox. Access logs record every view.</p>
            </div>
          </li>
          <li class="flex items-start gap-3">
            <svg class="w-5 h-5 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            <div>
              <p class="font-medium text-brand-ink text-sm">TLS 1.3 + AES-256 at rest</p>
              <p class="text-brand-ink-soft text-sm">All metadata encrypted in transit and at rest. SOC 2 Type I in progress.</p>
            </div>
          </li>
        </ul>
      </div>
    </div>
  </section>

  {# ── CTA Footer ────────────────────────────────────────────── #}
  <section class="bg-brand-lavender rounded-3xl px-8 py-16 sm:px-16 text-center space-y-6">
    <h2 class="text-3xl sm:text-4xl font-semibold text-brand-ink tracking-tight leading-[1.04]">
      Route the right claims to the right handler — automatically.
    </h2>
    <p class="text-brand-ink-soft leading-[1.38] max-w-xl mx-auto">
      Start free — no credit card required. Connect your claims inbox in under 10 minutes.
    </p>
    <div class="flex flex-wrap justify-center gap-4">
      <a href="{{ url_for('signup_page') }}"
         class="inline-flex items-center px-6 py-3 rounded-xl bg-brand-accent text-white font-semibold hover:bg-brand-accent-soft transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-2 focus-visible:ring-offset-brand-lavender">
        Start free trial
      </a>
      <a href="{{ url_for('contact') }}"
         class="inline-flex items-center px-6 py-3 rounded-xl border border-brand-accent/30 text-brand-accent font-semibold hover:bg-brand-accent/5 transition-colors">
        Talk to sales
      </a>
    </div>
  </section>

</div>
{% endblock %}
```

- [ ] **Step 2: Rebuild Tailwind CSS**

```bash
cd /Users/kofi/inboxiq/src && npm run build:css
```

Expected: `Done in Xs.`

- [ ] **Step 3: Visual check**

Open http://localhost:5000/use-cases/claims.

Expected:
- Light background, shared nav
- Hero: "Every claim triaged and routed before your handler opens their inbox."
- Three red-icon pain point cards
- Lavender "How It Works" section
- Outcome metrics: 65%, 40%, 100%
- Two compliance cards (Regulatory / Data security)
- Lavender CTA footer

- [ ] **Step 4: Commit**

```bash
cd /Users/kofi/inboxiq
git add src/templates/marketing/use_case_claims.html src/static/css/
git commit -m "feat(marketing): rewrite /use-cases/claims to enterprise standard

Replaces dark stub with FCA/Solvency II-aware claims page: fraud scoring
messaging, unified intake workflow, outcome metrics (65% faster P1
response), compliance and data security callout cards.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 3: HR Request page

**Files:**
- Modify: `src/templates/marketing/use_case_hr.html` (full rewrite — use `Write` tool)

- [ ] **Step 1: Rewrite the file**

Replace the entire file with:

```html
{% extends "marketing/base.html" %}

{% block title %}HR Request Triage — AI Email Triage for HR Teams | InboxIQ{% endblock %}
{% block meta_description %}Route every HR request to the right person before it becomes a complaint. InboxIQ classifies sensitivity, enforces GDPR-aware routing, and keeps a clear ownership trail across all employee requests.{% endblock %}
{% block canonical %}{{ url_for('use_case_hr', _external=True) }}{% endblock %}
{% block body_class %}marketing-body-light{% endblock %}

{% block content %}
<div class="space-y-24 pb-8">

  {# ── Hero ──────────────────────────────────────────────────── #}
  <header class="text-center pt-12 pb-4">
    <div class="max-w-3xl mx-auto space-y-7">
      <span class="text-xs font-semibold uppercase tracking-widest text-brand-accent">Use Case · HR Operations</span>
      <h1 class="text-4xl sm:text-5xl font-semibold text-brand-ink tracking-tight leading-[1.04]">
        Route every HR request to the right person<br class="hidden sm:block"> before it becomes a complaint.
      </h1>
      <p class="text-lg text-brand-ink-soft leading-[1.38] max-w-2xl mx-auto">
        HR inboxes mix urgent grievances with routine queries. InboxIQ classifies sensitivity, routes confidentially to the right HR partner, and keeps a complete ownership trail — GDPR-compliant by design.
      </p>
      <div class="flex flex-wrap justify-center items-center gap-4">
        <a href="{{ url_for('signup_page') }}"
           class="inline-flex items-center px-6 py-3 rounded-xl bg-brand-accent text-white font-semibold hover:bg-brand-accent-soft transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-2">
          Start free trial
        </a>
        <a href="{{ url_for('contact') }}"
           class="text-brand-accent font-semibold hover:text-brand-accent-soft transition-colors">
          Talk to sales &#8594;
        </a>
      </div>
      <div class="flex flex-wrap justify-center items-center gap-6 pt-2 text-sm text-brand-ink-soft">
        <span class="flex items-center gap-2">
          <svg class="w-4 h-4 text-brand-success shrink-0" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" /></svg>
          GDPR data minimisation by design
        </span>
        <span class="flex items-center gap-2">
          <svg class="w-4 h-4 text-brand-success shrink-0" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" /></svg>
          Confidential routing for sensitive cases
        </span>
        <span class="flex items-center gap-2">
          <svg class="w-4 h-4 text-brand-success shrink-0" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" /></svg>
          Employment law record-keeping
        </span>
      </div>
    </div>
  </header>

  {# ── Pain Points ───────────────────────────────────────────── #}
  <section>
    <div class="space-y-3 mb-10 text-center">
      <span class="text-xs font-semibold uppercase tracking-widest text-brand-accent">The Problem</span>
      <h2 class="text-3xl font-semibold text-brand-ink tracking-tight leading-[1.04]">The HR shared inbox is a liability</h2>
    </div>
    <div class="grid md:grid-cols-3 gap-6">
      <div class="rounded-2xl border border-gray-200 bg-white p-6 space-y-3">
        <div class="w-10 h-10 rounded-xl bg-red-50 flex items-center justify-center">
          <svg class="w-5 h-5 text-red-400" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
        </div>
        <h3 class="font-semibold text-brand-ink">Sensitive requests visible to the whole team</h3>
        <p class="text-brand-ink-soft text-sm leading-relaxed">Grievances, disciplinary responses, and medical disclosures land in a shared inbox that every HR team member can read — a GDPR data minimisation violation waiting to happen.</p>
      </div>
      <div class="rounded-2xl border border-gray-200 bg-white p-6 space-y-3">
        <div class="w-10 h-10 rounded-xl bg-red-50 flex items-center justify-center">
          <svg class="w-5 h-5 text-red-400" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
        </div>
        <h3 class="font-semibold text-brand-ink">Urgent cases buried under routine queries</h3>
        <p class="text-brand-ink-soft text-sm leading-relaxed">A grievance or absence escalation sits behind 40 holiday request emails. Without urgency classification, the time-sensitive cases are invisible.</p>
      </div>
      <div class="rounded-2xl border border-gray-200 bg-white p-6 space-y-3">
        <div class="w-10 h-10 rounded-xl bg-red-50 flex items-center justify-center">
          <svg class="w-5 h-5 text-red-400" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
        </div>
        <h3 class="font-semibold text-brand-ink">No clear ownership or resolution trail</h3>
        <p class="text-brand-ink-soft text-sm leading-relaxed">Employment tribunal evidence requires a clear log of who handled a request, what decision was made, and when. Shared inbox threads don't provide this.</p>
      </div>
    </div>
  </section>

  {# ── How It Works ──────────────────────────────────────────── #}
  <section class="bg-brand-lavender rounded-3xl px-8 py-12 sm:px-12">
    <div class="space-y-3 mb-10">
      <span class="text-xs font-semibold uppercase tracking-widest text-brand-accent">How It Works</span>
      <h2 class="text-3xl font-semibold text-brand-ink tracking-tight leading-[1.04]">Classify, route confidentially, log everything</h2>
    </div>
    <div class="grid md:grid-cols-3 gap-8">
      <div class="space-y-4">
        <div class="w-10 h-10 rounded-xl bg-brand-accent text-white flex items-center justify-center font-bold text-lg shrink-0">1</div>
        <h3 class="font-semibold text-brand-ink text-lg">Sensitivity classification</h3>
        <p class="text-brand-ink-soft text-sm leading-relaxed">InboxIQ reads each incoming HR request and classifies it: grievance, disciplinary, absence, payroll, general query. Sensitive categories are immediately separated from the general queue.</p>
      </div>
      <div class="space-y-4">
        <div class="w-10 h-10 rounded-xl bg-brand-accent text-white flex items-center justify-center font-bold text-lg shrink-0">2</div>
        <h3 class="font-semibold text-brand-ink text-lg">GDPR-aware confidential routing</h3>
        <p class="text-brand-ink-soft text-sm leading-relaxed">Sensitive requests are routed only to the designated HR Business Partner — not the shared inbox. Data minimisation is enforced automatically. Only the assigned handler sees the content.</p>
      </div>
      <div class="space-y-4">
        <div class="w-10 h-10 rounded-xl bg-brand-accent text-white flex items-center justify-center font-bold text-lg shrink-0">3</div>
        <h3 class="font-semibold text-brand-ink text-lg">Ownership and resolution log</h3>
        <p class="text-brand-ink-soft text-sm leading-relaxed">Every request gets an owner, an SLA, and a logged outcome. The complete trail — who handled it, what action was taken, and when — is available for Subject Access Requests and tribunal evidence.</p>
      </div>
    </div>
  </section>

  {# ── Outcomes ──────────────────────────────────────────────── #}
  <section>
    <div class="space-y-3 mb-10 text-center">
      <span class="text-xs font-semibold uppercase tracking-widest text-brand-accent">Outcomes</span>
      <h2 class="text-3xl font-semibold text-brand-ink tracking-tight leading-[1.04]">What HR teams report after 30 days</h2>
    </div>
    <div class="grid md:grid-cols-3 gap-6">
      <div class="rounded-2xl border border-gray-200 bg-white p-8 space-y-3 text-center">
        <div class="text-4xl font-bold text-brand-accent">55%</div>
        <p class="font-semibold text-brand-ink">Fewer misdirected sensitive requests</p>
        <p class="text-sm text-brand-ink-soft">Grievances and medical disclosures reach only the intended handler — not the whole team inbox.</p>
      </div>
      <div class="rounded-2xl border border-gray-200 bg-white p-8 space-y-3 text-center">
        <div class="text-4xl font-bold text-brand-accent">3×</div>
        <p class="font-semibold text-brand-ink">Faster response on grievance cases</p>
        <p class="text-sm text-brand-ink-soft">Urgent cases are prioritised and assigned before the routine queue is processed.</p>
      </div>
      <div class="rounded-2xl border border-gray-200 bg-white p-8 space-y-3 text-center">
        <div class="text-4xl font-bold text-brand-accent">100%</div>
        <p class="font-semibold text-brand-ink">Requests with an owner and log</p>
        <p class="text-sm text-brand-ink-soft">Every request has a named owner, SLA, and resolution record — ready for SAR responses and tribunal evidence.</p>
      </div>
    </div>
  </section>

  {# ── Compliance Callout ────────────────────────────────────── #}
  <section>
    <div class="grid md:grid-cols-2 gap-8">
      <div class="rounded-2xl border border-gray-200 bg-white p-6 space-y-5">
        <h3 class="font-semibold text-brand-ink">GDPR compliance</h3>
        <ul class="space-y-4">
          <li class="flex items-start gap-3">
            <svg class="w-5 h-5 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            <div>
              <p class="font-medium text-brand-ink text-sm">Article 5 data minimisation enforced</p>
              <p class="text-brand-ink-soft text-sm">Role-scoped routing ensures only the necessary HR partner accesses sensitive employee data — not the full team.</p>
            </div>
          </li>
          <li class="flex items-start gap-3">
            <svg class="w-5 h-5 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            <div>
              <p class="font-medium text-brand-ink text-sm">Subject Access Request support</p>
              <p class="text-brand-ink-soft text-sm">Complete access logs make SAR responses straightforward — every view of an employee's data is recorded with identity and timestamp.</p>
            </div>
          </li>
          <li class="flex items-start gap-3">
            <svg class="w-5 h-5 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            <div>
              <p class="font-medium text-brand-ink text-sm">BYOL — employee data never leaves your boundary</p>
              <p class="text-brand-ink-soft text-sm">Use your own AI key. HR request content goes directly to your provider — InboxIQ never stores email payloads.</p>
            </div>
          </li>
        </ul>
      </div>
      <div class="rounded-2xl border border-gray-200 bg-white p-6 space-y-5">
        <h3 class="font-semibold text-brand-ink">Employment law record-keeping</h3>
        <ul class="space-y-4">
          <li class="flex items-start gap-3">
            <svg class="w-5 h-5 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            <div>
              <p class="font-medium text-brand-ink text-sm">Tribunal-ready decision trail</p>
              <p class="text-brand-ink-soft text-sm">Every action on a grievance or disciplinary request is logged with the handler identity, timestamp, and outcome notes.</p>
            </div>
          </li>
          <li class="flex items-start gap-3">
            <svg class="w-5 h-5 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            <div>
              <p class="font-medium text-brand-ink text-sm">Consistent SLA enforcement</p>
              <p class="text-brand-ink-soft text-sm">Automated SLA timers mean statutory acknowledgement windows (e.g. 5-day grievance acknowledgement) are never missed.</p>
            </div>
          </li>
          <li class="flex items-start gap-3">
            <svg class="w-5 h-5 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            <div>
              <p class="font-medium text-brand-ink text-sm">Exportable case records</p>
              <p class="text-brand-ink-soft text-sm">Case history is exportable for legal review, Acas early conciliation, and employment tribunal submissions.</p>
            </div>
          </li>
        </ul>
      </div>
    </div>
  </section>

  {# ── CTA Footer ────────────────────────────────────────────── #}
  <section class="bg-brand-lavender rounded-3xl px-8 py-16 sm:px-16 text-center space-y-6">
    <h2 class="text-3xl sm:text-4xl font-semibold text-brand-ink tracking-tight leading-[1.04]">
      Give your HR team a compliant inbox — not a liability.
    </h2>
    <p class="text-brand-ink-soft leading-[1.38] max-w-xl mx-auto">
      Start free — no credit card required. Connect your HR inbox in under 10 minutes.
    </p>
    <div class="flex flex-wrap justify-center gap-4">
      <a href="{{ url_for('signup_page') }}"
         class="inline-flex items-center px-6 py-3 rounded-xl bg-brand-accent text-white font-semibold hover:bg-brand-accent-soft transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-2 focus-visible:ring-offset-brand-lavender">
        Start free trial
      </a>
      <a href="{{ url_for('contact') }}"
         class="inline-flex items-center px-6 py-3 rounded-xl border border-brand-accent/30 text-brand-accent font-semibold hover:bg-brand-accent/5 transition-colors">
        Talk to sales
      </a>
    </div>
  </section>

</div>
{% endblock %}
```

- [ ] **Step 2: Rebuild Tailwind CSS**

```bash
cd /Users/kofi/inboxiq/src && npm run build:css
```

Expected: `Done in Xs.`

- [ ] **Step 3: Visual check**

Open http://localhost:5000/use-cases/hr.

Expected:
- Light background, shared nav
- Hero: "Route every HR request to the right person before it becomes a complaint."
- Three pain point cards (sensitive requests / urgent buried / no ownership)
- Lavender "How It Works" section
- Outcome metrics: 55%, 3×, 100%
- Two compliance cards (GDPR / Employment law)
- Lavender CTA footer

- [ ] **Step 4: Commit**

```bash
cd /Users/kofi/inboxiq
git add src/templates/marketing/use_case_hr.html src/static/css/
git commit -m "feat(marketing): rewrite /use-cases/hr to enterprise standard

Replaces dark stub with GDPR/employment-law-aware HR page: sensitivity
classification messaging, confidential routing workflow, outcome metrics
(55% fewer misdirected requests, 3x faster grievance response),
GDPR Article 5 and tribunal record-keeping callout cards.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 4: Finance Approvals page

**Files:**
- Modify: `src/templates/marketing/use_case_finance.html` (full rewrite — use `Write` tool)

- [ ] **Step 1: Rewrite the file**

Replace the entire file with:

```html
{% extends "marketing/base.html" %}

{% block title %}Finance Approval Triage — AI Email Triage for Finance Teams | InboxIQ{% endblock %}
{% block meta_description %}Approve, escalate, and audit finance requests without a pile of forwarded emails. InboxIQ routes approvals to the right authoriser, enforces SOX-compliant decision trails, and eliminates missed payment deadlines.{% endblock %}
{% block canonical %}{{ url_for('use_case_finance', _external=True) }}{% endblock %}
{% block body_class %}marketing-body-light{% endblock %}

{% block content %}
<div class="space-y-24 pb-8">

  {# ── Hero ──────────────────────────────────────────────────── #}
  <header class="text-center pt-12 pb-4">
    <div class="max-w-3xl mx-auto space-y-7">
      <span class="text-xs font-semibold uppercase tracking-widest text-brand-accent">Use Case · Finance Operations</span>
      <h1 class="text-4xl sm:text-5xl font-semibold text-brand-ink tracking-tight leading-[1.04]">
        Approve, escalate, and audit finance requests<br class="hidden sm:block"> without a pile of forwarded emails.
      </h1>
      <p class="text-lg text-brand-ink-soft leading-[1.38] max-w-2xl mx-auto">
        InboxIQ identifies approval type, routes to the correct authoriser with deadline context, and logs every decision with a SOX-compliant audit trail — automatically.
      </p>
      <div class="flex flex-wrap justify-center items-center gap-4">
        <a href="{{ url_for('signup_page') }}"
           class="inline-flex items-center px-6 py-3 rounded-xl bg-brand-accent text-white font-semibold hover:bg-brand-accent-soft transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-2">
          Start free trial
        </a>
        <a href="{{ url_for('contact') }}"
           class="text-brand-accent font-semibold hover:text-brand-accent-soft transition-colors">
          Talk to sales &#8594;
        </a>
      </div>
      <div class="flex flex-wrap justify-center items-center gap-6 pt-2 text-sm text-brand-ink-soft">
        <span class="flex items-center gap-2">
          <svg class="w-4 h-4 text-brand-success shrink-0" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" /></svg>
          SOX Section 404 audit trail
        </span>
        <span class="flex items-center gap-2">
          <svg class="w-4 h-4 text-brand-success shrink-0" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" /></svg>
          Segregation of duties enforced
        </span>
        <span class="flex items-center gap-2">
          <svg class="w-4 h-4 text-brand-success shrink-0" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" /></svg>
          Zero missed payment deadlines
        </span>
      </div>
    </div>
  </header>

  {# ── Pain Points ───────────────────────────────────────────── #}
  <section>
    <div class="space-y-3 mb-10 text-center">
      <span class="text-xs font-semibold uppercase tracking-widest text-brand-accent">The Problem</span>
      <h2 class="text-3xl font-semibold text-brand-ink tracking-tight leading-[1.04]">Finance approvals get lost in shared inboxes</h2>
    </div>
    <div class="grid md:grid-cols-3 gap-6">
      <div class="rounded-2xl border border-gray-200 bg-white p-6 space-y-3">
        <div class="w-10 h-10 rounded-xl bg-red-50 flex items-center justify-center">
          <svg class="w-5 h-5 text-red-400" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
        </div>
        <h3 class="font-semibold text-brand-ink">Approval requests lost in shared inboxes</h3>
        <p class="text-brand-ink-soft text-sm leading-relaxed">Invoice approvals, purchase order sign-offs, and expense claims land in a shared finance inbox with no routing. Time-sensitive items sit unread until someone manually picks them up.</p>
      </div>
      <div class="rounded-2xl border border-gray-200 bg-white p-6 space-y-3">
        <div class="w-10 h-10 rounded-xl bg-red-50 flex items-center justify-center">
          <svg class="w-5 h-5 text-red-400" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
        </div>
        <h3 class="font-semibold text-brand-ink">No escalation path for urgent items</h3>
        <p class="text-brand-ink-soft text-sm leading-relaxed">A payment due today sits beside a routine reimbursement claim. Without urgency classification, deadlines are missed and supplier relationships suffer.</p>
      </div>
      <div class="rounded-2xl border border-gray-200 bg-white p-6 space-y-3">
        <div class="w-10 h-10 rounded-xl bg-red-50 flex items-center justify-center">
          <svg class="w-5 h-5 text-red-400" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
        </div>
        <h3 class="font-semibold text-brand-ink">SOX audits expose forwarded-email trails</h3>
        <p class="text-brand-ink-soft text-sm leading-relaxed">SOX Section 404 requires documented internal controls over financial reporting. Email forwards with "FYI — please approve" don't satisfy this.</p>
      </div>
    </div>
  </section>

  {# ── How It Works ──────────────────────────────────────────── #}
  <section class="bg-brand-lavender rounded-3xl px-8 py-12 sm:px-12">
    <div class="space-y-3 mb-10">
      <span class="text-xs font-semibold uppercase tracking-widest text-brand-accent">How It Works</span>
      <h2 class="text-3xl font-semibold text-brand-ink tracking-tight leading-[1.04]">Classify, route to the right authoriser, log the decision</h2>
    </div>
    <div class="grid md:grid-cols-3 gap-8">
      <div class="space-y-4">
        <div class="w-10 h-10 rounded-xl bg-brand-accent text-white flex items-center justify-center font-bold text-lg shrink-0">1</div>
        <h3 class="font-semibold text-brand-ink text-lg">Approval type classification</h3>
        <p class="text-brand-ink-soft text-sm leading-relaxed">InboxIQ reads each inbound finance request and classifies it: invoice approval, PO sign-off, expense claim, budget exception, compliance review. Each type follows its own routing rules.</p>
      </div>
      <div class="space-y-4">
        <div class="w-10 h-10 rounded-xl bg-brand-accent text-white flex items-center justify-center font-bold text-lg shrink-0">2</div>
        <h3 class="font-semibold text-brand-ink text-lg">Authorisation-level routing</h3>
        <p class="text-brand-ink-soft text-sm leading-relaxed">Requests above threshold are escalated to the correct authority level automatically — enforcing segregation of duties. Deadline context is attached so the approver sees due date before opening the email.</p>
      </div>
      <div class="space-y-4">
        <div class="w-10 h-10 rounded-xl bg-brand-accent text-white flex items-center justify-center font-bold text-lg shrink-0">3</div>
        <h3 class="font-semibold text-brand-ink text-lg">SOX-compliant decision log</h3>
        <p class="text-brand-ink-soft text-sm leading-relaxed">Every approval decision is logged with approver identity, timestamp, and action taken. Exportable for internal audit, external audit, and SOX Section 404 control documentation.</p>
      </div>
    </div>
  </section>

  {# ── Outcomes ──────────────────────────────────────────────── #}
  <section>
    <div class="space-y-3 mb-10 text-center">
      <span class="text-xs font-semibold uppercase tracking-widest text-brand-accent">Outcomes</span>
      <h2 class="text-3xl font-semibold text-brand-ink tracking-tight leading-[1.04]">What finance teams report after 30 days</h2>
    </div>
    <div class="grid md:grid-cols-3 gap-6">
      <div class="rounded-2xl border border-gray-200 bg-white p-8 space-y-3 text-center">
        <div class="text-4xl font-bold text-brand-accent">70%</div>
        <p class="font-semibold text-brand-ink">Reduction in approval turnaround</p>
        <p class="text-sm text-brand-ink-soft">Requests reach the right authoriser immediately — no manual routing or "did you see my email?" follow-up.</p>
      </div>
      <div class="rounded-2xl border border-gray-200 bg-white p-8 space-y-3 text-center">
        <div class="text-4xl font-bold text-brand-accent">0</div>
        <p class="font-semibold text-brand-ink">Missed payment deadlines</p>
        <p class="text-sm text-brand-ink-soft">Due-date context surfaces with each approval request — urgent items are routed and flagged before the queue review.</p>
      </div>
      <div class="rounded-2xl border border-gray-200 bg-white p-8 space-y-3 text-center">
        <div class="text-4xl font-bold text-brand-accent">100%</div>
        <p class="font-semibold text-brand-ink">Decisions with approver identity logged</p>
        <p class="text-sm text-brand-ink-soft">Every approval is timestamped and attributed — ready for internal audit and SOX compliance documentation.</p>
      </div>
    </div>
  </section>

  {# ── Compliance Callout ────────────────────────────────────── #}
  <section>
    <div class="grid md:grid-cols-2 gap-8">
      <div class="rounded-2xl border border-gray-200 bg-white p-6 space-y-5">
        <h3 class="font-semibold text-brand-ink">SOX &amp; internal controls</h3>
        <ul class="space-y-4">
          <li class="flex items-start gap-3">
            <svg class="w-5 h-5 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            <div>
              <p class="font-medium text-brand-ink text-sm">SOX Section 404 control documentation</p>
              <p class="text-brand-ink-soft text-sm">Decision logs provide auditable evidence of financial approval controls — supporting management's assertion on internal control effectiveness.</p>
            </div>
          </li>
          <li class="flex items-start gap-3">
            <svg class="w-5 h-5 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            <div>
              <p class="font-medium text-brand-ink text-sm">Segregation of duties enforcement</p>
              <p class="text-brand-ink-soft text-sm">Routing rules prevent the same person from both requesting and approving. Threshold-based escalation is automatic, not manual.</p>
            </div>
          </li>
          <li class="flex items-start gap-3">
            <svg class="w-5 h-5 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            <div>
              <p class="font-medium text-brand-ink text-sm">AP/AR audit trail</p>
              <p class="text-brand-ink-soft text-sm">Every accounts payable and receivable decision is logged — supporting both internal review and external audit requirements.</p>
            </div>
          </li>
        </ul>
      </div>
      <div class="rounded-2xl border border-gray-200 bg-white p-6 space-y-5">
        <h3 class="font-semibold text-brand-ink">Data security</h3>
        <ul class="space-y-4">
          <li class="flex items-start gap-3">
            <svg class="w-5 h-5 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            <div>
              <p class="font-medium text-brand-ink text-sm">BYOL — financial data in your boundary</p>
              <p class="text-brand-ink-soft text-sm">Connect your own OpenAI or Azure OpenAI key. Invoice and contract content goes directly to your AI provider — InboxIQ never stores email payloads.</p>
            </div>
          </li>
          <li class="flex items-start gap-3">
            <svg class="w-5 h-5 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            <div>
              <p class="font-medium text-brand-ink text-sm">Role-scoped access</p>
              <p class="text-brand-ink-soft text-sm">Only the designated approver can action a request. Access logs record every view — supporting need-to-know access principles.</p>
            </div>
          </li>
          <li class="flex items-start gap-3">
            <svg class="w-5 h-5 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            <div>
              <p class="font-medium text-brand-ink text-sm">TLS 1.3 + AES-256 at rest</p>
              <p class="text-brand-ink-soft text-sm">All routing metadata encrypted in transit and at rest. SOC 2 Type I in progress.</p>
            </div>
          </li>
        </ul>
      </div>
    </div>
  </section>

  {# ── CTA Footer ────────────────────────────────────────────── #}
  <section class="bg-brand-lavender rounded-3xl px-8 py-16 sm:px-16 text-center space-y-6">
    <h2 class="text-3xl sm:text-4xl font-semibold text-brand-ink tracking-tight leading-[1.04]">
      Close the loop on every finance approval.
    </h2>
    <p class="text-brand-ink-soft leading-[1.38] max-w-xl mx-auto">
      Start free — no credit card required. Connect your finance inbox in under 10 minutes.
    </p>
    <div class="flex flex-wrap justify-center gap-4">
      <a href="{{ url_for('signup_page') }}"
         class="inline-flex items-center px-6 py-3 rounded-xl bg-brand-accent text-white font-semibold hover:bg-brand-accent-soft transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-2 focus-visible:ring-offset-brand-lavender">
        Start free trial
      </a>
      <a href="{{ url_for('contact') }}"
         class="inline-flex items-center px-6 py-3 rounded-xl border border-brand-accent/30 text-brand-accent font-semibold hover:bg-brand-accent/5 transition-colors">
        Talk to sales
      </a>
    </div>
  </section>

</div>
{% endblock %}
```

- [ ] **Step 2: Rebuild Tailwind CSS**

```bash
cd /Users/kofi/inboxiq/src && npm run build:css
```

Expected: `Done in Xs.`

- [ ] **Step 3: Visual check**

Open http://localhost:5000/use-cases/finance.

Expected:
- Light background, shared nav
- Hero: "Approve, escalate, and audit finance requests without a pile of forwarded emails."
- Three pain point cards (lost approvals / no escalation path / SOX audit exposure)
- Lavender "How It Works" section with 3 numbered steps
- Outcome metrics: 70%, 0, 100%
- Two compliance cards (SOX & internal controls / Data security)
- Lavender CTA footer

- [ ] **Step 4: Commit**

```bash
cd /Users/kofi/inboxiq
git add src/templates/marketing/use_case_finance.html src/static/css/
git commit -m "feat(marketing): rewrite /use-cases/finance to enterprise standard

Replaces dark stub with SOX/audit-aware finance page: authorisation
routing workflow, segregation of duties enforcement messaging, outcome
metrics (70% approval turnaround reduction, 0 missed deadlines),
SOX Section 404 and AP/AR audit trail callout cards.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```
