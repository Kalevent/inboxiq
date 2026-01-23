InboxIQ B2B lead-gen (to sell InboxIQ) + scoring rubric (UK, 50–500 FTE, RevOps/Demand Gen)

Use the existing Jinja email template (`src/templates/email/newsletter.html.j2` / `app/templates/email/newsletter.html.j2`). A lightweight Loom/resource card is now supported via the `resource` object to keep the email text-first and deliverability-safe.

Newsletter draft payload (example)
- Endpoint: `/publishing/newsletter/draft` (sync or Celery).
- Body to render the template:
  - `preheader`: "How UK RevOps teams keep SDR queues clean with InboxIQ"
  - `hero`: `{ kicker: "Outbound hygiene", headline: "InboxIQ routes only live buyers to your SDRs", cta_text: "See InboxIQ live", cta_url: "<cal/loom/demo>" }`
  - `resource`: `{ kicker: "2-min loom", title: "InboxIQ routing + scoring flow", summary: "See InboxIQ enrich, score, and route inbound → SDR in under 2:30.", cta_text: "Watch the Loom", url: "<loom_link>" }`
  - `sections` (HTML allowed):
    1) Title: "ICP + triggers we’re targeting"  
       HTML: bullet the ICP—UK HQ or GTM, 50–500 FTE (focus 50–300), roles: VP/Director RevOps, VP/Director Demand Gen/Marketing Ops, Head of Sales Ops/Enablement. Triggers: hiring SDR/BDR/RevOps, funding in last 12 months (Seed–B/C), new product launch/PR, tech stack SFDC/HubSpot + Outreach/Salesloft + Gong/Chorus.
    2) Title: "Outbound that doesn’t burn the domain"  
       HTML: recap the 4-step sequence, small A/B batches (20–30), pause variants <30% open or <1% reply after 50 sends, cap daily cold volume and ramp subdomain.
    3) Title: "Warm first, cold second"  
       HTML: prioritize site traffic/webinar signups/partners before cold; run a single-step warm email + retargeting before sequences.
    4) Title: "Newsletter-as-nurture for InboxIQ"  
       HTML: monthly playbook with one InboxIQ insight + one CTA to see the product; segment high fit/no intent into this stream.
  - `cta_block`: `{ headline: "Ready to try InboxIQ?", cta_text: "Book a 10-min demo", cta_url: "<cal_link>" }`
  - `footer`: current values (company/address/unsubscribe/legal).

Boolean filters for sourcing
- Titles: ("VP Revenue Operations" OR "Director Revenue Operations" OR "VP RevOps" OR "Head of RevOps" OR "Head of Sales Operations" OR "Director Sales Operations" OR "VP Demand Generation" OR "Director Demand Generation" OR "Marketing Operations Director" OR "Sales Enablement Director")
- Headcount: 50–500 (start with 50–300).
- Geo: United Kingdom HQ or GTM.
- Seniority/Function: Director/VP/Head; Operations/Sales/Marketing/BD.
- Industry: B2B SaaS/Software/IT Services; exclude staffing/agency.
- Stack keywords: ("Salesforce" OR "HubSpot") AND ("Outreach" OR "Salesloft") AND ("Gong" OR "Chorus").
- Triggers: job posts with “SDR” OR “BDR” OR “Revenue Operations”; funding in last 12 months; PR/product launch in last 90 days.

Scoring rubric (use for routing + newsletter segmentation)
- Fit score (0–10):
  - +4 title/role match (from list above)
  - +2 company size 50–500
  - +2 stack match (SFDC/HubSpot + Outreach/Salesloft; +1 extra if Gong/Chorus present)
  - +1 UK HQ or GTM team
  - +1 industry in B2B SaaS/Software/IT Services
- Intent score (0–12):
  - +1 open
  - +3 click
  - +10 reply (positive or neutral)
  - +12 meeting booked (hard-cap intent at 12 to avoid runaway scores)
  - -5 hard bounce/complaint (and suppress)
- Routing thresholds:
  - High-priority → human follow-up: fit ≥8 AND intent ≥6, or any reply/meeting.
  - Nurture cadence → slower sequence + newsletter: fit ≥6 AND intent 1–5.
  - Newsletter-only: fit <6 OR no engagement after 3 touches.

Measurement + pruning
- Track per-segment: open, reply, positive reply/meeting rate, CAC per booked call, unsubscribe/complaint rate.
- Kill/prune monthly: remove segments <30% open or <1% reply after 50 sends; reinvest into top-performing titles/industries/stacks.
- Domain health: cap daily cold volume; ramp new subdomains; keep a plain-text-heavy template (one CTA, single Loom link).

Lead Sourcing agent setup (multi-MCP, keeps triage intact)
- MCP servers to register (via `/agents/mcp/servers`), labels:
  - `search-mcp`: `["python", "-m", "src.mcp.search_mcp"]`
  - `sql-mcp`: `["python", "-m", "src.mcp.sql_mcp"]`
  - `http-mcp`: `["python", "-m", "src.mcp.http_mcp"]`
- Create agent:
  ```json
  {
    "name": "Lead Sourcing Agent",
    "description": "Searches intent signals, fetches pages, upserts leads/scores",
    "mcp_servers": [
      {"label": "search-mcp", "command": ["python", "-m", "src.mcp.search_mcp"]},
      {"label": "sql-mcp", "command": ["python", "-m", "src.mcp.sql_mcp"]},
      {"label": "http-mcp", "command": ["python", "-m", "src.mcp.http_mcp"]}
    ],
    "capabilities": ["search", "sql", "http"],
    "triggers": [{"type": "manual"}]
  }
  ```
- Invoke examples (set `mcp_server_label` to disambiguate when multiple servers are configured):
  - Search signals: `{"tool": "search", "arguments": {"query": "UK SaaS hiring SDR BDR"}, "mcp_server_label": "search-mcp"}`
  - Fetch a job page: `{"tool": "http_request", "arguments": {"url": "<job_url>"}, "mcp_server_label": "http-mcp"}`
  - Upsert lead (requires `requires_human=true` to avoid unsafe writes):
    ```json
    {
      "tool": "execute",
      "arguments": {
        "sql": "insert into leads(email, company, title, fit_score, intent_score) values ('a@b.com','Acme','Head of RevOps',8,6)",
        "requires_human": true
      },
      "mcp_server_label": "sql-mcp"
    }
    ```
- Triage unaffected: single-server agents (e.g., email triage) still default to their lone MCP server. Multi-server agents must send `mcp_server_label`; otherwise, the API returns a clear 400 to prevent hitting the wrong server.

Lead enrichment tools (automate extraction + email verification)
- New MCP server: `lead-enrichment-mcp` (`python -m src.mcp.lead_enrichment_mcp`) exposing:
  - `extract_contacts(text, domain_hint)`: pull name/title/email from HTML/text; synthesize `first.last@domain` if no email and domain_hint provided.
  - `verify_email(email, from_address)`: syntax + MX + lightweight SMTP RCPT check (best effort).
  - `send_probe_email(to_email, from_email, subject, body)`: send a lightweight probe email via PROBE_SMTP_* (or fallback SMTP_*) to confirm real delivery.
- Register it in `mcp_servers` and select with `mcp_server_label: "lead-enrichment-mcp"` during invoke.
- Suggested autonomous flow per lead:
  1) `search` (search-mcp) → collect URLs.
  2) `http_request` (http-mcp) to fetch a URL’s body.
  3) `extract_contacts` (lead-enrichment-mcp) on the body; pass domain_hint from the URL host.
  4) For each candidate email, `verify_email` (lead-enrichment-mcp); keep only `valid: true`.
  4b) Optional: `send_probe_email` to high-fit candidates from a probe subdomain; mark invalid if SMTP rejects or bounces are observed.
  5) Upsert to `leads` via `execute` (sql-mcp) with `requires_human: true` to safeguard writes.
- Human review only when the newsletter draft is ready to send; the sourcing/verification loop runs via the agent using the new tools.
