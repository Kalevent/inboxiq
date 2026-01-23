# Social Publishing Agent Plan (InboxIQ)

### Scope
- Internal-only: let staff draft/publish to a few social channels (LinkedIn company/page, X/Twitter).
- Keep existing blog/newsletter/whitepaper flows unchanged; social posting is additive.
- No auto-posting without explicit approval; respect RBAC (owners/admins only).

### Constraints
- Internal use only; no multi-tenant/consumer-facing UI.
- No social connectors exist today; requires OAuth/app registrations per channel.
- Keep the same agent/MCP pattern: agent invoke → MCP HTTP tool → internal social endpoints.
- Minimal surface: one endpoint per channel to create/publish posts; optional media upload later.

### Design
- New endpoints (auth-required):
  - `POST /publishing/social/draft` (channel, text, media refs, audience tags) → returns draft id + preview payload.
  - `POST /publishing/social/publish/<draft_id>` → posts to external channel; stores external post id/link.
  - `GET /publishing/social/drafts` (include status filter) → list with links to previews.
- Draft model/table: `social_drafts` with fields: id, channel, text, rendered_preview, media_json, status (draft|queued|failed|published), external_post_id/url, error, created_at, updated_at.
- MCP: reuse generic HTTP MCP; add tools to call the above endpoints (`create_social_draft`, `publish_social_post`) or direct HTTP `http_request`.
- LLM: reuse shared `llm_client` to generate short-form copy when requested (`sync:true` or Celery for async); fallback is explicit error, no stub.
- Auth to socials: per-channel OAuth tokens stored securely (env/secret store). Single-tenant/internal only.
- RBAC: owner/admin only for publish; drafts visible to authenticated staff.

### Implementation Steps
1) **Model**: add `social_drafts` table via migration (fields above).
2) **Routes** (`src/publishing/routes.py`):
   - `POST /publishing/social/draft` (sync/async generation using `llm_client`).
   - `POST /publishing/social/publish/<id>` (calls channel-specific client; records external id/link).
   - `GET /publishing/social/drafts` (auth, optional status filter).
   - `GET /publishing/social/draft/<id>` (auth preview with "Draft" banner).
3) **Channel clients** (`src/publishing/social_clients.py`):
   - LinkedIn: post to organization/page (text + optional media URL).
   - X/Twitter: post text + optional media.
   - Pluggable interface for future channels.
4) **MCP tools**: extend HTTP MCP usage or add small wrappers (`create_social_draft`, `publish_social_post`) pointing at the new endpoints.
5) **Admin UI** (`src/templates/admin.html`):
   - Add Social Publishing panel with draft list link and ID-to-preview/publish helpers.
6) **RBAC/Guardrails**:
   - Restrict publish endpoints to owner/admin.
   - Input validation (length limits per channel; no empty text).
   - Error logging with external response snippets.
7) **Config**:
   - Channel app keys/secrets (env/secret store).
   - `OPENAI_API_KEY` already used; optional `SOCIAL_MAX_TOKENS`, `SOCIAL_ALLOWED_CHANNELS`.
8) **Testing**:
   - Unit: draft generation (LLM mocked), validation, status transitions.
   - Integration: mock LinkedIn/X clients; publish happy-path and failure.
   - MCP: agent invoke → HTTP MCP → social draft/publish endpoints.

### Risks / Mitigations
- OAuth/key management: single-tenant/internal; keep secrets out of logs; rotate keys manually if needed.
- Rate limits: handle 429 with backoff; surface errors to drafts.
- Content length/channel rules: validate server-side before publish.
- Security: require auth on all draft/publish endpoints; limit to owner/admin roles.
