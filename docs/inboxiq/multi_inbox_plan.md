# Multi-Inbox Support Plan

## The scenario

Oliver is the account owner. He pays. His wife wants to connect her own Gmail to the same InboxIQ account. She wants her own login, her own automation rules, and she should not see Oliver's emails. Oliver should not see hers either.

This is a two-phase problem:

- **Phase 1 — Multi-inbox (build now):** One account, multiple email addresses connected. All tickets visible to whoever is logged in as owner. Simple constraint swap.
- **Phase 2 — Multi-user / seat model (build after):** Wife gets her own InboxIQ login, sees only her inbox, manages her own rules. Oliver remains owner and pays.

---

## Phase 1 — Multi-inbox

### The only real blocker

One line in `src/models/core.py`:

```python
UniqueConstraint("user_id", "provider", name="uq_user_provider_inbox")
```

This enforces one Gmail per user. Swap it to:

```python
UniqueConstraint("account_id", "email_address", name="uq_account_email_inbox")
```

One inbox per email address per account. Oliver and his wife can both connect Gmail as long as they use different addresses. That's it.

### What already works (no changes needed)

- **Polling** — `_poll_inbox_internal(connection_id)` operates per connection. The scheduler iterates all connections for an account.
- **Labels / intelligence** — OAuth tokens, label IDs, and metadata are stored per `InboxConnection` row. Wife's Gmail gets its own token, its own `InboxIQ/` labels, its own label cache — completely isolated from Oliver's.
- **Tickets** — scoped by `account_id`, so all inboxes feed the same dashboard.
- **Sender profiles & corrections** — shared across the account. If wife corrects `github.com → forums`, Oliver benefits from that signal too.
- **Credential changes** — InboxIQ uses OAuth tokens, not passwords. If wife changes her Gmail password, her OAuth token is unaffected. The connection only breaks if she explicitly revokes app access in Google — which already surfaces as an auth error in the poll loop.

### The 4 changes

**1. Model** (`src/models/core.py`)

Swap the unique constraint and add an optional display name:

```python
# Before
UniqueConstraint("user_id", "provider", name="uq_user_provider_inbox")

# After
UniqueConstraint("account_id", "email_address", name="uq_account_email_inbox")

# New field
display_name = db.Column(db.String(100), nullable=True)  # e.g. "Oliver's Gmail", "Sarah's Gmail"
```

**2. `connect_inbox` API** (`src/api/v1/inboxiq.py`)

Change the lookup from `filter_by(user_id, provider)` to `filter_by(account_id, email_address)`:

```python
# Before — overwrites the existing Gmail connection
conn = InboxConnection.query.filter_by(user_id=user_id, provider=provider).first()

# After — creates a new row for a new email address
conn = InboxConnection.query.filter_by(account_id=account_id, email_address=email_address).first()
```

Connecting `sarah@gmail.com` while `oliver@gmail.com` is already connected creates a second row — does not overwrite Oliver's.

**3. Settings UI** (`src/settings/routes.py` + template)

Replace the single "Connected inbox" slot with a list of all connections for the account. Each row shows: email address, display name, provider badge, status, last poll time, disconnect button. Add an "Add another inbox" button that re-runs the OAuth flow.

#### 4. Migration

```bash
flask db migrate -m "multi-inbox: swap unique constraint, add display_name"
```

Review the generated migration before `flask db upgrade`. It must drop `uq_user_provider_inbox` and add `uq_account_email_inbox`.

---

## Phase 2 — Multi-user / seat model

### The problem Phase 1 does not solve

After Phase 1, Oliver connects his wife's Gmail on her behalf. She has no InboxIQ login of her own. If she wants to set an automation rule — "archive anything from LinkedIn" — she has to ask Oliver to do it. She also sees Oliver's emails in the dashboard. That's not right.

### What the codebase already has

The `User` and `Account` models already anticipate this:

```python
# Account
seats_limit = db.Column(db.Integer, default=1)
seats_used  = db.Column(db.Integer, default=1)

# User
role = db.Column(db.String(32), server_default="agent")
# values: owner | admin | agent | viewer | billing
```

Multiple `User` rows can already belong to one `Account`. The roles are already defined. The seats counter is already there. The foundation exists — it just hasn't been wired to an invite flow or inbox scoping yet.

### Does the wife need to sign in?

**In Phase 1 — no.** Oliver connects her Gmail from his own InboxIQ account. The InboxIQ labels appear in her Gmail inbox automatically. Triage, drafts, and automation all run under Oliver's dashboard. She never touches InboxIQ. She just sees her inbox being organised.

Phase 2 login is only needed if she wants her own InboxIQ dashboard — her own view, her own rules — without seeing Oliver's emails. If Oliver manages everything on her behalf, Phase 1 is the complete story.

### Why "Sign in with Google" does not work for invited members

Oliver signed up via Google OAuth. The auth callback ([`src/api/v1/auth.py`](../../src/api/v1/auth.py)) calls `_find_or_create_user(email)`: if no `User` row exists for that email, it creates a **brand new account**. If Sarah clicks "Sign in with Google" today, she gets her own separate InboxIQ account — not Oliver's.

The invite flow must pre-create her `User` row first, linked to Oliver's `account_id`. Then when she logs in (any method), the lookup finds her existing row and drops her into Oliver's account.

### What Phase 2 adds

#### A. Invite flow and how Sarah logs in

**Step 1 — Oliver sends the invite**
Oliver goes to Settings → Team → "Invite member", enters `sarah@gmail.com`. The app creates a `User` row immediately: `email = sarah@gmail.com`, `account_id = oliver's account`, `role = agent`, `password_hash = null`. A one-time invite token is stored on the row. Sarah gets an email: "Oliver invited you to InboxIQ — click here to accept."

**Step 2 — Sarah accepts**
She clicks the link. It opens an InboxIQ page that says: "Set your password to continue." She enters a password. The app hashes it, saves it to her `User` row, marks the invite token as used. Done.

**Step 3 — Sarah logs in from now on**
She goes to the InboxIQ login page and uses **email + password** — `sarah@gmail.com` and the password she just set. That is her login. Not Google OAuth. Not Oliver's account. Her own email and her own password, but landing inside Oliver's InboxIQ account.

**Step 4 — Sarah connects her Gmail inbox**
Once logged in, she goes to Settings → Inboxes → "Connect inbox" and runs the Gmail OAuth flow. This is separate from logging into InboxIQ — it is only for giving InboxIQ permission to read her Gmail. Her `InboxConnection` is created with `user_id = sarah.id`, `account_id = oliver's account`.

**Summary of the two different Google things:**
- "Sign in with Google" on the login page = Oliver's way in (owner only, not for invited members)
- Gmail OAuth in Settings → Inboxes = how any user connects their email inbox (Oliver and Sarah both do this)

These are two completely separate OAuth flows. Sarah uses the first one never. She uses the second one once to connect her inbox.

#### B. Inbox ownership

`InboxConnection.user_id` already points to a `User`. In Phase 1 Oliver connects his wife's Gmail under his own `user_id`. In Phase 2, after wife has her own `User` row, her `InboxConnection` is re-associated (or connected fresh) with `user_id = wife.id`. This is the link that scopes what she sees.

#### C. Ticket scoping

Add `connection_id` as a FK on the `Ticket` model (already flagged as future work). When wife logs in, the dashboard filters to `connection_id IN [her connections]`. Oliver as owner sees all.

```python
# Ticket model addition
connection_id = db.Column(db.String(64), db.ForeignKey("inbox_connections.id"), nullable=True, index=True)
```

#### D. Automation rule scoping

`AutomationRule` is currently scoped to `account_id` only — rules apply to all inboxes on the account. Add an optional `connection_ids` JSON field:

```python
connection_ids = db.Column(db.JSON, nullable=True)
# None / [] = applies to all inboxes on the account (Oliver's rules)
# ["conn-uuid-1"] = applies only to that inbox (wife's rules)
```

When the rule engine evaluates a ticket, it checks: if `rule.connection_ids` is set, only fire if `ticket.connection_id` is in that list.

Wife creates her own rules in Automation Studio. They only fire on her inbox. Oliver's rules fire on all inboxes unless he scopes them too.

### Phase 2 change summary

| What | Where | Notes |
| --- | --- | --- |
| Invite endpoint + email | `src/api/v1/` + `src/notifications/emails.py` | Creates `User`, sends invite link |
| Accept invite page | `src/settings/` or new blueprint | Sets password, marks invite used |
| Seats enforcement | `connect_inbox` / invite flow | Reject if `seats_used >= seats_limit` |
| `Ticket.connection_id` FK | `src/models/tickets.py` | Migration required |
| Dashboard inbox filter | UI + API | Filter by connection_id for non-owners |
| `AutomationRule.connection_ids` | `src/models/automation.py` | Migration required |
| Rule engine scope check | `src/automation/` | Skip rule if ticket.connection_id not in rule.connection_ids |

### What the wife experience looks like end-to-end (Phase 2)

1. Oliver opens Settings → Team → "Invite Sarah"
2. Sarah gets an email, clicks the link, sets her password
3. Sarah logs into InboxIQ with her own credentials
4. Sarah goes to Settings → Inboxes → "Connect inbox" → connects her Gmail via OAuth
5. Her `InboxConnection` is created with `user_id = sarah.id`, `account_id = oliver.id`
6. Sarah's dashboard shows only her tickets. Oliver's dashboard shows all tickets (owner privilege)
7. Sarah opens Automation Studio, creates a rule — it is automatically scoped to her inbox
8. Oliver can see Sarah's rules in a read-only team view if needed

---

## Out of scope (not in either phase)

- **True inbox isolation at the owner level** (Oliver cannot see wife's emails even as owner) — requires an explicit privacy model, not just scoping. Design separately if needed.
- **Inbox-based billing** — the natural billing unit is the connected inbox (`InboxConnection`), not the user. Charge per inbox, not per seat. The existing `seats_limit` / `seats_used` fields on `Account` should be repurposed or renamed to `inbox_limit` / `inbox_used`. A plan gives you N inboxes; adding more costs more. Users (team members) are free — you're paying for the intelligence on each email stream.
- **Shared inbox** — deliberately retired. Automation rules with AI forwarding replace this pattern entirely. If an email needs a colleague's attention, a rule forwards it to their inbox. They handle it in their own InboxIQ instance. No shared queue, no manual routing. Do not add shared inbox code. If any future PR or feature introduces a shared queue or joint inbox view as a first-class concept, reject it — the routing problem it solves belongs to the rule engine.
