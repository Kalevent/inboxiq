# Security & Privacy Page Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite `src/templates/security.html` to extend `marketing/base.html`, use brand tokens throughout, and implement a 7-section enterprise layout that earns trust with security-conscious buyers.

**Architecture:** Complete replacement of the existing standalone dark-themed security.html with a Jinja2 template that extends `marketing/base.html` (light theme, shared nav/footer). Five content sections are added incrementally; a CSS rebuild after each task catches any new brand token classes. No backend changes — the existing route at `src/app.py:404` (`return render_template("security.html")`) continues to work unchanged.

**Tech Stack:** Jinja2, Tailwind CSS (brand tokens), inline Heroicons SVGs, Flask dev server for visual verification.

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `src/templates/security.html` | **Full rewrite** | Complete page — all 7 sections |

No other files change. The route, base template, and CSS pipeline already exist.

---

### Task 1: Template scaffold + hero section

**Files:**
- Modify: `src/templates/security.html` (full rewrite — replace entire file)

This task writes the complete file with the template wrapper and hero section. Remaining sections are added in Tasks 2–4. Use the `Write` tool (not `Edit`) — the existing file is being replaced, not patched.

- [ ] **Step 1: Check dev server is available**

```bash
cd /Users/kofi/inboxiq && flask run --port 5000
```

Keep this running in a separate terminal for visual checks. If port 5000 is in use: `flask run --port 5001`.

- [ ] **Step 2: Write the template scaffold and hero section**

Replace `src/templates/security.html` entirely with:

```html
{% extends "marketing/base.html" %}

{% block title %}Security &amp; Privacy — InboxIQ{% endblock %}
{% block meta_description %}InboxIQ gives you three deployment models and explicit control over which AI provider processes your emails. GDPR ready. Data encrypted in transit and at rest. Bring your own LLM key.{% endblock %}
{% block body_class %}marketing-body-light{% endblock %}

{% block content %}
<div class="space-y-24 pb-8">

  {# ── Hero ──────────────────────────────────────────────────── #}
  <header class="text-center pt-12 pb-4">
    <div class="max-w-3xl mx-auto space-y-7">
      <span class="text-xs font-semibold uppercase tracking-widest text-brand-accent">Security &amp; Privacy</span>
      <h1 class="text-4xl sm:text-5xl font-semibold text-brand-ink tracking-tight leading-[1.04]">
        You decide where your data lives<br class="hidden sm:block"> and which AI touches it.
      </h1>
      <p class="text-lg text-brand-ink-soft leading-[1.38] max-w-2xl mx-auto">
        InboxIQ gives you three deployment models and explicit control over which AI provider processes your emails. No surprises. No lock-in.
      </p>
      <div class="flex flex-wrap justify-center items-center gap-4">
        <a href="{{ url_for('signup_page') }}"
           class="inline-flex items-center px-6 py-3 rounded-xl bg-brand-accent text-white font-semibold hover:bg-brand-accent-soft transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-2">
          Start free trial
        </a>
        <a href="{{ url_for('settings.settings_page', tab='ai_provider') }}"
           class="text-brand-accent font-semibold hover:text-brand-accent-soft transition-colors">
          Configure BYOL in Settings &#8594;
        </a>
      </div>
      <div class="flex flex-wrap justify-center items-center gap-6 pt-2 text-sm text-brand-ink-soft">
        <span class="flex items-center gap-2">
          <svg class="w-4 h-4 text-brand-success shrink-0" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
          </svg>
          GDPR Ready
        </span>
        <span class="flex items-center gap-2">
          <svg class="w-4 h-4 text-brand-success shrink-0" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 10-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 002.25-2.25v-6.75a2.25 2.25 0 00-2.25-2.25H6.75a2.25 2.25 0 00-2.25 2.25v6.75a2.25 2.25 0 002.25 2.25z" />
          </svg>
          Encrypted in transit &amp; at rest
        </span>
        <span class="flex items-center gap-2">
          <svg class="w-4 h-4 text-brand-success shrink-0" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" d="M15.75 5.25a3 3 0 013 3m3 0a6 6 0 01-7.029 5.912c-.563-.097-1.159.026-1.563.43L10.5 17.25H8.25v2.25H6v2.25H2.25v-2.818c0-.597.237-1.17.659-1.591l6.499-6.499c.404-.404.527-1 .43-1.563A6 6 0 1121.75 8.25z" />
          </svg>
          Use your own LLM key
        </span>
      </div>
    </div>
  </header>

  {# Deployment Models — Task 2 #}
  {# Security Posture Grid — Task 2 #}
  {# AI Sub-processors — Task 3 #}
  {# Compliance + Disclosure + Contact — Task 3 #}
  {# CTA Footer — Task 4 #}

</div>
{% endblock %}
```

- [ ] **Step 3: Rebuild Tailwind CSS**

```bash
cd /Users/kofi/inboxiq/src && npm run build:css
```

Expected: exits 0, outputs something like `Done in Xs.`

- [ ] **Step 4: Visual check**

Open http://localhost:5000/security in a browser.

Expected:
- Light background (marketing-body-light class), not dark
- Shared nav bar at top (Features, Pricing, Blog, etc.) — NOT the old inline nav
- Hero text: "You decide where your data lives and which AI touches it."
- Three trust strip items with green checkmarks below the CTAs
- Shared footer at bottom

---

### Task 2: Deployment models section + Security posture grid

**Files:**
- Modify: `src/templates/security.html` (replace the two placeholder comments with real sections)

- [ ] **Step 1: Replace the deployment models placeholder**

Find the line:
```
  {# Deployment Models — Task 2 #}
```

Replace it (and only it — leave the Security Posture placeholder below it) with the full deployment models section:

```html
  {# ── Deployment Models ─────────────────────────────────────── #}
  <section>
    <div class="space-y-3 mb-10 text-center">
      <span class="text-xs font-semibold uppercase tracking-widest text-brand-accent">Deployment Models</span>
      <h2 class="text-3xl font-semibold text-brand-ink tracking-tight leading-[1.04]">Pick the deployment that fits your security requirements</h2>
      <p class="text-brand-ink-soft leading-[1.38] max-w-2xl mx-auto">
        All plans start on Cloud. BYOL is available today. Self-hosted and Air-gapped are on the roadmap for compliance-heavy industries.
      </p>
    </div>
    <div class="grid sm:grid-cols-2 lg:grid-cols-4 gap-6">

      {# Cloud — default/muted #}
      <div class="rounded-2xl border border-gray-200 bg-white p-6 space-y-4">
        <div class="w-10 h-10 rounded-xl bg-gray-100 flex items-center justify-center">
          <svg class="w-5 h-5 text-brand-ink-soft" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" d="M2.25 15a4.5 4.5 0 004.5 4.5H18a3.75 3.75 0 001.332-7.257 3 3 0 00-3.758-3.848 5.25 5.25 0 00-10.233 2.33A4.502 4.502 0 002.25 15z" />
          </svg>
        </div>
        <h3 class="font-semibold text-brand-ink text-lg">Cloud</h3>
        <p class="text-brand-ink-soft text-sm leading-relaxed">InboxIQ manages infrastructure. Your emails are processed in our secure multi-tenant environment.</p>
        <ul class="space-y-2">
          <li class="flex items-start gap-2 text-sm text-brand-ink-soft">
            <svg class="w-4 h-4 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            TLS 1.3 in transit
          </li>
          <li class="flex items-start gap-2 text-sm text-brand-ink-soft">
            <svg class="w-4 h-4 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            AES-256 at rest
          </li>
          <li class="flex items-start gap-2 text-sm text-brand-ink-soft">
            <svg class="w-4 h-4 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            EU/US region selection
          </li>
          <li class="flex items-start gap-2 text-sm text-brand-ink-soft">
            <svg class="w-4 h-4 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            SOC 2 (in progress)
          </li>
        </ul>
      </div>

      {# BYOL — featured / recommended #}
      <div class="rounded-2xl border-2 border-brand-accent bg-brand-lavender p-6 space-y-4 relative">
        <span class="absolute -top-3 left-1/2 -translate-x-1/2 bg-brand-accent text-white text-xs font-semibold px-3 py-1 rounded-full whitespace-nowrap">Most Popular</span>
        <div class="w-10 h-10 rounded-xl bg-brand-accent/10 flex items-center justify-center">
          <svg class="w-5 h-5 text-brand-accent" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" d="M15.75 5.25a3 3 0 013 3m3 0a6 6 0 01-7.029 5.912c-.563-.097-1.159.026-1.563.43L10.5 17.25H8.25v2.25H6v2.25H2.25v-2.818c0-.597.237-1.17.659-1.591l6.499-6.499c.404-.404.527-1 .43-1.563A6 6 0 1121.75 8.25z" />
          </svg>
        </div>
        <h3 class="font-semibold text-brand-ink text-lg">BYOL — Bring Your Own LLM</h3>
        <p class="text-brand-ink-soft text-sm leading-relaxed">Connect your own OpenAI, Anthropic, or Azure OpenAI key. AI calls go from your browser to your provider — we never see the payload.</p>
        <ul class="space-y-2">
          <li class="flex items-start gap-2 text-sm text-brand-ink-soft">
            <svg class="w-4 h-4 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            Zero data retention at InboxIQ for AI payloads
          </li>
          <li class="flex items-start gap-2 text-sm text-brand-ink-soft">
            <svg class="w-4 h-4 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            Works with any OpenAI-compatible endpoint
          </li>
          <li class="flex items-start gap-2 text-sm text-brand-ink-soft">
            <svg class="w-4 h-4 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            Rotate or revoke keys at any time
          </li>
          <li class="flex items-start gap-2 text-sm text-brand-ink-soft">
            <svg class="w-4 h-4 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            Per-inbox key isolation
          </li>
        </ul>
        <a href="{{ url_for('settings.settings_page', tab='ai_provider') }}"
           class="inline-flex items-center text-sm font-semibold text-brand-accent hover:text-brand-accent-soft transition-colors">
          Configure in Settings &#8594;
        </a>
      </div>

      {# Self-hosted — coming soon, dimmed #}
      <div class="rounded-2xl border border-gray-200 bg-white p-6 space-y-4 opacity-60">
        <div class="flex items-center justify-between">
          <div class="w-10 h-10 rounded-xl bg-gray-100 flex items-center justify-center">
            <svg class="w-5 h-5 text-brand-ink-soft" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" d="M5.25 14.25h13.5m-13.5 0a3 3 0 01-3-3m3 3a3 3 0 100 6h13.5a3 3 0 100-6m-16.5-3a3 3 0 013-3h13.5a3 3 0 013 3m-19.5 0a4.5 4.5 0 01.9-2.7L5.737 5.1a3.375 3.375 0 012.7-1.35h7.126c1.062 0 2.062.5 2.7 1.35l2.587 3.45a4.5 4.5 0 01.9 2.7m0 0a3 3 0 01-3 3m0 3h.008v.008h-.008v-.008zm0-6h.008v.008h-.008v-.008zm-3 6h.008v.008h-.008v-.008zm0-6h.008v.008h-.008v-.008z" />
            </svg>
          </div>
          <span class="text-xs font-semibold bg-gray-100 text-gray-500 px-2 py-1 rounded-full">Coming soon</span>
        </div>
        <h3 class="font-semibold text-brand-ink text-lg">Self-hosted</h3>
        <p class="text-brand-ink-soft text-sm leading-relaxed">Deploy InboxIQ inside your own VPC or private cloud. Full control over data residency and network egress.</p>
        <ul class="space-y-2">
          <li class="flex items-start gap-2 text-sm text-brand-ink-soft">
            <svg class="w-4 h-4 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            Docker + Kubernetes manifests
          </li>
          <li class="flex items-start gap-2 text-sm text-brand-ink-soft">
            <svg class="w-4 h-4 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            Bring your own Postgres &amp; Redis
          </li>
          <li class="flex items-start gap-2 text-sm text-brand-ink-soft">
            <svg class="w-4 h-4 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            No outbound calls except to configured AI provider
          </li>
        </ul>
      </div>

      {# Air-gapped — coming soon, dimmed #}
      <div class="rounded-2xl border border-gray-200 bg-white p-6 space-y-4 opacity-60">
        <div class="flex items-center justify-between">
          <div class="w-10 h-10 rounded-xl bg-gray-100 flex items-center justify-center">
            <svg class="w-5 h-5 text-brand-ink-soft" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
            </svg>
          </div>
          <span class="text-xs font-semibold bg-gray-100 text-gray-500 px-2 py-1 rounded-full">Coming soon</span>
        </div>
        <h3 class="font-semibold text-brand-ink text-lg">Air-gapped</h3>
        <p class="text-brand-ink-soft text-sm leading-relaxed">Fully isolated deployment with no internet connectivity. Purpose-built for regulated industries and government.</p>
        <ul class="space-y-2">
          <li class="flex items-start gap-2 text-sm text-brand-ink-soft">
            <svg class="w-4 h-4 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            Offline AI model support (Ollama compatible)
          </li>
          <li class="flex items-start gap-2 text-sm text-brand-ink-soft">
            <svg class="w-4 h-4 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            Signed artefact bundles
          </li>
          <li class="flex items-start gap-2 text-sm text-brand-ink-soft">
            <svg class="w-4 h-4 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            Audit-ready installation guide
          </li>
        </ul>
      </div>

    </div>
  </section>
```

- [ ] **Step 2: Replace the Security Posture placeholder**

Find the line:
```
  {# Security Posture Grid — Task 2 #}
```

Replace it with:

```html
  {# ── Security Posture Grid ─────────────────────────────────── #}
  <section>
    <div class="space-y-3 mb-10">
      <span class="text-xs font-semibold uppercase tracking-widest text-brand-accent">Security Posture</span>
      <h2 class="text-3xl font-semibold text-brand-ink tracking-tight leading-[1.04]">Built for teams that take security seriously</h2>
    </div>
    <div class="grid md:grid-cols-2 gap-12">

      {# Infrastructure #}
      <div>
        <h3 class="font-semibold text-brand-ink mb-5">Infrastructure</h3>
        <ul class="space-y-5">
          <li class="flex items-start gap-3">
            <svg class="w-5 h-5 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            <div>
              <p class="font-medium text-brand-ink text-sm">Encryption in transit (TLS 1.3)</p>
              <p class="text-brand-ink-soft text-sm">All data in flight is encrypted using TLS 1.3.</p>
            </div>
          </li>
          <li class="flex items-start gap-3">
            <svg class="w-5 h-5 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            <div>
              <p class="font-medium text-brand-ink text-sm">Encryption at rest (AES-256)</p>
              <p class="text-brand-ink-soft text-sm">Database and object storage encrypted at rest with AES-256.</p>
            </div>
          </li>
          <li class="flex items-start gap-3">
            <svg class="w-5 h-5 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            <div>
              <p class="font-medium text-brand-ink text-sm">Isolated file serving</p>
              <p class="text-brand-ink-soft text-sm">User uploads served from files.kalevent.com — isolated from the main application domain.</p>
            </div>
          </li>
        </ul>
      </div>

      {# Access Control #}
      <div>
        <h3 class="font-semibold text-brand-ink mb-5">Access Control</h3>
        <ul class="space-y-5">
          <li class="flex items-start gap-3">
            <svg class="w-5 h-5 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            <div>
              <p class="font-medium text-brand-ink text-sm">JWT-based authentication</p>
              <p class="text-brand-ink-soft text-sm">Short-lived signed tokens. No session cookies stored on the server.</p>
            </div>
          </li>
          <li class="flex items-start gap-3">
            <svg class="w-5 h-5 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            <div>
              <p class="font-medium text-brand-ink text-sm">Passkey / WebAuthn support</p>
              <p class="text-brand-ink-soft text-sm">Phishing-resistant hardware-bound login via FIDO2 passkeys.</p>
            </div>
          </li>
          <li class="flex items-start gap-3">
            <svg class="w-5 h-5 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            <div>
              <p class="font-medium text-brand-ink text-sm">Role-scoped API credentials</p>
              <p class="text-brand-ink-soft text-sm">Developer API keys are scoped to specific permissions (intake:write, tickets:read).</p>
            </div>
          </li>
        </ul>
      </div>

      {# Application Security #}
      <div>
        <h3 class="font-semibold text-brand-ink mb-5">Application Security</h3>
        <ul class="space-y-5">
          <li class="flex items-start gap-3">
            <svg class="w-5 h-5 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            <div>
              <p class="font-medium text-brand-ink text-sm">Dependency scanning</p>
              <p class="text-brand-ink-soft text-sm">Dependabot monitors all packages for known CVEs.</p>
            </div>
          </li>
          <li class="flex items-start gap-3">
            <svg class="w-5 h-5 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            <div>
              <p class="font-medium text-brand-ink text-sm">Secret scanning</p>
              <p class="text-brand-ink-soft text-sm">GitHub Advanced Security scans every commit for accidentally committed credentials.</p>
            </div>
          </li>
          <li class="flex items-start gap-3">
            <svg class="w-5 h-5 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            <div>
              <p class="font-medium text-brand-ink text-sm">Container image scanning</p>
              <p class="text-brand-ink-soft text-sm">Every container build is scanned for OS-level CVEs before deployment.</p>
            </div>
          </li>
          <li class="flex items-start gap-3">
            <svg class="w-5 h-5 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            <div>
              <p class="font-medium text-brand-ink text-sm">SAST / code analysis</p>
              <p class="text-brand-ink-soft text-sm">Static analysis runs on every pull request.</p>
            </div>
          </li>
        </ul>
      </div>

      {# Compliance & Observability #}
      <div>
        <h3 class="font-semibold text-brand-ink mb-5">Compliance &amp; Observability</h3>
        <ul class="space-y-5">
          <li class="flex items-start gap-3">
            <svg class="w-5 h-5 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            <div>
              <p class="font-medium text-brand-ink text-sm">Audit log</p>
              <p class="text-brand-ink-soft text-sm">Every authenticated action is logged with user, timestamp, and IP. Visible to account owners in Settings.</p>
            </div>
          </li>
          <li class="flex items-start gap-3">
            <svg class="w-5 h-5 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            <div>
              <p class="font-medium text-brand-ink text-sm">Rate limiting on all public endpoints</p>
              <p class="text-brand-ink-soft text-sm">Flask-Limiter enforces per-IP rate limits on every public-facing route.</p>
            </div>
          </li>
          <li class="flex items-start gap-3">
            <svg class="w-5 h-5 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            <div>
              <p class="font-medium text-brand-ink text-sm">GDPR-ready data controls</p>
              <p class="text-brand-ink-soft text-sm">Account deletion, data export, and right-to-erasure requests supported.</p>
            </div>
          </li>
          <li class="flex items-start gap-3">
            <svg class="w-5 h-5 text-brand-success shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            <div>
              <p class="font-medium text-brand-ink text-sm">Vulnerability disclosure programme</p>
              <p class="text-brand-ink-soft text-sm">Responsible disclosure policy with 24-hour acknowledgement SLA.</p>
            </div>
          </li>
        </ul>
      </div>

    </div>
  </section>
```

- [ ] **Step 3: Rebuild Tailwind CSS**

```bash
cd /Users/kofi/inboxiq/src && npm run build:css
```

Expected: exits 0.

- [ ] **Step 4: Visual check**

Open http://localhost:5000/security (hard-refresh if needed).

Expected:
- Deployment Models heading + 4 cards in a row on large screens
- BYOL card has brand-lavender background, brand-accent border, and "Most Popular" badge at top
- Self-hosted and Air-gapped cards are visibly dimmed with "Coming soon" pill
- Security Posture section below, 2-column layout with 4 groups

---

### Task 3: AI transparency section + Compliance/Disclosure/Contact row

**Files:**
- Modify: `src/templates/security.html`

- [ ] **Step 1: Replace the AI Sub-processors placeholder**

Find the line:
```
  {# AI Sub-processors — Task 3 #}
```

Replace it with:

```html
  {# ── AI Sub-processors ─────────────────────────────────────── #}
  <section class="bg-brand-lavender rounded-3xl px-8 py-12 sm:px-12">
    <div class="space-y-3 mb-10">
      <span class="text-xs font-semibold uppercase tracking-widest text-brand-accent">AI Sub-processors</span>
      <h2 class="text-3xl font-semibold text-brand-ink tracking-tight leading-[1.04]">We tell you exactly which AI sees your emails</h2>
    </div>
    <div class="grid lg:grid-cols-2 gap-12 items-start">

      {# Sub-processor table #}
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b border-brand-accent/20">
              <th class="text-left pb-3 font-semibold text-brand-ink">Provider</th>
              <th class="text-left pb-3 font-semibold text-brand-ink">Used for</th>
              <th class="text-left pb-3 font-semibold text-brand-ink">Data retention</th>
              <th class="text-left pb-3 font-semibold text-brand-ink">Opt-out</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-brand-accent/10">
            <tr>
              <td class="py-4 pr-4 text-brand-ink font-medium">OpenAI (default)</td>
              <td class="py-4 pr-4 text-brand-ink-soft">Email triage, draft replies</td>
              <td class="py-4 pr-4 text-brand-ink-soft">0 days (Zero Data Retention policy)</td>
              <td class="py-4 text-brand-ink-soft">Use BYOL to replace</td>
            </tr>
            <tr>
              <td class="py-4 pr-4 text-brand-ink font-medium">Your provider (BYOL)</td>
              <td class="py-4 pr-4 text-brand-ink-soft">All AI features</td>
              <td class="py-4 pr-4 text-brand-ink-soft">Your own policy</td>
              <td class="py-4 text-brand-ink-soft">N/A — you control it</td>
            </tr>
          </tbody>
        </table>
      </div>

      {# OpenAI ZDR callout #}
      <div class="bg-white rounded-2xl p-8 space-y-4">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-xl bg-brand-accent/10 flex items-center justify-center shrink-0">
            <svg class="w-5 h-5 text-brand-accent" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
            </svg>
          </div>
          <h3 class="font-semibold text-brand-ink">OpenAI Zero Data Retention</h3>
        </div>
        <p class="text-brand-ink-soft text-sm leading-relaxed">
          InboxIQ calls OpenAI's API with ZDR enabled. OpenAI does not use your emails to train models and retains no data after responding.
        </p>
        <a href="https://platform.openai.com/docs/models/how-we-use-your-data" target="_blank" rel="noopener noreferrer"
           class="inline-flex items-center text-sm font-semibold text-brand-accent hover:text-brand-accent-soft transition-colors">
          OpenAI ZDR policy &#8594;
        </a>
      </div>

    </div>
  </section>
```

- [ ] **Step 2: Replace the Compliance/Disclosure/Contact placeholder**

Find the line:
```
  {# Compliance + Disclosure + Contact — Task 3 #}
```

Replace it with:

```html
  {# ── Compliance + Disclosure + Contact ────────────────────── #}
  <section>
    <div class="grid md:grid-cols-3 gap-8">

      {# Compliance Roadmap #}
      <div class="rounded-2xl border border-gray-200 bg-white p-6 space-y-5">
        <h3 class="font-semibold text-brand-ink">Compliance Roadmap</h3>
        <ul class="space-y-3">
          <li class="flex items-center justify-between">
            <span class="text-sm text-brand-ink-soft">SOC 2 Type I</span>
            <span class="text-xs font-semibold bg-yellow-50 text-yellow-700 px-2 py-0.5 rounded-full">In progress</span>
          </li>
          <li class="flex items-center justify-between">
            <span class="text-sm text-brand-ink-soft">GDPR</span>
            <span class="text-xs font-semibold bg-green-50 text-green-700 px-2 py-0.5 rounded-full">Ready</span>
          </li>
          <li class="flex items-center justify-between">
            <span class="text-sm text-brand-ink-soft">HIPAA</span>
            <span class="text-xs font-semibold bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">Planned</span>
          </li>
          <li class="flex items-center justify-between">
            <span class="text-sm text-brand-ink-soft">ISO 27001</span>
            <span class="text-xs font-semibold bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">Planned</span>
          </li>
        </ul>
      </div>

      {# Vulnerability Disclosure #}
      <div class="rounded-2xl border border-gray-200 bg-white p-6 space-y-4">
        <h3 class="font-semibold text-brand-ink">Vulnerability Disclosure</h3>
        <p class="text-sm text-brand-ink-soft leading-relaxed">
          We operate a responsible disclosure programme. If you discover a vulnerability, please report it to
          <a href="mailto:security@kalevent.com" class="text-brand-accent hover:text-brand-accent-soft">security@kalevent.com</a>.
          We aim to acknowledge within 24 hours and resolve critical issues within 72 hours.
        </p>
        <a href="mailto:security@kalevent.com"
           class="inline-flex items-center text-sm font-semibold text-brand-accent hover:text-brand-accent-soft transition-colors">
          Report a vulnerability &#8594;
        </a>
      </div>

      {# Security Contact #}
      <div class="rounded-2xl border border-gray-200 bg-white p-6 space-y-4">
        <h3 class="font-semibold text-brand-ink">Security Team</h3>
        <p class="text-sm text-brand-ink-soft leading-relaxed">
          Questions about our security posture, penetration test results, or compliance documentation? Reach our security team directly.
        </p>
        <a href="mailto:security@kalevent.com"
           class="inline-flex items-center text-sm font-semibold text-brand-accent hover:text-brand-accent-soft transition-colors">
          security@kalevent.com &#8594;
        </a>
      </div>

    </div>
  </section>
```

- [ ] **Step 3: Rebuild Tailwind CSS**

```bash
cd /Users/kofi/inboxiq/src && npm run build:css
```

Expected: exits 0.

- [ ] **Step 4: Visual check**

Open http://localhost:5000/security.

Expected:
- AI Sub-processors section on a `bg-brand-lavender` background with rounded corners
- Table with two rows (OpenAI default, Your provider BYOL)
- White callout box on the right with the ZDR explanation
- Compliance Roadmap card showing GDPR as green "Ready" and SOC 2 as yellow "In progress"

---

### Task 4: CTA footer block + final CSS build + commit

**Files:**
- Modify: `src/templates/security.html`

- [ ] **Step 1: Replace the CTA Footer placeholder**

Find the line:
```
  {# CTA Footer — Task 4 #}
```

Replace it with:

```html
  {# ── CTA Footer ────────────────────────────────────────────── #}
  <section class="bg-brand-lavender rounded-3xl px-8 py-16 sm:px-16 text-center space-y-6">
    <h2 class="text-3xl sm:text-4xl font-semibold text-brand-ink tracking-tight leading-[1.04]">
      Ready to take control of your inbox data?
    </h2>
    <p class="text-brand-ink-soft leading-[1.38] max-w-xl mx-auto">
      Start free — no credit card required. Configure BYOL in under 5 minutes.
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
```

- [ ] **Step 2: Final Tailwind CSS rebuild**

```bash
cd /Users/kofi/inboxiq/src && npm run build:css
```

Expected: exits 0.

- [ ] **Step 3: Full page visual check**

Open http://localhost:5000/security (hard-refresh with Cmd+Shift+R / Ctrl+Shift+R).

Walk down the full page and confirm each section is present:

1. Hero — eyebrow + H1 + subtext + two CTAs + three trust strip items
2. Deployment Models — 4-column grid, BYOL featured with lavender background
3. Security Posture — 2-column, 4 groups (Infrastructure / Access Control / App Security / Compliance)
4. AI Sub-processors — lavender background, table + ZDR callout card
5. Compliance Roadmap + Disclosure + Contact — 3-column card row
6. CTA Footer — lavender background, "Ready to take control of your inbox data?"

Also confirm:
- The page uses the shared nav from marketing/base.html (no old inline nav)
- The page uses the shared footer from marketing/base.html (no old inline footer)
- No raw hex colours visible in page source (no `#0A0A14`, `#5B5BD6`)

- [ ] **Step 4: Commit**

```bash
cd /Users/kofi/inboxiq
git add src/templates/security.html src/static/css/
git commit -m "feat(marketing): redesign /security page to enterprise standard

Replaces standalone dark template with light-theme marketing/base.html
layout. Adds deployment model cards (Cloud/BYOL/Self-hosted/Air-gapped),
security posture grid, AI sub-processor transparency section, compliance
roadmap, and CTA footer — all using brand tokens.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

Expected: commit succeeds, shows `security.html` and any CSS file in the diff.
