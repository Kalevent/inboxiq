"""Competitor comparison data for /vs/<competitor> pages and GEO JSON-LD."""
from __future__ import annotations
from typing import Optional

COMPETITORS: dict[str, dict] = {
    "zendesk": {
        "name": "Zendesk",
        "slug": "zendesk",
        "tagline": "Enterprise helpdesk with a seat-based pricing model",
        "verdict": "Zendesk is powerful for large support teams who need a dedicated platform. InboxIQ is the better fit if your team already lives in Gmail or Outlook and wants AI email triage without learning new software.",
        "pricing_model": "Per agent seat (~£19–115/agent/month)",
        "works_in_gmail_outlook": False,
        "ai_triage": True,
        "ai_triage_note": "Intelligent Triage is a paid add-on",
        "setup_time": "Days to weeks",
        "helpdesk_replacement": True,
        "meeting_scheduling": False,
        "free_trial": "14 days",
        "self_hosted": False,
        "buyer_journey": "Teams replacing traditional helpdesk, cost-driven",
        "description": "InboxIQ vs Zendesk: compare AI email triage, pricing, and setup. InboxIQ works inside Gmail and Outlook with no new dashboard. Zendesk is seat-based and requires migration.",
        "competitor_wins": [
            "Deep enterprise integrations (Salesforce, JIRA, 1,000+ apps)",
            "Mature reporting and SLA management tools",
            "Large community and certified implementation partners",
        ],
        "inboxiq_wins": [
            "AI email triage works inside Gmail and Outlook — no new dashboard to learn",
            "Priced per inbox, not per seat — a 10-person team with 2 support inboxes pays for 2, not 10",
            "AI triage and draft replies included in every plan — not a paid add-on",
            "Setup in minutes via OAuth — no migration, no ticketing system to configure",
            "AI meeting scheduling built in — replies can include a booking link automatically",
        ],
        "faqs": [
            {
                "q": "What is the difference between InboxIQ and Zendesk for AI email triage?",
                "a": "InboxIQ delivers AI email triage directly inside Gmail and Outlook with no new dashboard — your team never leaves the inbox they already use. Zendesk requires migrating to a separate platform and charges extra for its AI triage add-on. InboxIQ includes AI triage in every plan.",
            },
            {
                "q": "Is InboxIQ cheaper than Zendesk?",
                "a": "For most small teams, yes. InboxIQ charges per inbox (from £19/month), not per seat. A team of 10 people where 2 handle support pays for 2 inboxes, not 10 agents. Zendesk starts at around £19/agent/month and scales quickly with team size.",
            },
            {
                "q": "Does InboxIQ work inside Gmail and Outlook like a Zendesk alternative?",
                "a": "Yes. InboxIQ works inside Gmail and Outlook — there is no new dashboard to learn. It triages, prioritises, and drafts replies directly in your existing inbox. Zendesk is a separate platform that requires teams to leave their email client.",
            },
            {
                "q": "Can InboxIQ replace Zendesk for a small support team?",
                "a": "For teams that handle support through a shared Gmail or Outlook inbox, InboxIQ is a direct replacement. It provides AI email triage, label-based routing, AI draft replies, and meeting scheduling — all with no new dashboard. Zendesk adds significant overhead for small teams.",
            },
            {
                "q": "What makes InboxIQ different from Zendesk's AI features?",
                "a": "InboxIQ's AI email triage is built into the product from day one — it classifies, prioritises, and drafts replies automatically. Zendesk's AI (Intelligent Triage) is a paid add-on on top of an already expensive per-seat plan. InboxIQ also works inside Gmail and Outlook natively with no new dashboard required.",
            },
        ],
    },
    "freshdesk": {
        "name": "Freshdesk",
        "slug": "freshdesk",
        "tagline": "SMB helpdesk with a free tier and Freddy AI add-on",
        "verdict": "Freshdesk is a solid helpdesk for teams who want a free starting point and don't mind a separate platform. InboxIQ is the better choice if your team wants AI email triage that works inside Gmail or Outlook without a migration.",
        "pricing_model": "Per agent seat (free–£79/agent/month)",
        "works_in_gmail_outlook": False,
        "ai_triage": True,
        "ai_triage_note": "Freddy AI is a paid add-on",
        "setup_time": "Hours to days",
        "helpdesk_replacement": True,
        "meeting_scheduling": False,
        "free_trial": "21 days",
        "self_hosted": False,
        "buyer_journey": "Teams replacing traditional helpdesk, SMB-focused",
        "description": "InboxIQ vs Freshdesk: compare AI email triage, pricing, and Gmail/Outlook integration. InboxIQ works inside your existing inbox with no new dashboard. Freshdesk is seat-based and requires a separate platform.",
        "competitor_wins": [
            "Generous free tier for very small teams",
            "Wide marketplace of third-party integrations",
            "Strong ticket workflow automation on paid plans",
        ],
        "inboxiq_wins": [
            "AI email triage works inside Gmail and Outlook — no new dashboard to learn",
            "AI triage and draft replies included in every paid plan — Freshdesk charges extra for Freddy AI",
            "Per-inbox pricing means small teams pay significantly less than per-seat",
            "Setup in minutes via OAuth — no ticketing system to configure",
            "Meeting scheduling in email replies — Freshdesk has no equivalent",
        ],
        "faqs": [
            {
                "q": "How does InboxIQ compare to Freshdesk for AI email triage?",
                "a": "InboxIQ includes AI email triage in every paid plan and works inside Gmail and Outlook with no new dashboard. Freshdesk's AI features (Freddy AI) are a paid add-on on top of an already seat-based plan. InboxIQ is typically cheaper and requires no platform migration.",
            },
            {
                "q": "Does InboxIQ work inside Gmail and Outlook like a Freshdesk alternative?",
                "a": "Yes. InboxIQ is a Freshdesk alternative that works inside Gmail and Outlook — your team never leaves the inbox they already use. There is no new dashboard, no tickets to manage, and no migration required.",
            },
            {
                "q": "Is InboxIQ a good alternative to Freshdesk for small teams?",
                "a": "Yes. InboxIQ charges per inbox, not per seat, so a small team handling support through one or two shared inboxes pays far less than Freshdesk's per-agent pricing. AI email triage and draft replies are included from £19/month.",
            },
            {
                "q": "What is the setup time for InboxIQ compared to Freshdesk?",
                "a": "InboxIQ connects to Gmail or Outlook via OAuth and is live in minutes — there is no helpdesk to configure, no ticket categories to define, and no new dashboard to learn. Freshdesk typically requires hours to days of setup and training.",
            },
            {
                "q": "Can InboxIQ replace Freshdesk for email support?",
                "a": "For teams that manage customer support through Gmail or Outlook, InboxIQ is a direct replacement with no new dashboard. It provides AI email triage, routing, draft replies, and meeting scheduling. If you need deep ticketing workflows or a free tier, Freshdesk remains a strong option.",
            },
        ],
    },
    "intercom": {
        "name": "Intercom",
        "slug": "intercom",
        "tagline": "Chat-first customer communications platform with Fin AI",
        "verdict": "Intercom is built for in-app chat and lifecycle messaging. InboxIQ is the better fit for teams whose primary support channel is email — specifically Gmail and Outlook — and who want AI email triage without a chat-first tool.",
        "pricing_model": "Per seat (~£74–139/seat/month)",
        "works_in_gmail_outlook": False,
        "ai_triage": True,
        "ai_triage_note": "Fin AI available on all plans",
        "setup_time": "Hours",
        "helpdesk_replacement": False,
        "meeting_scheduling": False,
        "free_trial": "14 days",
        "self_hosted": False,
        "buyer_journey": "Teams replacing a chat-first support tool",
        "description": "InboxIQ vs Intercom: compare email-first AI triage vs chat-first support. InboxIQ works inside Gmail and Outlook with no new dashboard. Intercom is built around in-app chat and lifecycle messaging.",
        "competitor_wins": [
            "Best-in-class in-app chat and product tours",
            "Fin AI agent for automated chat resolution",
            "Strong lifecycle messaging and user segmentation",
        ],
        "inboxiq_wins": [
            "Built for email-first support — AI email triage works inside Gmail and Outlook with no new dashboard",
            "Far lower cost for email-only teams (from £19/inbox vs £74/seat)",
            "No chat widget to install — works entirely inside the existing inbox",
            "AI meeting scheduling in email replies — no equivalent in Intercom",
            "Per-inbox pricing: a team of 10 with 2 support inboxes pays for 2, not 10 seats",
        ],
        "faqs": [
            {
                "q": "What is the difference between InboxIQ and Intercom for email support?",
                "a": "Intercom is primarily a chat and lifecycle messaging platform — email support is secondary. InboxIQ is built specifically for AI email triage inside Gmail and Outlook, with no new dashboard to learn. For teams whose primary channel is email, InboxIQ is a more focused and affordable alternative.",
            },
            {
                "q": "Does InboxIQ work inside Gmail and Outlook as an Intercom alternative?",
                "a": "Yes. InboxIQ works inside Gmail and Outlook — there is no new dashboard, no chat widget to install, and no migration required. It provides AI email triage, draft replies, and meeting scheduling directly in your existing inbox.",
            },
            {
                "q": "Is InboxIQ cheaper than Intercom for email triage?",
                "a": "Significantly, yes. Intercom starts at around £74 per seat per month. InboxIQ charges per inbox from £19/month — a team with two support inboxes pays £38/month regardless of headcount.",
            },
            {
                "q": "Can InboxIQ replace Intercom for a support team that only uses email?",
                "a": "If your team only handles support via email (Gmail or Outlook), InboxIQ is a direct and much cheaper replacement. It provides AI email triage, routing, draft replies, and meeting scheduling with no new dashboard. Intercom's strengths (in-app chat, product tours, lifecycle campaigns) are not relevant for email-only teams.",
            },
            {
                "q": "What AI features does InboxIQ offer compared to Intercom's Fin AI?",
                "a": "InboxIQ provides AI email triage, priority scoring, automatic labelling, and AI-generated draft replies — all working inside Gmail and Outlook with no new dashboard. Intercom's Fin AI is focused on chat resolution. InboxIQ also includes AI meeting scheduling, allowing support replies to automatically include a booking link.",
            },
        ],
    },
    "front": {
        "name": "Front",
        "slug": "front",
        "tagline": "Shared inbox platform for team email collaboration",
        "verdict": "Front is a polished shared inbox built around team collaboration. InboxIQ is the better fit if you want AI email triage that works inside Gmail or Outlook itself — rather than syncing to a separate platform — with no new dashboard to learn.",
        "pricing_model": "Per seat (£19–99/seat/month)",
        "works_in_gmail_outlook": False,
        "ai_triage": False,
        "ai_triage_note": "Limited AI features on higher plans",
        "setup_time": "Hours",
        "helpdesk_replacement": False,
        "meeting_scheduling": False,
        "free_trial": "7 days",
        "self_hosted": False,
        "buyer_journey": "Inbox-native teams seeking team email collaboration",
        "description": "InboxIQ vs Front: compare AI email triage and inbox-native workflows. InboxIQ works inside Gmail and Outlook with no new dashboard. Front syncs email to a separate shared inbox platform.",
        "competitor_wins": [
            "Strong team collaboration features (assignments, internal comments, shared drafts)",
            "Clean interface with good mobile app",
            "Wide integrations including CRM and project management tools",
        ],
        "inboxiq_wins": [
            "AI email triage works inside Gmail and Outlook — no new dashboard to learn, no email sync required",
            "AI-generated draft replies included — Front has limited AI on most plans",
            "Per-inbox pricing is typically cheaper than Front's per-seat model",
            "AI meeting scheduling in email replies built in",
            "No email migration needed — connects via OAuth, live in minutes",
        ],
        "faqs": [
            {
                "q": "What is the difference between InboxIQ and Front for email management?",
                "a": "Front syncs your email to a separate shared inbox platform where your team collaborates. InboxIQ works inside Gmail and Outlook directly — there is no new dashboard, no email sync, and no platform to learn. InboxIQ also includes AI email triage and draft replies that Front does not offer on standard plans.",
            },
            {
                "q": "Does InboxIQ work inside Gmail and Outlook unlike Front?",
                "a": "Yes. InboxIQ is a Front alternative that works natively inside Gmail and Outlook with no new dashboard. Front requires your team to move to a separate platform. InboxIQ adds AI email triage, routing, and draft replies without changing your existing inbox workflow.",
            },
            {
                "q": "Is InboxIQ cheaper than Front?",
                "a": "For most teams, yes. Front charges per seat from £19/month. InboxIQ charges per inbox from £19/month — a team with one shared support inbox pays £19 regardless of how many people access it.",
            },
            {
                "q": "Can InboxIQ replace Front for a small support team?",
                "a": "If your team wants AI email triage and draft replies inside Gmail or Outlook with no new dashboard, InboxIQ is a simpler and typically cheaper alternative to Front. Front's strengths are team collaboration features (comments, assignments) — if those are critical, Front remains strong.",
            },
            {
                "q": "Does InboxIQ have AI email triage that Front lacks?",
                "a": "Yes. InboxIQ includes AI email triage on every paid plan — automatically classifying, prioritising, and drafting replies for incoming emails inside Gmail and Outlook with no new dashboard. Front has limited AI on most plans and requires a separate platform.",
            },
        ],
    },
    "helpscout": {
        "name": "Help Scout",
        "slug": "helpscout",
        "tagline": "Simple shared inbox helpdesk focused on small teams",
        "verdict": "Help Scout is a clean, simple helpdesk for small teams. InboxIQ is the better fit if you want AI email triage that works inside Gmail or Outlook itself — with no new platform to migrate to and no new dashboard to learn.",
        "pricing_model": "Per user (£20–65/user/month)",
        "works_in_gmail_outlook": False,
        "ai_triage": False,
        "ai_triage_note": "Beacon AI is limited to chat; no email triage",
        "setup_time": "Hours",
        "helpdesk_replacement": True,
        "meeting_scheduling": False,
        "free_trial": "15 days",
        "self_hosted": False,
        "buyer_journey": "Inbox-native teams seeking simplicity",
        "description": "InboxIQ vs Help Scout: compare AI email triage and Gmail/Outlook integration. InboxIQ works inside your existing inbox with no new dashboard. Help Scout is a separate shared inbox platform.",
        "competitor_wins": [
            "Clean, simple interface with low learning curve",
            "Good customer satisfaction (CSAT) features",
            "Docs knowledge base included on higher plans",
        ],
        "inboxiq_wins": [
            "AI email triage works inside Gmail and Outlook — no new dashboard, no migration",
            "AI draft replies included — Help Scout has no equivalent email AI",
            "Per-inbox pricing is often cheaper for small teams than per-user",
            "AI meeting scheduling in email replies built in",
            "Live in minutes via OAuth — no helpdesk to configure",
        ],
        "faqs": [
            {
                "q": "What is the difference between InboxIQ and Help Scout?",
                "a": "Help Scout is a separate shared inbox platform that your team migrates to. InboxIQ works inside Gmail and Outlook with no new dashboard — your team never changes how they access email. InboxIQ also includes AI email triage and draft replies that Help Scout does not offer.",
            },
            {
                "q": "Does InboxIQ work inside Gmail and Outlook as a Help Scout alternative?",
                "a": "Yes. InboxIQ is a Help Scout alternative that works natively inside Gmail and Outlook with no new dashboard. It provides AI email triage, automatic labelling, AI draft replies, and meeting scheduling — all without migrating to a new platform.",
            },
            {
                "q": "Is InboxIQ cheaper than Help Scout for a small team?",
                "a": "Typically yes. Help Scout charges £20–65 per user per month. InboxIQ charges per inbox from £19/month — a team sharing one support inbox pays £19 regardless of team size.",
            },
            {
                "q": "Can InboxIQ replace Help Scout for email support?",
                "a": "For teams managing support through Gmail or Outlook, InboxIQ is a direct replacement with no new dashboard, no migration, and AI email triage included. Help Scout's advantages are simplicity and CSAT tooling — if you specifically need those, Help Scout remains a strong option.",
            },
            {
                "q": "What AI features does InboxIQ have that Help Scout lacks?",
                "a": "InboxIQ includes AI email triage, priority scoring, automatic labelling, and AI-generated draft replies — all working inside Gmail and Outlook with no new dashboard. Help Scout's Beacon AI is limited to chat; there is no AI triage or drafting for email in Help Scout.",
            },
        ],
    },
    "groove": {
        "name": "Groove",
        "slug": "groove",
        "tagline": "Simple helpdesk for small teams built around shared inboxes",
        "verdict": "Groove is an affordable, simple helpdesk for small teams. InboxIQ is the better choice if you want AI email triage that works inside Gmail or Outlook with no new dashboard — rather than syncing to another platform.",
        "pricing_model": "Per user (£16–56/user/month)",
        "works_in_gmail_outlook": False,
        "ai_triage": False,
        "ai_triage_note": "No AI triage or draft replies",
        "setup_time": "Hours",
        "helpdesk_replacement": True,
        "meeting_scheduling": False,
        "free_trial": "7 days",
        "self_hosted": False,
        "buyer_journey": "Small inbox-native teams seeking a simple, affordable helpdesk",
        "description": "InboxIQ vs Groove: compare AI email triage, pricing, and Gmail/Outlook integration. InboxIQ works inside your existing inbox with no new dashboard. Groove is a separate shared inbox helpdesk.",
        "competitor_wins": [
            "Low starting price with a simple interface",
            "Collision detection for shared inboxes",
            "Decent reporting for small teams",
        ],
        "inboxiq_wins": [
            "AI email triage works inside Gmail and Outlook — no new dashboard, no migration",
            "AI draft replies included in every plan — Groove has no AI features",
            "Per-inbox pricing is comparable or cheaper for single-inbox teams",
            "AI meeting scheduling in email replies built in",
            "Setup in minutes via OAuth — no helpdesk to configure",
        ],
        "faqs": [
            {
                "q": "What is the difference between InboxIQ and Groove for email support?",
                "a": "Groove is a separate helpdesk platform that your team migrates email to. InboxIQ works inside Gmail and Outlook with no new dashboard — there is no migration and your team continues using the inbox they know. InboxIQ also includes AI email triage and draft replies that Groove does not offer.",
            },
            {
                "q": "Does InboxIQ work inside Gmail and Outlook as a Groove alternative?",
                "a": "Yes. InboxIQ is a Groove alternative that provides AI email triage, labelling, and draft replies directly inside Gmail and Outlook — no new dashboard, no platform to learn, no email migration required.",
            },
            {
                "q": "Is InboxIQ cheaper than Groove?",
                "a": "For single-inbox teams, prices are similar. Groove starts at £16 per user per month. InboxIQ starts at £19 per inbox per month — a team of three sharing one support inbox pays £19 with InboxIQ vs £48 with Groove.",
            },
            {
                "q": "Does InboxIQ have AI features that Groove lacks?",
                "a": "Yes. InboxIQ includes AI email triage, priority scoring, automatic labelling, AI-generated draft replies, and AI meeting scheduling — all working inside Gmail and Outlook with no new dashboard. Groove has no AI email triage or drafting features.",
            },
            {
                "q": "Can InboxIQ replace Groove for a small support team?",
                "a": "Yes. For small teams handling support through Gmail or Outlook, InboxIQ is a direct replacement with AI email triage built in and no new dashboard to learn. Groove requires migrating to a separate platform and adds no AI capability.",
            },
        ],
    },
}

COMPETITORS["n8n"] = {
    "name": "N8N / Make / Zapier",
    "slug": "n8n",
    "tagline": "No-code workflow automation platforms that developers use to build custom email pipelines",
    "verdict": "N8N, Make, and Zapier are excellent automation platforms for developers who want maximum flexibility. InboxIQ is the finished product those platforms are asking you to build — purpose-built for shared team inboxes, with AI triage, threaded draft replies, approval workflows, and SLA tracking that work out of the box in under an hour.",
    "pricing_model": "Per execution (N8N ~€20–667/mo depending on volume; Make/Zapier similar)",
    "works_in_gmail_outlook": False,
    "ai_triage": True,
    "ai_triage_note": "Requires LLM API key + custom prompt engineering per deployment",
    "setup_time": "Days to weeks (developer project)",
    "helpdesk_replacement": False,
    "meeting_scheduling": False,
    "free_trial": "Free tier with strict execution limits",
    "self_hosted": True,
    "threaded_draft_replies_note": "✗ Known open bug — N8N Gmail node cannot set In-Reply-To headers; Outlook node cannot create drafts at all",
    "shared_team_inbox_note": "✗ No built-in shared queue, round-robin assignment, or team routing layer",
    "natural_language_rules_note": "✗ Rules are JSON nodes wired by a developer, not plain-English descriptions",
    "approval_workflows_note": "✗ No native inbox-thread approval primitive — requires third-party tools",
    "buyer_journey": "Developers and automation engineers who want custom control",
    "description": "InboxIQ vs N8N, Make, and Zapier: why workflow builders are not email triage products. InboxIQ ships threaded draft replies, team routing, SLA tracking, and approval workflows out of the box. N8N requires a developer, LLM API keys, and weeks of custom build time — with known limitations in Gmail and Outlook draft creation.",
    "competitor_wins": [
        "Maximum flexibility — can automate almost any multi-step process across hundreds of apps",
        "Self-hostable with no execution caps on the open-source version",
        "Large community of pre-built workflow templates for non-email use cases",
    ],
    "inboxiq_wins": [
        "Ships as a complete product — no prompt engineering, no node building, no LLM API keys required",
        "Threaded draft replies work inside Gmail and Outlook natively — N8N has a known open bug preventing proper in-thread drafting in Gmail, and no draft-reply capability in Outlook at all",
        "Team inbox routing built in — assign to team members, shared queue management, and SLA tracking without writing a single node",
        "Natural language automation rules — describe what you want in plain English ('when a billing complaint arrives, route to the billing team and create a P1 ticket'); N8N requires JSON node configuration by a developer",
        "Prior authorization workflows — approve or reject requests directly from your inbox; the decision is logged with a timestamped audit trail automatically",
        "Booking links in replies — when a meeting request is detected, InboxIQ includes a calendar slot link in the draft reply automatically; no Calendly integration to wire up",
        "Multi-channel unified intake — email, forms, chat, voice, and social media all flow through the same triage engine; each channel in N8N/Make is a separate workflow to build and maintain",
        "Per-inbox pricing with no execution caps — N8N cloud at 2,500 executions/month is exhausted by a single Gmail polling workflow in 3.5× overage",
    ],
    "faqs": [
        {
            "q": "Can N8N do what InboxIQ does for email triage?",
            "a": "N8N can be wired up to approximate some InboxIQ features, but it is a developer project, not a finished product. A production email triage workflow in N8N requires configuring an LLM API, writing classification prompts, building routing branches, and maintaining the workflow over time. N8N also has a known open bug preventing threaded draft replies in Gmail, and no native draft-reply capability in Outlook. InboxIQ ships all of this pre-built and connects via OAuth in under an hour.",
        },
        {
            "q": "What is the difference between N8N and InboxIQ?",
            "a": "N8N is an automation builder — it is plumbing you assemble yourself. InboxIQ is the finished product that plumbing would be trying to recreate. InboxIQ delivers AI email triage that works inside Gmail and Outlook with no new dashboard — support managers, IT admins, and ops teams connect via OAuth and are live in under an hour. N8N gives developers maximum flexibility but requires LLM API keys, custom prompt engineering, and ongoing maintenance before the first email is classified.",
        },
        {
            "q": "Can Make or Zapier replace InboxIQ for email triage?",
            "a": "Make and Zapier face the same fundamental limitation as N8N for email triage: they are automation platforms, not email intelligence products. Creating a draft reply inside a Gmail or Outlook thread, routing emails to team members based on semantic content, tracking SLA response times, and running approval workflows from the inbox all require significant custom build time on Make or Zapier — and still may not work natively inside the inbox. InboxIQ ships all of these as default capabilities.",
        },
        {
            "q": "Is N8N cheaper than InboxIQ?",
            "a": "At face value N8N's entry price is lower, but the total cost of ownership is not. A production N8N email triage deployment requires developer time (setup and ongoing maintenance), LLM API costs (OpenAI/Anthropic per-token charges), and N8N cloud execution costs that scale with email volume — a single Gmail polling workflow on N8N Starter exhausts the monthly quota in under four days. InboxIQ prices per inbox with no execution caps, no API keys to manage, and no developer required.",
        },
        {
            "q": "Does InboxIQ work with N8N or Zapier?",
            "a": "Yes. InboxIQ provides a webhook and API (Developer Portal) that can be used as a trigger or action step inside N8N, Make, or Zapier workflows. Teams that already use these platforms can use InboxIQ as the inbox intelligence layer — handling triage, classification, and draft replies — while N8N/Make handles downstream automation like CRM updates, Slack notifications, or ticketing system sync.",
        },
    ],
}

COMPETITORS["microsoft-copilot"] = {
    "name": "Microsoft Copilot / Claude in Outlook",
    "slug": "microsoft-copilot",
    "tagline": "AI writing assistants embedded in individual Outlook inboxes",
    "verdict": "Microsoft Copilot and Claude in Outlook make individual knowledge workers faster in their own inbox. InboxIQ automates shared team inboxes — routing, SLA tracking, approval workflows, and multi-channel intake that neither Copilot nor Claude in Outlook was designed to handle.",
    "pricing_model": "Copilot: $18–30/user/month on top of M365 subscription",
    "works_in_gmail_outlook": True,
    "ai_triage": True,
    "ai_triage_note": "Personal inbox summarisation only — no shared inbox classification",
    "setup_time": "Immediate (included in M365 Copilot licence)",
    "helpdesk_replacement": False,
    "meeting_scheduling": False,
    "free_trial": "Included in M365 Business / Enterprise plans",
    "self_hosted": False,
    "threaded_draft_replies_note": "✓ Copilot drafts replies — but only for the individual user's inbox, not a shared team inbox",
    "shared_team_inbox_note": "⚠ Copilot shared inbox action-taking marked 'not supported, coming soon' in Microsoft docs as of mid-2026",
    "natural_language_rules_note": "✗ No automation rules — Copilot assists on demand, does not act automatically on incoming email",
    "approval_workflows_note": "✗ Claude in Outlook is read-only — it cannot draft, send, route, or take any action inside Outlook",
    "buyer_journey": "Microsoft 365 customers evaluating whether Copilot replaces dedicated inbox tools",
    "description": "InboxIQ vs Microsoft Copilot and Claude in Outlook: why AI writing assistants are not shared inbox automation tools. Copilot helps individual users draft faster. InboxIQ operates on shared team inboxes — routing, SLA, approval workflows, and multi-channel intake that Copilot was not designed to handle.",
    "competitor_wins": [
        "Included with existing M365 subscriptions — no new vendor to evaluate for existing Microsoft customers",
        "Deep integration with Teams, SharePoint, and the full M365 ecosystem",
        "Personal productivity gains for individual knowledge workers across all Microsoft apps",
    ],
    "inboxiq_wins": [
        "Built for shared team inboxes (support@, hr@, it@) — Copilot's shared inbox capabilities are still marked 'coming soon' in Microsoft's own documentation",
        "Acts automatically on every inbound email without a human prompt — Copilot waits for a user to open a message and ask; InboxIQ classifies, routes, and drafts before anyone opens the email",
        "Claude in Outlook is read-only — Anthropic's Microsoft 365 connector can search and read threads to answer questions in Claude.ai, but it cannot draft, send, route, or take any action inside Outlook whatsoever",
        "Team routing and assignment — InboxIQ routes emails to the right team member based on content, not just the person whose inbox received it",
        "Prior authorization and approval workflows — employees email a request, the approver replies from their own inbox, the decision is logged with an audit trail; Copilot has no approval workflow primitive",
        "Booking links in draft replies — InboxIQ detects meeting requests and includes a calendar slot link automatically; no Outlook add-in configuration required",
        "Natural language automation rules — describe what should happen when a certain email arrives ('route all billing complaints to Sarah and mark P1'); Copilot cannot create automation rules",
        "Per-inbox pricing vs per-user — a 10-person team using one shared support@ inbox pays for one inbox with InboxIQ, vs 10 Copilot licences at $18–30/user",
        "Multi-channel intake — email, forms, chat, voice, and social media through one triage engine; Copilot only handles Outlook",
    ],
    "faqs": [
        {
            "q": "Does Microsoft Copilot work in shared team inboxes?",
            "a": "As of mid-2026, Microsoft's own documentation marks Copilot action-taking in shared and delegated mailboxes as 'not supported, coming soon.' Thread summarisation reached shared mailboxes in GA only recently, and routing, assignment, or SLA tracking in shared inboxes is not on the current roadmap. InboxIQ is purpose-built for shared team inboxes as its primary use case.",
        },
        {
            "q": "What is Claude in Outlook — can it replace InboxIQ?",
            "a": "Anthropic's Claude connector for Microsoft 365 is a read-only research tool. It can search and read your Outlook threads, Teams messages, and SharePoint content to answer questions in the Claude.ai interface. It cannot draft replies, send emails, route messages, create tickets, or take any action inside Outlook. It is useful for information retrieval — it is not an inbox automation tool.",
        },
        {
            "q": "Can Copilot route emails to team members automatically?",
            "a": "No. Microsoft Copilot in Outlook is a personal writing assistant — it helps the person whose inbox it is draft and summarise faster. It does not classify inbound emails, route them to team members, assign ownership, or track whether a response was sent within SLA. These are the core operations that InboxIQ handles automatically before any human opens the email.",
        },
        {
            "q": "Is InboxIQ a Copilot alternative for Outlook?",
            "a": "For personal inbox productivity, Copilot and InboxIQ serve different purposes and are complementary. For shared team inbox operations — routing, SLA tracking, approval workflows, and automatic triage across support@, hr@, or it@ — InboxIQ does what Copilot was not designed to do. Many teams use both: Copilot for personal productivity in their individual inbox, InboxIQ for the shared operational inboxes their team manages.",
        },
        {
            "q": "Does InboxIQ work in Outlook as well as Gmail?",
            "a": "Yes. InboxIQ delivers AI email triage that works inside Gmail and Outlook with no new dashboard — your team connects via OAuth and continues using the inbox they already know. Triage labels, draft replies, routing, and approval workflows all appear directly inside the email client.",
        },
    ],
}

VALID_SLUGS = set(COMPETITORS.keys())


def get_competitor(slug: str) -> Optional[dict]:
    """Return competitor data dict or None if slug is unknown."""
    return COMPETITORS.get(slug)
