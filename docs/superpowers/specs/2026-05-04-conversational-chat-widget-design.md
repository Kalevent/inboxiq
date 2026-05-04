# Conversational Chat Widget Redesign

> **Status:** Approved for implementation

## Goal

Replace the upfront-form chat widget with a conversational widget that greets visitors with an avatar and three CTA buttons, collecting details contextually instead of asking for them immediately. This removes friction and increases engagement.

## Architecture

### What Changes

- **Full rewrite** of `src/static/js/chat-widget.js` — new state machine, CTA buttons, guided flows
- **No new backend routes** — `/api/v1/chat/submit` stays intact; name/email already optional
- **One new API call** inside the "talk" branch: `POST /api/v1/enterprise-inquiry` (create `EnterpriseInquiry` record)
- **DSPy signature update** — `build_chat_widget_reply` in `src/dspy/signatures.py` gets a `widget_context` field so the AI knows which branch the visitor came from
- **Caroline's avatar photo** — served as a static asset at `/static/img/aria-avatar.jpg` (download once from HeyGen, commit to repo)

### What Stays the Same

- `/api/v1/chat/submit` endpoint and rate limiting
- `EnterpriseInquiry` model (no migration needed)
- Feature gate and quota checks

---

## Widget State Machine

```text
CLOSED
  └─ [5-second delay on page load] ──► GREETING
                                          ├─ "See how it works"  ──► DEMO
                                          ├─ "Start free trial"  ──► REDIRECT (signup page)
                                          └─ "Talk to someone"   ──► TALK_ASK_NAME
                                                                        └─ [name entered] ──► TALK_ASK_EMAIL
                                                                                               └─ [email entered] ──► TALK_CHAT
```

`DEMO` opens a free-text chat session using the existing `/api/v1/chat/submit` flow.
`TALK_CHAT` routes through the same endpoint but also creates an `EnterpriseInquiry` record after email is captured.

---

## Widget Sections

### Bubble (always visible when CLOSED)

- Bottom-right, 64 × 64 px circle
- Shows Caroline's avatar photo (`/static/img/aria-avatar.jpg`)
- Red badge dot appears after 5 s to draw attention (disappears once opened)
- Click opens to GREETING state

### Greeting Panel

```text
┌─────────────────────────────────┐
│  [avatar 48px]  Aria from       │
│                 InboxIQ      ×  │
├─────────────────────────────────┤
│                                 │
│  Hi there 👋                    │
│  I'm Aria, your InboxIQ guide.  │
│  What brings you here today?    │
│                                 │
│  ┌─────────────────────────┐    │
│  │  🎬  See how it works   │    │
│  └─────────────────────────┘    │
│  ┌─────────────────────────┐    │
│  │  🚀  Start free trial   │    │
│  └─────────────────────────┘    │
│  ┌─────────────────────────┐    │
│  │  💬  Talk to someone    │    │
│  └─────────────────────────┘    │
└─────────────────────────────────┘
```

- Width 360 px, auto-height (no fixed scroll pane)
- Dark header bar with avatar + "Aria from InboxIQ" + close ×

### Demo Branch

When "See how it works" is clicked:

1. Widget transitions to chat view (messages pane + free-text input)
2. Aria sends a canned opening message:
   > "InboxIQ triage emails automatically so your support team only sees what needs a human. I can answer questions about features, pricing, or anything else — what would you like to know?"
3. Visitor types freely; every message goes to `/api/v1/chat/submit` as normal
4. A soft CTA appears after the first AI reply:
   > "Want to try it yourself? [Start free trial →]"  (small link, not a button)

No name/email collected unless the visitor volunteers it in chat.

### Trial Branch

When "Start free trial" is clicked:

1. Widget closes immediately (no open state)
2. `window.location.href = '/auth/register'`

This is the only branch that navigates away.

### Talk Branch — Guided Collection

When "Talk to someone" is clicked, widget transitions to a guided chat. Aria drives the conversation:

**Step 1 — Ask name:**
> "Happy to connect you with our team! What's your name?"

Input: single-line text field labelled "Your name", submit button "Next →"

**Step 2 — Ask email (after name submitted):**
> "Nice to meet you, {name}! What's the best email to reach you on?"

Input: email field labelled "Your email", submit button "Next →"

**Step 3 — Free chat (after email submitted):**

1. Create `EnterpriseInquiry` record (POST to backend — see below)
2. Aria sends confirmation:
   > "Got it! Someone from the team will follow up at {email}. While you wait, is there anything I can help you with now?"
3. Widget opens free-text chat backed by `/api/v1/chat/submit`; name and email are included in the context payload

---

## Backend Changes

### 1. `/api/v1/chat/submit` — context field added

Add `branch` to the context payload the JS sends. The endpoint already ignores unknown context fields, so no server-side change is needed. The DSPy module uses it for tone.

### 2. New route: `POST /api/v1/enterprise-inquiry/chat`

Add to `src/api/v1/intake.py` (same blueprint as other public endpoints).

```python
@v1.route("/enterprise-inquiry/chat", methods=["POST"])
def create_chat_inquiry():
    """Create an EnterpriseInquiry from the chat widget talk-branch capture."""
    payload = request.get_json(silent=True) or {}
    name = sanitize_html(str(payload.get("name", "")).strip())[:200]
    email = str(payload.get("email", "")).strip().lower()[:255]
    account_id = str(payload.get("account_id", "2")).strip()

    if not name or not email:
        return jsonify({"error": "validation_error", "message": "Name and email required"}), 400
    if "@" not in email or "." not in email.split("@")[-1]:
        return jsonify({"error": "validation_error", "message": "Invalid email"}), 400

    from src.models.marketing import EnterpriseInquiry
    from src.extensions import db

    inquiry = EnterpriseInquiry(
        name=name,
        email=email,
        message="Chat widget — talk branch",
    )
    try:
        db.session.add(inquiry)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return jsonify({"ok": True})
```

### 3. DSPy signature — `build_chat_widget_reply` update

Add `branch` input field to `ChatWidgetReplySignature` in `src/dspy/signatures.py`:

```python
branch = dspy.InputField(desc="Widget branch visitor came from: 'demo' or 'talk'.")
```

The signature docstring gets a sentence:
> "If branch is 'talk', the visitor wants a human follow-up — be warm and reassuring, not salesy."

---

## Avatar Asset

Caroline's photo used throughout:

- Source: download the 512 × 512 square crop from HeyGen avatar list API or admin panel
- Save as: `src/static/img/aria-avatar.jpg`
- Commit to repo; served at `/static/img/aria-avatar.jpg`
- Referenced in JS as `/static/img/aria-avatar.jpg` (absolute path so widget works on any page)

No runtime API call to HeyGen — static file only.

---

## Error Handling

| Scenario | Behaviour |
| --- | --- |
| `/api/v1/chat/submit` fails | Show "Something went wrong — please try again." in chat, input stays editable |
| `/api/v1/enterprise-inquiry/chat` fails | Show "We couldn't save your details — please email us at support@kalevent.com" |
| Invalid email in talk branch | Inline validation: "Please enter a valid email address" under the input |
| Widget already opened; user returns | Preserve state in `sessionStorage` so conversation continues |
| Visitor dismisses (×) | Widget returns to CLOSED; does not auto-reopen this session |

---

## JS File Structure

`src/static/js/chat-widget.js` sections (all in one IIFE, no bundler):

1. **Config** — account, primaryColor, avatarUrl, signupUrl
2. **State** — `state` object: `{ phase, name, email, messages[] }`; persisted to `sessionStorage`
3. **DOM builder** — `createBubble()`, `createWindow()` — imperative DOM, no framework
4. **Phase renderers** — `renderGreeting()`, `renderDemo()`, `renderTalkAskName()`, `renderTalkAskEmail()`, `renderTalkChat()`
5. **API helpers** — `sendChatMessage(body, context)`, `createInquiry(name, email)`
6. **Event wiring** — bubble click, CTA clicks, form submits, close button
7. **Auto-open** — `setTimeout(openToGreeting, 5000)` — only if `sessionStorage` has no prior interaction

---

## Testing

- Open the InboxIQ homepage; after 5 s the widget opens to greeting
- Click "See how it works" → chat opens with canned message; type a question → AI reply arrives
- Refresh page → widget remembers conversation (sessionStorage)
- Click "Start free trial" → redirected to `/auth/register`
- Click "Talk to someone" → name prompt → enter name → email prompt → enter email → confirmation message appears → `EnterpriseInquiry` row exists in DB
- Enter invalid email in talk branch → validation error shown, not submitted
- Dismiss with × → widget closes; does not reopen on same page view
- New page load → widget auto-opens again after 5 s (new session)
