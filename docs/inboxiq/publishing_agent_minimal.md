# Publishing AI Agent (Minimal, InboxIQ-Style)

Lean plan to add a publishing agent that drafts, persists, and publishes blogs, newsletters, and whitepapers using the current inboxiq-style agent framework (`src/api/v1/agents.py`) and existing publishing flows. No new external frameworks; reuse MCP servers and Flask/Celery patterns already in the repo.

## What we learned from inboxiq (legacy)
- Agents are plain dict-backed objects managed by `AgentRegistry`; no pydantic or heavy models.
- MCP invocations are pooled via `PersistentMCPClient` to avoid per-call spawn cost.
- LLM is opt-in (`use_llm` flag); errors are captured in `AgentEvent` with latency metrics.
- Minimal shape for MCP server configs: label + command/env/cwd rows in `MCPServerCatalog`; the first server is used by default.

## Goals
- One publishing agent that can: create drafts, regenerate, and publish blogs/newsletters/whitepapers.
- Source blueprint (current): `app/publishing` (controllers, tasks, models). Destination blueprint (planned): `src/publishing/` where we will copy/move the new code and register a `publishing` blueprint there.
- Reuse existing publishing endpoints/tasks (`app/publishing/controllers.py`, `app/publishing/tasks.py`) and models (`NewsletterDraft`, `WhitepaperDraft`, new `BlogDraft`) as the starting point before relocation.
- Keep code minimal: a small agent spec plus thin helper functions; no new frameworks.
- Exclude social/outbound campaigns; email sending remains via newsletter publish only.

## Data and endpoints to reuse
- Newsletters: `/publishing/newsletter/draft`, `/publishing/newsletter/publish/<id>`, `/publishing/newsletter/drafts`, `/publishing/preview/<id>`.
- Whitepapers: `/publishing/whitepaper/draft`, `/publishing/whitepaper/download/<id>`.
- New blogs (to add): `/publishing/blog/draft`, `/publishing/blog/publish/<id>`, `/publishing/blogs` (list), `/publishing/blog/<slug>` (public).
- MCP SQL server: `kalevent_mcp/sql_mcp.py` (`run_query`, `execute`) for direct persistence/reads when needed.

## Minimal agent shape (registry-first)
- Agent stored via `AgentRegistry.create` with fields:
  - `name`: "Publishing Agent"
  - `description`: drafts/publishes blogs, newsletters, whitepapers.
  - `mcp_servers`: one entry pointing to the SQL MCP command (label `db` or similar).
  - `capabilities` (optional tags): `sql`, `http`.
  - `triggers`: manual only for now.
  - `human_review`: optional checkpoint before publish.
- Invocation contract:
  - `tool`: defaults to `triage_email_ticket` today; we will add publishing tools so caller sets `tool` to one of: `create_blog_draft`, `create_newsletter_draft`, `create_whitepaper_draft`, `publish_blog`, `publish_newsletter`, `publish_whitepaper`.
  - `arguments`: JSON payload matching each endpoint (e.g., `{"title": "...", "brief": "...", "audience": "..."}`).
  - `mode`: `llm` optional; otherwise MCP tool path is used.

## Blog flow (new, mirrors existing patterns)
- Model: reuse `BlogPost` (src/models.py) with status transitions; add fields as needed (`markdown`, `rendered_html`, `brief_json`, `last_prompt`) while keeping `content_html`, `slug`, `status`, `published_at`.
- Draft endpoint (sync/async option like newsletters):
  - Validate `title`, `brief`, `audience`.
  - Queue Celery task `draft_blog_task` or run sync path using `create_text_completion` with a blog-specific system prompt (short-form article, CTA).
  - Persist markdown and rendered HTML on `BlogPost`; leave status `draft`/`ready` before publish.
  - Status lifecycle: `draft|queued|generating|ready|failed|published`.
- Publish endpoint:
  - Flip status to `published`, set `published_at`, expose public slug route.
  - Store final rendered HTML in `content_html` (and optionally keep `rendered_html`/`markdown` for history).
- Public view: `/publishing/blog/<slug>` renders stored HTML; 404 for non-published.

## Newsletter flow (existing)
- Model: `NewsletterDraft` in `app/publishing/models.py` with `status`, `rendered_html`, `brief_json`.
- Draft endpoint: `/publishing/newsletter/draft` (sync or Celery via `draft_newsletter_task`), uses `SYSTEM_NEWSLETTER`, enforces JSON and renders Jinja email template; status `queued|generating|ready|failed|published`.
- Publish endpoint: `/publishing/newsletter/publish/<id>` flips status to `published`; email send task can be enqueued separately.
- Preview: `/publishing/preview/<id>` (if rendered HTML stored).
- List: `/publishing/newsletter/drafts`.

## Whitepaper flow (existing)
- Model: `WhitepaperDraft` with `markdown`, optional `pdf_url`, `status`, `brief_json`.
- Draft endpoint: `/publishing/whitepaper/draft` (sync or Celery via `draft_whitepaper_task`), uses `SYSTEM_WHITEPAPER`; can render to PDF via pandoc or return markdown.
- Download/publish: `/publishing/whitepaper/download/<id>` for ready drafts; publish can be represented by status flip when ready.
- Status lifecycle: `queued|generating|ready|failed|published` (published optional if we want a flag when shared externally).

## Agent-to-publishing wiring (minimal glue)
- Add small tool wrappers (Flask endpoints or MCP tool shims):
  - `create_blog_draft` → POST to `/publishing/blog/draft`.
  - `publish_blog` → POST `/publishing/blog/publish/<id>`.
  - Reuse existing newsletter/whitepaper draft/publish endpoints similarly.
- In `PersistentMCPClient.invoke`, the agent calls these wrapper tools via MCP HTTP or directly via SQL MCP for list/read operations (e.g., fetch latest drafts).
- Keep MCP server list simple: one SQL server for DB writes; optionally add HTTP MCP for internal POSTs if needed.

## Safety and constraints
- No social media/connectors; only blog/newsletter/whitepaper.
- Auth: keep `@login_required` on publishing endpoints; agent calls should carry service credentials if invoked internally.
- Input sanitation: reuse `_safe_json` and ICP reader; enforce slug regex for blogs.
- Error handling: mirror newsletter/whitepaper flows—on failure, delete draft or mark `failed`, log `AgentEvent` with latency and error message.

## Steps to implement (code delta)
1) Models: reuse `BlogPost` (in `src/models.py`) and extend it with any needed working fields (`markdown`, `rendered_html`, `brief_json`, `last_prompt`) instead of creating `BlogDraft`; keep status transitions (`draft` → `published`). Add migration for new fields.  
2) Controllers: add `/publishing/blog/draft`, `/publishing/blog/publish/<id>`, `/publishing/blog/<slug>`, `/publishing/blogs` list; sync/async generation with `draft_blog_task`; status flips on publish.  
3) Tasks: add `draft_blog_task` Celery job; reuse `_read_icp`, `create_text_completion`, markdown render; persist into `BlogPost`.  
4) Templates: optional `publishing/blog_post.html.j2` for render; or markdown-to-HTML fallback.  
5) Agent registry: seed a `Publishing Agent` via `POST /api/v1/agents` with MCP server command pointing to `kalevent_mcp/sql_mcp.py` (stdio).  
6) MCP tool wrappers: expose minimal tools for create/publish (HTTP MCP) or use SQL MCP to read/write posts where appropriate.  
7) Tests: Flask client tests for blog draft/publish, Celery task mock, agent invoke happy path using `PersistentMCPClient`.

## Invoke examples (using current API)
- Create agent:
  ```bash
  curl -X POST /api/v1/agents -H "Content-Type: application/json" -d '{
    "name": "Publishing Agent",
    "description": "Drafts and publishes blogs, newsletters, whitepapers",
    "mcp_servers": [{"label": "db", "command": ["python", "-m", "kalevent_mcp.sql_mcp"]}],
    "capabilities": ["sql", "http"],
    "triggers": [{"type": "manual"}]
  }'
  ```
- Invoke to draft a newsletter (sync):
  ```bash
  curl -X POST /api/v1/agents/<id>/invoke -H "Content-Type: application/json" -d '{
    "tool": "create_newsletter_draft",
    "arguments": {"campaign_title": "October update", "audience": "Gov procurement", "brief": "Focus on audit readiness", "sync": true}
  }'
  ```
- Invoke to publish a blog:
  ```bash
  curl -X POST /api/v1/agents/<id>/invoke -d '{
    "tool": "publish_blog",
    "arguments": {"draft_id": "<draft-id>"}
  }'
  ```

## Notes
- Keep code additions small and local; mirror inboxiq patterns (no pydantic models).
- Prefer MCP pooling (already in `_get_persistent_mcp_client`) to keep agent calls cheap.
- Avoid new connectors; all outbound stays disabled.
