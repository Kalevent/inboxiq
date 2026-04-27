# LinkedIn Outreach Cadence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an agent-driven LinkedIn outreach system that discovers prospects, drafts personalised 3-message sequences, and delivers a daily digest email — the user only needs to send on LinkedIn and mark actions done.

**Architecture:** Three new Celery tasks (discover, draft, digest) run sequentially each morning. Two DSPy scripts generate messages and match blog posts. A Marketing Ops queue UI and a mark-as-sent route handle status progression. ICP criteria live in a new `ICPConfig` model, not in code.

**Tech Stack:** Python 3.11, Flask blueprints, SQLAlchemy, Celery + crontab, DSPy ChainOfThought, SMTP via existing `src/notifications/emails.py`

---

## File Map

| Action | File | Responsibility |
| --- | --- | --- |
| Modify | `src/models/campaigns.py` | Add `LinkedInProspect` model |
| Modify | `src/models/marketing.py` | Add `ICPConfig` model |
| Modify | `src/models/leads.py` | Add `linkedin_url` column |
| Modify | `src/models/__init__.py` | Re-export new models |
| Create | `src/tasks/linkedin.py` | 3 Celery tasks: discover, draft, digest |
| Modify | `src/notifications/emails.py` | Add `send_linkedin_digest` function |
| Create | `src/api/v1/linkedin.py` | Mark-as-sent + manual add endpoints |
| Modify | `src/marketing_ops/routes.py` | Add linkedin queue + ICP settings routes |
| Create | `src/templates/admin/section_linkedin.html` | Queue UI + ICP settings panel |
| Modify | `src/templates/marketing_ops.html` | Include linkedin section |
| Modify | `src/celery_inboxiq.py` | Register 3 tasks in beat_schedule |
| Create | `skills/linkedin_cadence/scripts/draft_messages.py` | DSPy MessageDrafterModule |
| Create | `skills/linkedin_cadence/scripts/match_post.py` | DSPy BlogPostMatcherModule |
| Modify | `skills/linkedin_cadence/skill.md` | Flesh out the skill document |
| Create | `tests/linkedin/__init__.py` | Test package |
| Create | `tests/linkedin/conftest.py` | App fixture |
| Create | `tests/linkedin/test_models.py` | Model unit tests |
| Create | `tests/linkedin/test_tasks.py` | Task logic tests |

---

## Task 1: `LinkedInProspect` Model

**Files:**
- Modify: `src/models/campaigns.py`
- Modify: `src/models/__init__.py`
- Create: `tests/linkedin/__init__.py`
- Create: `tests/linkedin/conftest.py`
- Create: `tests/linkedin/test_models.py`

- [ ] **Step 1: Write the failing test**

Create `tests/linkedin/__init__.py` (empty) and `tests/linkedin/conftest.py`:

```python
# tests/linkedin/conftest.py
import pytest
from src.app import create_app
from src.extensions import db as _db


@pytest.fixture
def app():
    app = create_app()
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SECRET_KEY"] = "test-secret"
    with app.app_context():
        _db.create_all()
        yield app
        _db.drop_all()


@pytest.fixture
def db(app):
    return _db
```

Create `tests/linkedin/test_models.py`:

```python
from src.models.campaigns import LinkedInProspect


def test_linkedin_prospect_defaults(db):
    p = LinkedInProspect(
        account_id=1,
        name="Alice Smith",
        linkedin_url="https://linkedin.com/in/alice",
    )
    db.session.add(p)
    db.session.commit()
    assert p.status == "pending"
    assert p.source == "auto"
    assert p.id is not None


def test_linkedin_prospect_unique_url_per_account(db):
    p1 = LinkedInProspect(account_id=1, name="Alice", linkedin_url="https://linkedin.com/in/alice")
    p2 = LinkedInProspect(account_id=1, name="Alice Dup", linkedin_url="https://linkedin.com/in/alice")
    db.session.add(p1)
    db.session.commit()
    db.session.add(p2)
    import pytest
    with pytest.raises(Exception):
        db.session.commit()


def test_linkedin_prospect_same_url_different_account(db):
    p1 = LinkedInProspect(account_id=1, name="Alice", linkedin_url="https://linkedin.com/in/alice")
    p2 = LinkedInProspect(account_id=2, name="Alice", linkedin_url="https://linkedin.com/in/alice")
    db.session.add_all([p1, p2])
    db.session.commit()
    assert p1.id != p2.id
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/linkedin/test_models.py -v
```

Expected: `ImportError` — `LinkedInProspect` not defined yet.

- [ ] **Step 3: Add `LinkedInProspect` to `src/models/campaigns.py`**

Add this import at the top of the file (after existing imports):

```python
from uuid import uuid4
from datetime import datetime
```

Then append at the bottom of `src/models/campaigns.py`:

```python
class LinkedInProspect(db.Model):
    """Tracks a LinkedIn prospect through the 3-message outreach cadence."""
    __tablename__ = "linkedin_prospects"
    __table_args__ = (
        db.UniqueConstraint("account_id", "linkedin_url", name="uq_li_prospect_account_url"),
        db.Index("idx_li_prospect_account_status", "account_id", "status"),
        db.Index("idx_li_prospect_due", "message_2_due_at", "message_3_due_at"),
    )

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()))
    account_id = db.Column(db.Integer, nullable=False)
    lead_id = db.Column(db.String(64), db.ForeignKey("leads.id"), nullable=True)
    name = db.Column(db.String(255), nullable=False)
    company_name = db.Column(db.String(255), nullable=True)
    job_title = db.Column(db.String(255), nullable=True)
    industry = db.Column(db.String(100), nullable=True)
    linkedin_url = db.Column(db.String(500), nullable=False)
    source = db.Column(db.String(20), nullable=False, default="auto")
    status = db.Column(
        db.Enum(
            "pending",
            "connection_sent",
            "connected",
            "message_2_sent",
            "message_3_sent",
            "replied",
            "qualified",
            "disqualified",
            name="linkedin_prospect_status_enum",
        ),
        nullable=False,
        default="pending",
    )
    fit_score = db.Column(db.Integer, nullable=True)
    connection_sent_at = db.Column(db.DateTime(timezone=True), nullable=True)
    connected_at = db.Column(db.DateTime(timezone=True), nullable=True)
    message_2_due_at = db.Column(db.DateTime(timezone=True), nullable=True)
    message_2_sent_at = db.Column(db.DateTime(timezone=True), nullable=True)
    message_3_due_at = db.Column(db.DateTime(timezone=True), nullable=True)
    message_3_sent_at = db.Column(db.DateTime(timezone=True), nullable=True)
    msg_1_draft = db.Column(db.Text, nullable=True)
    msg_2_draft = db.Column(db.Text, nullable=True)
    msg_3_draft = db.Column(db.Text, nullable=True)
    suggested_post_id = db.Column(db.String(64), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
```

- [ ] **Step 4: Re-export from `src/models/__init__.py`**

Find the campaigns import line and add `LinkedInProspect`:

```python
from src.models.campaigns import (
    CampaignSender, HunterDomainCache, EmailCampaign,
    EmailOutreach, NurtureEmailSend, LinkedInProspect,
)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/linkedin/test_models.py -v
```

Expected: All 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/models/campaigns.py src/models/__init__.py tests/linkedin/
git commit -m "feat(linkedin): add LinkedInProspect model"
```

---

## Task 2: `ICPConfig` Model

**Files:**
- Modify: `src/models/marketing.py`
- Modify: `src/models/__init__.py`
- Modify: `tests/linkedin/test_models.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/linkedin/test_models.py`:

```python
from src.models.marketing import ICPConfig


def test_icp_config_defaults(db):
    config = ICPConfig(account_id=1)
    db.session.add(config)
    db.session.commit()
    assert config.company_size_min == 10
    assert config.company_size_max == 50
    assert "Founder" in config.titles
    assert "B2B SaaS" in config.industries


def test_icp_config_one_per_account(db):
    c1 = ICPConfig(account_id=1)
    c2 = ICPConfig(account_id=1)
    db.session.add(c1)
    db.session.commit()
    db.session.add(c2)
    import pytest
    with pytest.raises(Exception):
        db.session.commit()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/linkedin/test_models.py::test_icp_config_defaults -v
```

Expected: `ImportError` — `ICPConfig` not defined yet.

- [ ] **Step 3: Add `ICPConfig` to `src/models/marketing.py`**

Append at the bottom of `src/models/marketing.py`:

```python
class ICPConfig(db.Model):
    """Per-account ICP criteria used by the LinkedIn discovery task."""
    __tablename__ = "icp_configs"

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()))
    account_id = db.Column(db.Integer, nullable=False, unique=True)
    titles = db.Column(
        db.JSON,
        nullable=False,
        default=lambda: ["Founder", "Head of Support", "Operations Lead", "Customer Success Lead"],
    )
    industries = db.Column(db.JSON, nullable=False, default=lambda: ["B2B SaaS", "Software"])
    company_size_min = db.Column(db.Integer, nullable=False, default=10)
    company_size_max = db.Column(db.Integer, nullable=False, default=50)
    geographies = db.Column(db.JSON, nullable=False, default=lambda: ["UK", "US", "Nigeria"])
    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
```

Ensure `from uuid import uuid4` and `from datetime import datetime` are imported at the top of `src/models/marketing.py`.

- [ ] **Step 4: Re-export from `src/models/__init__.py`**

Add `ICPConfig` to the marketing imports line.

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/linkedin/test_models.py -v
```

Expected: All 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/models/marketing.py src/models/__init__.py tests/linkedin/test_models.py
git commit -m "feat(linkedin): add ICPConfig model"
```

---

## Task 3: Add `linkedin_url` to `Lead` + Run Migration

**Files:**
- Modify: `src/models/leads.py`

- [ ] **Step 1: Add the column to the Lead model**

In `src/models/leads.py`, find the `notes` column and add `linkedin_url` after it:

```python
notes = db.Column(db.Text, nullable=True)
linkedin_url = db.Column(db.String(500), nullable=True, index=True)
```

- [ ] **Step 2: Commit the model change**

```bash
git add src/models/leads.py
git commit -m "feat(linkedin): add linkedin_url to Lead model"
```

- [ ] **Step 3: ⚠️ USER ACTION REQUIRED — run migration**

```bash
flask db migrate -m "Add LinkedInProspect, ICPConfig, Lead.linkedin_url"
flask db upgrade
```

Review the generated migration in `src/migrations/versions/` before running `upgrade`. Confirm it creates `linkedin_prospects`, `icp_configs`, and adds `linkedin_url` to `leads`.

---

## Task 4: DSPy Scripts

**Files:**
- Create: `skills/linkedin_cadence/scripts/draft_messages.py`
- Create: `skills/linkedin_cadence/scripts/match_post.py`

- [ ] **Step 1: Create `skills/linkedin_cadence/scripts/draft_messages.py`**

```python
"""
Message Drafter — DSPy Module

Drafts all three LinkedIn messages for a prospect in one ChainOfThought call.
Run standalone: python -m skills.linkedin_cadence.scripts.draft_messages
"""
import dspy


class MessageDrafterSignature(dspy.Signature):
    """Draft three LinkedIn messages for a B2B SaaS outreach sequence."""

    prospect_name = dspy.InputField(desc="Prospect's first name")
    job_title = dspy.InputField(desc="Prospect's job title")
    company_name = dspy.InputField(desc="Prospect's company name")
    industry = dspy.InputField(desc="Prospect's industry")
    product_name = dspy.InputField(desc="Your product name")

    msg_1 = dspy.OutputField(
        desc=(
            "LinkedIn connection request message. Max 300 characters. "
            "Mention shared context or relevant pain point. "
            "No pitch. No product mention. Warm and human."
        )
    )
    msg_2 = dspy.OutputField(
        desc=(
            "Follow-up message sent 3 days after connecting. Max 500 characters. "
            "Share a useful insight or blog post (placeholder: [POST_TITLE] at [POST_URL]). "
            "No ask. Pure value."
        )
    )
    msg_3 = dspy.OutputField(
        desc=(
            "Soft ask sent 5 days after message 2. Max 400 characters. "
            "One CTA only: would a 15-minute call make sense? "
            "Acknowledge they are busy. No pressure."
        )
    )


class MessageDrafterModule(dspy.Module):
    """Drafts all three LinkedIn outreach messages in a single DSPy call."""

    def __init__(self):
        super().__init__()
        self.draft = dspy.ChainOfThought(MessageDrafterSignature)

    def forward(
        self,
        prospect_name: str,
        job_title: str,
        company_name: str,
        industry: str,
        product_name: str = "InboxIQ",
    ):
        return self.draft(
            prospect_name=prospect_name,
            job_title=job_title,
            company_name=company_name,
            industry=industry,
            product_name=product_name,
        )


if __name__ == "__main__":
    from src.dspy import _configure_dspy
    _configure_dspy()

    module = MessageDrafterModule()
    result = module(
        prospect_name="Sarah",
        job_title="Head of Support",
        company_name="Acme SaaS",
        industry="B2B SaaS",
    )
    print(f"Message 1 ({len(result.msg_1)} chars):\n{result.msg_1}\n")
    print(f"Message 2 ({len(result.msg_2)} chars):\n{result.msg_2}\n")
    print(f"Message 3 ({len(result.msg_3)} chars):\n{result.msg_3}\n")
```

- [ ] **Step 2: Create `skills/linkedin_cadence/scripts/match_post.py`**

```python
"""
Blog Post Matcher — DSPy Module

Selects the most relevant published blog post for a prospect's message 2.
Run standalone: python -m skills.linkedin_cadence.scripts.match_post
"""
import dspy


class BlogPostMatcherSignature(dspy.Signature):
    """Select the most relevant blog post to share with a LinkedIn prospect."""

    prospect_industry = dspy.InputField(desc="Prospect's industry")
    job_title = dspy.InputField(desc="Prospect's job title")
    posts_json = dspy.InputField(
        desc='JSON array of published posts: [{"slug": "...", "title": "...", "primary_keyword": "..."}]'
    )

    selected_slug = dspy.OutputField(desc="Slug of the best matching post from the posts_json array")
    reason = dspy.OutputField(
        desc="One sentence explaining why this post is relevant to this prospect's role and industry"
    )


class BlogPostMatcherModule(dspy.Module):
    """Selects the best published blog post for a LinkedIn prospect."""

    def __init__(self):
        super().__init__()
        self.match = dspy.ChainOfThought(BlogPostMatcherSignature)

    def forward(self, prospect_industry: str, job_title: str, posts_json: str):
        return self.match(
            prospect_industry=prospect_industry,
            job_title=job_title,
            posts_json=posts_json,
        )


if __name__ == "__main__":
    import json
    from src.dspy import _configure_dspy
    _configure_dspy()

    module = BlogPostMatcherModule()
    posts = [
        {"slug": "customer-support-automation-benefits", "title": "Key Benefits of Customer Support Automation for B2B SaaS", "primary_keyword": "customer support automation"},
        {"slug": "post-purchase-strategies", "title": "Top 5 Post-Purchase Strategies for E-commerce Loyalty", "primary_keyword": "post-purchase strategies"},
    ]
    result = module(
        prospect_industry="B2B SaaS",
        job_title="Head of Support",
        posts_json=json.dumps(posts),
    )
    print(f"Selected: {result.selected_slug}")
    print(f"Reason:   {result.reason}")
```

- [ ] **Step 3: Commit**

```bash
git add skills/linkedin_cadence/scripts/
git commit -m "feat(linkedin): add MessageDrafter and BlogPostMatcher DSPy modules"
```

---

## Task 5: `linkedin.discover_prospects` Task

**Files:**
- Create: `src/tasks/linkedin.py`
- Create: `tests/linkedin/test_tasks.py`

- [ ] **Step 1: Write the failing test**

Create `tests/linkedin/test_tasks.py`:

```python
from unittest.mock import patch, MagicMock


def test_discover_prospects_creates_record_for_qualifying_lead(app):
    """A Lead with source=linkedin and fit_score >= 7 becomes a LinkedInProspect."""
    with app.app_context():
        from src.extensions import db
        from src.models.leads import Lead
        from src.models.campaigns import LinkedInProspect
        from datetime import datetime

        lead = Lead(
            id="lead-001",
            account_id=1,
            name="Alice Smith",
            email="alice@acmesaas.com",
            company_name="Acme SaaS",
            source="linkedin",
            linkedin_url="https://linkedin.com/in/alice",
            status="New Lead",
            fit_score=8,
        )
        db.session.add(lead)
        db.session.commit()

        from src.tasks.linkedin import discover_prospects
        discover_prospects()

        prospect = db.session.query(LinkedInProspect).filter_by(
            linkedin_url="https://linkedin.com/in/alice", account_id=1
        ).first()
        assert prospect is not None
        assert prospect.status == "pending"
        assert prospect.source == "auto"


def test_discover_prospects_skips_low_fit_score(app):
    """Leads with fit_score < 7 are not added to the queue."""
    with app.app_context():
        from src.extensions import db
        from src.models.leads import Lead
        from src.models.campaigns import LinkedInProspect

        lead = Lead(
            id="lead-002",
            account_id=1,
            name="Bob Jones",
            email="bob@example.com",
            source="linkedin",
            linkedin_url="https://linkedin.com/in/bobjones",
            status="New Lead",
            fit_score=5,
        )
        db.session.add(lead)
        db.session.commit()

        from src.tasks.linkedin import discover_prospects
        discover_prospects()

        prospect = db.session.query(LinkedInProspect).filter_by(
            linkedin_url="https://linkedin.com/in/bobjones"
        ).first()
        assert prospect is None


def test_discover_prospects_no_duplicate(app):
    """Running discover twice does not create a second LinkedInProspect."""
    with app.app_context():
        from src.extensions import db
        from src.models.leads import Lead
        from src.models.campaigns import LinkedInProspect

        lead = Lead(
            id="lead-003",
            account_id=1,
            name="Carol White",
            email="carol@example.com",
            source="linkedin",
            linkedin_url="https://linkedin.com/in/carolwhite",
            status="New Lead",
            fit_score=9,
        )
        db.session.add(lead)
        db.session.commit()

        from src.tasks.linkedin import discover_prospects
        discover_prospects()
        discover_prospects()

        count = db.session.query(LinkedInProspect).filter_by(
            linkedin_url="https://linkedin.com/in/carolwhite", account_id=1
        ).count()
        assert count == 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/linkedin/test_tasks.py::test_discover_prospects_creates_record_for_qualifying_lead -v
```

Expected: `ImportError` — `src.tasks.linkedin` not defined.

- [ ] **Step 3: Create `src/tasks/linkedin.py`** with the discover task

```python
"""LinkedIn outreach cadence tasks."""
import logging

from celery import shared_task

from src.extensions import db

log = logging.getLogger(__name__)

_ICP_DEFAULTS = {
    "titles": ["Founder", "Head of Support", "Operations Lead", "Customer Success Lead"],
    "industries": ["B2B SaaS", "Software"],
    "company_size_min": 10,
    "company_size_max": 50,
    "geographies": ["UK", "US", "Nigeria"],
}


def _load_icp(account_id: int) -> dict:
    from src.models.marketing import ICPConfig
    config = db.session.query(ICPConfig).filter_by(account_id=account_id).first()
    if not config:
        return _ICP_DEFAULTS
    return {
        "titles": config.titles or _ICP_DEFAULTS["titles"],
        "industries": config.industries or _ICP_DEFAULTS["industries"],
        "company_size_min": config.company_size_min,
        "company_size_max": config.company_size_max,
        "geographies": config.geographies or _ICP_DEFAULTS["geographies"],
    }


@shared_task(name="linkedin.discover_prospects")
def discover_prospects():
    """
    Promote qualifying Leads into the LinkedIn outreach queue.
    Runs daily at 7:00am. Idempotent — safe to re-run.
    """
    from src.models.leads import Lead
    from src.models.campaigns import LinkedInProspect

    # Fetch all distinct account_ids that have LinkedIn leads
    account_ids = [
        r[0] for r in db.session.query(Lead.account_id).filter(
            Lead.account_id.isnot(None),
            Lead.linkedin_url.isnot(None),
            Lead.outreach_unsubscribed_at.is_(None),
            Lead.deleted.is_(False),
        ).distinct().all()
    ]

    created = 0
    for account_id in account_ids:
        icp = _load_icp(account_id)
        leads = db.session.query(Lead).filter(
            Lead.account_id == account_id,
            Lead.linkedin_url.isnot(None),
            Lead.fit_score >= 7,
            Lead.outreach_unsubscribed_at.is_(None),
            Lead.deleted.is_(False),
        ).all()

        for lead in leads:
            exists = db.session.query(LinkedInProspect).filter_by(
                account_id=account_id,
                linkedin_url=lead.linkedin_url,
            ).first()
            if exists:
                continue

            prospect = LinkedInProspect(
                account_id=account_id,
                lead_id=lead.id,
                name=lead.name,
                company_name=lead.company_name,
                job_title=None,
                industry=lead.industry,
                linkedin_url=lead.linkedin_url,
                source="auto",
                status="pending",
                fit_score=lead.fit_score,
            )
            try:
                db.session.add(prospect)
                db.session.commit()
                created += 1
            except Exception:
                db.session.rollback()
                log.exception("Failed to create LinkedInProspect for lead %s", lead.id)

    log.info("linkedin.discover_prospects: created %d new prospects", created)
    return {"created": created}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/linkedin/test_tasks.py::test_discover_prospects_creates_record_for_qualifying_lead \
       tests/linkedin/test_tasks.py::test_discover_prospects_skips_low_fit_score \
       tests/linkedin/test_tasks.py::test_discover_prospects_no_duplicate -v
```

Expected: All 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tasks/linkedin.py tests/linkedin/test_tasks.py
git commit -m "feat(linkedin): add discover_prospects task"
```

---

## Task 6: `linkedin.draft_messages` Task

**Files:**
- Modify: `src/tasks/linkedin.py`
- Modify: `tests/linkedin/test_tasks.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/linkedin/test_tasks.py`:

```python
def test_draft_messages_saves_drafts(app):
    """draft_messages_task sets msg_1_draft, msg_2_draft, msg_3_draft on pending prospects."""
    with app.app_context():
        from src.extensions import db
        from src.models.campaigns import LinkedInProspect
        from unittest.mock import patch, MagicMock

        prospect = LinkedInProspect(
            account_id=1,
            name="Dave Chen",
            company_name="BuildStack",
            job_title="Founder",
            industry="B2B SaaS",
            linkedin_url="https://linkedin.com/in/davechen",
            status="pending",
        )
        db.session.add(prospect)
        db.session.commit()

        mock_draft = MagicMock()
        mock_draft.msg_1 = "Hi Dave, would love to connect."
        mock_draft.msg_2 = "Thought this post might be useful."
        mock_draft.msg_3 = "Would a 15-min call make sense?"

        mock_post_match = MagicMock()
        mock_post_match.selected_slug = "customer-support-automation-benefits"
        mock_post_match.reason = "Relevant to Founder in B2B SaaS."

        with patch("src.tasks.linkedin._configure_dspy"), \
             patch("src.tasks.linkedin.MessageDrafterModule") as MockDrafter, \
             patch("src.tasks.linkedin.BlogPostMatcherModule") as MockMatcher, \
             patch("src.tasks.linkedin._get_published_posts", return_value=[]):
            MockDrafter.return_value.return_value = mock_draft
            MockMatcher.return_value.return_value = mock_post_match

            from src.tasks.linkedin import draft_messages_task
            draft_messages_task()

        db.session.refresh(prospect)
        assert prospect.msg_1_draft == "Hi Dave, would love to connect."
        assert prospect.msg_2_draft == "Thought this post might be useful."
        assert prospect.msg_3_draft == "Would a 15-min call make sense?"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/linkedin/test_tasks.py::test_draft_messages_saves_drafts -v
```

Expected: `ImportError` — `draft_messages_task` not defined.

- [ ] **Step 3: Add `draft_messages_task` to `src/tasks/linkedin.py`**

Add these imports at the top of `src/tasks/linkedin.py`:

```python
import json
from src.dspy import _configure_dspy
from skills.linkedin_cadence.scripts.draft_messages import MessageDrafterModule
from skills.linkedin_cadence.scripts.match_post import BlogPostMatcherModule
```

Then append the function and helper to `src/tasks/linkedin.py`:

```python
def _get_published_posts() -> list[dict]:
    """Return [{slug, title, primary_keyword}] for all published blog posts."""
    from src.models.content import BlogPost
    posts = db.session.query(
        BlogPost.slug, BlogPost.title, BlogPost.primary_keyword
    ).filter_by(status="published").all()
    return [{"slug": p.slug, "title": p.title, "primary_keyword": p.primary_keyword or ""} for p in posts]


def _get_post_by_slug(slug: str):
    from src.models.content import BlogPost
    return db.session.query(BlogPost).filter_by(slug=slug, status="published").first()


@shared_task(name="linkedin.draft_messages")
def draft_messages_task():
    """
    Draft all 3 LinkedIn messages for pending prospects with no drafts.
    Runs daily at 7:30am, after discover_prospects.
    """
    from src.models.campaigns import LinkedInProspect

    prospects = db.session.query(LinkedInProspect).filter(
        LinkedInProspect.status == "pending",
        LinkedInProspect.msg_1_draft.is_(None),
    ).all()

    if not prospects:
        log.info("linkedin.draft_messages: no prospects to draft")
        return {"drafted": 0}

    _configure_dspy()
    drafter = MessageDrafterModule()
    matcher = BlogPostMatcherModule()
    posts = _get_published_posts()
    posts_json = json.dumps(posts)

    drafted = 0
    for prospect in prospects:
        try:
            draft_result = drafter(
                prospect_name=prospect.name.split()[0],
                job_title=prospect.job_title or "professional",
                company_name=prospect.company_name or "your company",
                industry=prospect.industry or "SaaS",
            )

            suggested_post_id = None
            match_reason = None
            if posts:
                match_result = matcher(
                    prospect_industry=prospect.industry or "SaaS",
                    job_title=prospect.job_title or "professional",
                    posts_json=posts_json,
                )
                post = _get_post_by_slug(match_result.selected_slug)
                if post:
                    suggested_post_id = post.id
                    match_reason = match_result.reason
                    msg_2 = draft_result.msg_2.replace(
                        "[POST_TITLE]", post.title
                    ).replace(
                        "[POST_URL]", f"https://kalevent.com/blog/{post.slug}"
                    )
                else:
                    msg_2 = draft_result.msg_2
            else:
                msg_2 = draft_result.msg_2

            prospect.msg_1_draft = draft_result.msg_1
            prospect.msg_2_draft = msg_2
            prospect.msg_3_draft = draft_result.msg_3
            prospect.suggested_post_id = suggested_post_id
            if match_reason:
                prospect.notes = (prospect.notes or "") + f"\n[post match] {match_reason}"

            db.session.commit()
            drafted += 1
        except Exception:
            db.session.rollback()
            log.exception("Failed to draft messages for prospect %s", prospect.id)

    log.info("linkedin.draft_messages: drafted %d prospects", drafted)
    return {"drafted": drafted}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/linkedin/test_tasks.py::test_draft_messages_saves_drafts -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tasks/linkedin.py tests/linkedin/test_tasks.py
git commit -m "feat(linkedin): add draft_messages_task"
```

---

## Task 7: `send_linkedin_digest` Email Function

**Files:**
- Modify: `src/notifications/emails.py`

- [ ] **Step 1: Add `send_linkedin_digest` to `src/notifications/emails.py`**

Append to `src/notifications/emails.py`:

```python
def send_linkedin_digest(to_email: str, prospects: list[dict], date_label: str) -> bool:
    """
    Send the daily LinkedIn outreach digest email.

    Each prospect dict must have:
        name, company_name, job_title, linkedin_url, action_label,
        msg_draft, prospect_id
    Optional keys:
        suggested_post_title, suggested_post_url, match_reason
    """
    from flask import current_app
    app = current_app
    host = app.config.get("SMTP_HOST")
    if not host:
        app.logger.info({"event": "email.disabled", "reason": "SMTP_HOST not configured"})
        return False

    if not prospects:
        return False

    port = app.config.get("SMTP_PORT")
    user = app.config.get("SMTP_USER")
    password = app.config.get("SMTP_PASSWORD")
    use_tls = app.config.get("SMTP_USE_TLS", True)
    use_ssl = app.config.get("SMTP_USE_SSL", False)
    mail_from = app.config.get("MAIL_FROM", "noreply@kalevent.com")
    base_url = app.config.get("BASE_URL", "https://kalevent.com")

    subject = f"LinkedIn Outreach — {len(prospects)} action{'s' if len(prospects) != 1 else ''} ready ({date_label})"

    sections_html = []
    sections_text = []

    for p in prospects:
        advance_url = f"{base_url}/marketing/linkedin/advance/{p['prospect_id']}"
        post_html = ""
        post_text = ""
        if p.get("suggested_post_title"):
            post_html = (
                f"<p style='margin:4px 0;font-size:13px;color:#94a3b8;'>"
                f"Sharing: <a href='{p['suggested_post_url']}' style='color:#818cf8;'>{p['suggested_post_title']}</a>"
                f"<br><em>{p.get('match_reason', '')}</em></p>"
            )
            post_text = f"\nSharing: {p['suggested_post_title']} ({p['suggested_post_url']})\nWhy: {p.get('match_reason', '')}"

        sections_html.append(f"""
<div style="border:1px solid #1e293b;border-radius:8px;padding:16px;margin-bottom:16px;background:#0f172a;">
  <p style="margin:0 0 4px;font-weight:600;font-size:15px;color:#f1f5f9;">{p['name']} &middot; {p['job_title']} &middot; {p['company_name']}</p>
  <p style="margin:0 0 8px;font-size:12px;"><a href="{p['linkedin_url']}" style="color:#818cf8;">{p['linkedin_url']}</a></p>
  <p style="margin:0 0 8px;font-size:13px;font-weight:500;color:#e2e8f0;">Action: {p['action_label']}</p>
  {post_html}
  <div style="background:#1e293b;border-radius:6px;padding:12px;margin:8px 0;font-size:13px;color:#cbd5e1;font-style:italic;">
    {p['msg_draft'].replace(chr(10), '<br>')}
  </div>
  <a href="{advance_url}" style="display:inline-block;background:#6366f1;color:#fff;text-decoration:none;padding:6px 14px;border-radius:6px;font-size:13px;font-weight:500;">Mark as sent &rarr;</a>
</div>""")

        sections_text.append(
            f"\n{'─'*60}\n"
            f"{p['name']} · {p['job_title']} · {p['company_name']}\n"
            f"{p['linkedin_url']}\n\n"
            f"Action: {p['action_label']}{post_text}\n\n"
            f"{p['msg_draft']}\n\n"
            f"Mark as sent: {advance_url}\n"
        )

    html_body = f"""<!DOCTYPE html><html><body style="background:#020617;color:#f1f5f9;font-family:sans-serif;padding:24px;max-width:640px;margin:0 auto;">
<h2 style="color:#818cf8;margin-bottom:4px;">LinkedIn Outreach</h2>
<p style="color:#94a3b8;margin-top:0;">{len(prospects)} action{'s' if len(prospects) != 1 else ''} ready &mdash; {date_label}</p>
{''.join(sections_html)}
<p style="font-size:11px;color:#475569;margin-top:24px;">Manage your queue: <a href="{base_url}/marketing/linkedin" style="color:#818cf8;">{base_url}/marketing/linkedin</a></p>
</body></html>"""

    text_body = f"LinkedIn Outreach — {len(prospects)} actions ready — {date_label}\n{''.join(sections_text)}"

    import smtplib
    from email.message import EmailMessage
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = mail_from
    msg["To"] = to_email
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    try:
        if use_ssl:
            with smtplib.SMTP_SSL(host, port) as smtp:
                smtp.login(user, password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(host, port) as smtp:
                if use_tls:
                    smtp.starttls()
                smtp.login(user, password)
                smtp.send_message(msg)
        return True
    except Exception:
        import logging
        logging.getLogger(__name__).exception("send_linkedin_digest failed")
        return False
```

- [ ] **Step 2: Commit**

```bash
git add src/notifications/emails.py
git commit -m "feat(linkedin): add send_linkedin_digest email function"
```

---

## Task 8: `linkedin.send_digest` Task + Celery Schedule

**Files:**
- Modify: `src/tasks/linkedin.py`
- Modify: `src/celery_inboxiq.py`

- [ ] **Step 1: Append `send_digest_task` to `src/tasks/linkedin.py`**

```python
@shared_task(name="linkedin.send_digest")
def send_digest_task():
    """
    Collect all prospects due for action today and email the digest.
    Runs daily at 8:00am, after draft_messages_task.
    """
    from datetime import datetime, timezone
    from src.models.campaigns import LinkedInProspect
    from src.models.content import BlogPost
    from src.notifications.emails import send_linkedin_digest
    from flask import current_app

    now = datetime.now(timezone.utc)
    notify_email = current_app.config.get("ADMIN_EMAILS", "").split(",")[0].strip()
    if not notify_email:
        log.warning("linkedin.send_digest: ADMIN_EMAILS not configured, skipping")
        return {"sent": False}

    due = []

    # Connection requests ready to send (pending with drafts)
    pending = db.session.query(LinkedInProspect).filter(
        LinkedInProspect.status == "pending",
        LinkedInProspect.msg_1_draft.isnot(None),
    ).all()
    for p in pending:
        due.append(_prospect_to_digest_item(p, "Send connection request", p.msg_1_draft))

    # Message 2 due
    msg2_due = db.session.query(LinkedInProspect).filter(
        LinkedInProspect.status == "connected",
        LinkedInProspect.message_2_due_at <= now,
        LinkedInProspect.msg_2_draft.isnot(None),
    ).all()
    for p in msg2_due:
        days_ago = (now - p.connected_at.replace(tzinfo=timezone.utc)).days if p.connected_at else "?"
        due.append(_prospect_to_digest_item(p, f"Send message 2 (connected {days_ago} days ago)", p.msg_2_draft, with_post=True))

    # Message 3 due
    msg3_due = db.session.query(LinkedInProspect).filter(
        LinkedInProspect.status == "message_2_sent",
        LinkedInProspect.message_3_due_at <= now,
        LinkedInProspect.msg_3_draft.isnot(None),
    ).all()
    for p in msg3_due:
        due.append(_prospect_to_digest_item(p, "Send message 3 — soft ask", p.msg_3_draft))

    # Replied — needs qualify/disqualify decision
    replied = db.session.query(LinkedInProspect).filter(
        LinkedInProspect.status == "replied",
    ).all()
    for p in replied:
        due.append(_prospect_to_digest_item(p, "Follow up — prospect replied, qualify or disqualify", p.msg_3_draft or ""))

    if not due:
        log.info("linkedin.send_digest: no actions due today")
        return {"sent": False, "count": 0}

    # Order: msg3 first, then msg2, then connection requests, then replied
    order = {"Send message 3": 0, "Send message 2": 1, "Send connection": 2, "Follow up": 3}
    due.sort(key=lambda x: next((v for k, v in order.items() if x["action_label"].startswith(k)), 4))

    date_label = now.strftime("%a %d %b")
    sent = send_linkedin_digest(notify_email, due, date_label)
    log.info("linkedin.send_digest: sent=%s count=%d", sent, len(due))
    return {"sent": sent, "count": len(due)}


def _prospect_to_digest_item(prospect, action_label: str, msg_draft: str, with_post: bool = False) -> dict:
    from src.models.content import BlogPost
    item = {
        "prospect_id": prospect.id,
        "name": prospect.name,
        "company_name": prospect.company_name or "",
        "job_title": prospect.job_title or "",
        "linkedin_url": prospect.linkedin_url,
        "action_label": action_label,
        "msg_draft": msg_draft or "",
    }
    if with_post and prospect.suggested_post_id:
        post = db.session.query(BlogPost).filter_by(id=prospect.suggested_post_id).first()
        if post:
            item["suggested_post_title"] = post.title
            item["suggested_post_url"] = f"https://kalevent.com/blog/{post.slug}"
            # Extract match reason from notes if saved
            notes = prospect.notes or ""
            for line in notes.splitlines():
                if line.startswith("[post match]"):
                    item["match_reason"] = line.replace("[post match]", "").strip()
                    break
    return item
```

- [ ] **Step 2: Register the 3 tasks in `src/celery_inboxiq.py`**

Inside the `beat_schedule` dict (after the existing entries), add:

```python
"linkedin_discover_prospects": {
    "task": "linkedin.discover_prospects",
    "schedule": crontab(hour=7, minute=0),
    "options": {"queue": "inbox"},
},
"linkedin_draft_messages": {
    "task": "linkedin.draft_messages",
    "schedule": crontab(hour=7, minute=30),
    "options": {"queue": "inbox"},
},
"linkedin_send_digest": {
    "task": "linkedin.send_digest",
    "schedule": crontab(hour=8, minute=0),
    "options": {"queue": "inbox"},
},
```

Also register the task module so Celery autodiscovers it. Find the `include` list in `celery_inboxiq.py` and add:

```python
"src.tasks.linkedin",
```

- [ ] **Step 3: Commit**

```bash
git add src/tasks/linkedin.py src/celery_inboxiq.py
git commit -m "feat(linkedin): add send_digest task and register Celery schedule"
```

---

## Task 9: Mark-as-Sent Route + Manual Add API

**Files:**
- Create: `src/api/v1/linkedin.py`
- Modify: `src/app.py`

- [ ] **Step 1: Create `src/api/v1/linkedin.py`**

```python
"""LinkedIn outreach API endpoints."""
import logging
from datetime import datetime, timedelta, timezone

from flask import Blueprint, g, jsonify, redirect, request, url_for
from flask_jwt_extended import jwt_required

from src.extensions import db
from src.models.campaigns import LinkedInProspect
from src.settings import login_required_settings

log = logging.getLogger(__name__)

linkedin_api_bp = Blueprint("linkedin_api", __name__, url_prefix="/api/v1/linkedin")
linkedin_ui_bp = Blueprint("linkedin_ui", __name__)

_STATUS_TRANSITIONS = {
    "pending": ("connection_sent", "connection_sent_at"),
    "connection_sent": ("connected", "connected_at"),
    "connected": ("message_2_sent", "message_2_sent_at"),
    "message_2_sent": ("message_3_sent", "message_3_sent_at"),
    "message_3_sent": ("replied", None),
    "replied": ("qualified", None),
}


def _advance_prospect(prospect: LinkedInProspect) -> bool:
    """Advance a prospect to the next status. Returns True on success."""
    transition = _STATUS_TRANSITIONS.get(prospect.status)
    if not transition:
        return False
    new_status, timestamp_field = transition
    now = datetime.now(timezone.utc)
    prospect.status = new_status
    prospect.updated_at = now
    if timestamp_field:
        setattr(prospect, timestamp_field, now)
    # Compute due dates when timestamps are set
    if timestamp_field == "connected_at":
        prospect.message_2_due_at = now + timedelta(days=3)
    if timestamp_field == "message_2_sent_at":
        prospect.message_3_due_at = now + timedelta(days=5)
    # Funnel integration
    if new_status in ("replied", "qualified") and prospect.lead_id:
        _advance_lead_stage(prospect.lead_id, new_status)
    return True


def _advance_lead_stage(lead_id: str, prospect_status: str):
    from src.models.leads import Lead
    lead = db.session.query(Lead).filter_by(id=lead_id).first()
    if not lead:
        return
    if prospect_status == "replied":
        lead.current_funnel_stage = "consideration"
    elif prospect_status == "qualified":
        lead.current_funnel_stage = "conversion"
    lead.updated_at = datetime.now(timezone.utc)


# Session-auth route — used from email "Mark as sent" links
@linkedin_ui_bp.route("/marketing/linkedin/advance/<prospect_id>")
@login_required_settings
def advance_prospect(prospect_id: str):
    account_id = getattr(g, "current_account_id", None)
    prospect = db.session.query(LinkedInProspect).filter_by(
        id=prospect_id, account_id=account_id
    ).first()
    if not prospect:
        return redirect("/marketing/linkedin")
    if _advance_prospect(prospect):
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            log.exception("Failed to advance prospect %s", prospect_id)
    return redirect("/marketing/linkedin")


# JWT API — used from the queue UI
@linkedin_api_bp.route("/prospects/<prospect_id>/advance", methods=["POST"])
@jwt_required()
def api_advance_prospect(prospect_id: str):
    from flask_jwt_extended import get_jwt_identity
    account_id = get_jwt_identity()
    prospect = db.session.query(LinkedInProspect).filter_by(
        id=prospect_id, account_id=account_id
    ).first()
    if not prospect:
        return jsonify({"error": "not found"}), 404
    if not _advance_prospect(prospect):
        return jsonify({"error": "no valid transition from current status"}), 400
    try:
        db.session.commit()
        return jsonify({"status": prospect.status})
    except Exception:
        db.session.rollback()
        log.exception("Failed to advance prospect %s", prospect_id)
        return jsonify({"error": "internal error"}), 500


@linkedin_api_bp.route("/prospects/<prospect_id>/disqualify", methods=["POST"])
@jwt_required()
def api_disqualify_prospect(prospect_id: str):
    from flask_jwt_extended import get_jwt_identity
    account_id = get_jwt_identity()
    prospect = db.session.query(LinkedInProspect).filter_by(
        id=prospect_id, account_id=account_id
    ).first()
    if not prospect:
        return jsonify({"error": "not found"}), 404
    prospect.status = "disqualified"
    prospect.updated_at = datetime.now(timezone.utc)
    try:
        db.session.commit()
        return jsonify({"status": "disqualified"})
    except Exception:
        db.session.rollback()
        return jsonify({"error": "internal error"}), 500


@linkedin_api_bp.route("/prospects", methods=["POST"])
@jwt_required()
def api_add_prospect():
    """Manually add a LinkedIn prospect."""
    from flask_jwt_extended import get_jwt_identity
    from src.tasks.linkedin import draft_messages_task
    account_id = get_jwt_identity()
    data = request.get_json(silent=True) or {}

    linkedin_url = (data.get("linkedin_url") or "").strip()
    name = (data.get("name") or "").strip()
    if not linkedin_url or not name:
        return jsonify({"error": "linkedin_url and name are required"}), 400
    if "linkedin.com" not in linkedin_url:
        return jsonify({"error": "linkedin_url must be a linkedin.com URL"}), 400

    existing = db.session.query(LinkedInProspect).filter_by(
        account_id=account_id, linkedin_url=linkedin_url
    ).first()
    if existing:
        return jsonify({"error": "prospect already in queue"}), 409

    prospect = LinkedInProspect(
        account_id=account_id,
        name=name,
        company_name=(data.get("company_name") or "").strip() or None,
        job_title=(data.get("job_title") or "").strip() or None,
        industry=(data.get("industry") or "").strip() or None,
        linkedin_url=linkedin_url,
        source="manual",
        status="pending",
        fit_score=data.get("fit_score"),
        notes=(data.get("notes") or "").strip() or None,
    )
    try:
        db.session.add(prospect)
        db.session.commit()
    except Exception:
        db.session.rollback()
        log.exception("Failed to add manual prospect")
        return jsonify({"error": "internal error"}), 500

    # Draft messages asynchronously
    draft_messages_task.delay()

    return jsonify({"id": prospect.id, "status": "pending"}), 201


@linkedin_api_bp.route("/prospects", methods=["GET"])
@jwt_required()
def api_list_prospects():
    from flask_jwt_extended import get_jwt_identity
    account_id = get_jwt_identity()
    status_filter = request.args.get("status")
    query = db.session.query(LinkedInProspect).filter_by(account_id=account_id)
    if status_filter:
        query = query.filter_by(status=status_filter)
    prospects = query.order_by(LinkedInProspect.created_at.desc()).limit(200).all()
    return jsonify([{
        "id": p.id,
        "name": p.name,
        "company_name": p.company_name,
        "job_title": p.job_title,
        "linkedin_url": p.linkedin_url,
        "status": p.status,
        "fit_score": p.fit_score,
        "source": p.source,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "message_2_due_at": p.message_2_due_at.isoformat() if p.message_2_due_at else None,
        "message_3_due_at": p.message_3_due_at.isoformat() if p.message_3_due_at else None,
    } for p in prospects])


@linkedin_api_bp.route("/icp", methods=["GET"])
@jwt_required()
def api_get_icp():
    from flask_jwt_extended import get_jwt_identity
    from src.models.marketing import ICPConfig
    account_id = get_jwt_identity()
    config = db.session.query(ICPConfig).filter_by(account_id=account_id).first()
    if not config:
        from src.tasks.linkedin import _ICP_DEFAULTS
        return jsonify(_ICP_DEFAULTS)
    return jsonify({
        "titles": config.titles,
        "industries": config.industries,
        "company_size_min": config.company_size_min,
        "company_size_max": config.company_size_max,
        "geographies": config.geographies,
    })


@linkedin_api_bp.route("/icp", methods=["POST"])
@jwt_required()
def api_save_icp():
    from flask_jwt_extended import get_jwt_identity
    from src.models.marketing import ICPConfig
    account_id = get_jwt_identity()
    data = request.get_json(silent=True) or {}
    config = db.session.query(ICPConfig).filter_by(account_id=account_id).first()
    if not config:
        config = ICPConfig(account_id=account_id)
        db.session.add(config)
    config.titles = data.get("titles", config.titles)
    config.industries = data.get("industries", config.industries)
    config.company_size_min = int(data.get("company_size_min", config.company_size_min))
    config.company_size_max = int(data.get("company_size_max", config.company_size_max))
    config.geographies = data.get("geographies", config.geographies)
    try:
        db.session.commit()
        return jsonify({"saved": True})
    except Exception:
        db.session.rollback()
        return jsonify({"error": "internal error"}), 500
```

- [ ] **Step 2: Register blueprints in `src/app.py`**

Find the blueprint registration section and add:

```python
from src.api.v1.linkedin import linkedin_api_bp, linkedin_ui_bp
app.register_blueprint(linkedin_api_bp)
app.register_blueprint(linkedin_ui_bp)
```

- [ ] **Step 3: Commit**

```bash
git add src/api/v1/linkedin.py src/app.py
git commit -m "feat(linkedin): add mark-as-sent, manual add, and ICP API endpoints"
```

---

## Task 10: Marketing Ops Queue UI

**Files:**
- Modify: `src/marketing_ops/routes.py`
- Create: `src/templates/admin/section_linkedin.html`
- Modify: `src/templates/marketing_ops.html`

- [ ] **Step 1: Add linkedin to valid sections in `src/marketing_ops/routes.py`**

```python
_VALID_SECTIONS = {"funnel", "content", "marketing", "campaigns", "linkedin"}
```

- [ ] **Step 2: Add linkedin to the sidebar and section include in `src/templates/marketing_ops.html`**

Find the sidebar nav buttons section and add after the existing nav items:

```html
<button class="sidebar-nav-item w-full text-left" data-section="linkedin">
  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M18 18.72a9.094 9.094 0 003.741-.479 3 3 0 00-4.682-2.72m.94 3.198l.001.031c0 .225-.012.447-.037.666A11.944 11.944 0 0112 21c-2.17 0-4.207-.576-5.963-1.584A6.062 6.062 0 016 18.719m12 0a5.971 5.971 0 00-.941-3.197m0 0A5.995 5.995 0 0012 12.75a5.995 5.995 0 00-5.058 2.772m0 0a3 3 0 00-4.681 2.72 8.986 8.986 0 003.74.477m.94-3.197a5.971 5.971 0 00-.94 3.197M15 6.75a3 3 0 11-6 0 3 3 0 016 0zm6 3a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0zm-13.5 0a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0z" /></svg>
  LinkedIn
</button>
```

Find the section includes block (near `{% include 'admin/section_funnel.html' %}`) and add:

```html
{% include 'admin/section_linkedin.html' %}
```

- [ ] **Step 3: Create `src/templates/admin/section_linkedin.html`**

```html
<div class="admin-section" id="section-linkedin">
  <div class="content-container">

    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h2 class="text-xl font-semibold text-slate-100">LinkedIn Outreach Queue</h2>
        <p class="text-sm text-slate-400 mt-1">Agent-drafted messages · Mark sent after you post on LinkedIn</p>
      </div>
      <button onclick="showAddProspectModal()" class="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium rounded-lg transition-colors">
        + Add Prospect
      </button>
    </div>

    <!-- Today's Actions -->
    <div id="li-today-section" class="mb-8">
      <h3 class="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">Today's Actions</h3>
      <div id="li-today-cards" class="space-y-3">
        <p class="text-slate-500 text-sm">Loading…</p>
      </div>
    </div>

    <!-- Full Queue -->
    <div>
      <div class="flex items-center justify-between mb-3">
        <h3 class="text-sm font-semibold text-slate-300 uppercase tracking-wider">Full Queue</h3>
        <div class="flex gap-2">
          <select id="li-status-filter" onchange="loadLinkedInQueue()" class="bg-slate-800 border border-slate-700 text-slate-300 text-sm rounded-lg px-3 py-1.5">
            <option value="">All statuses</option>
            <option value="pending">Pending</option>
            <option value="connection_sent">Connection sent</option>
            <option value="connected">Connected</option>
            <option value="message_2_sent">Message 2 sent</option>
            <option value="message_3_sent">Message 3 sent</option>
            <option value="replied">Replied</option>
            <option value="qualified">Qualified</option>
            <option value="disqualified">Disqualified</option>
          </select>
        </div>
      </div>
      <div class="overflow-x-auto rounded-lg border border-slate-800">
        <table class="w-full text-sm text-slate-300">
          <thead class="bg-slate-900 text-slate-400 text-xs uppercase">
            <tr>
              <th class="px-4 py-3 text-left">Name</th>
              <th class="px-4 py-3 text-left">Company</th>
              <th class="px-4 py-3 text-left">Title</th>
              <th class="px-4 py-3 text-left">Status</th>
              <th class="px-4 py-3 text-left">Fit</th>
              <th class="px-4 py-3 text-left">Source</th>
              <th class="px-4 py-3 text-left">Actions</th>
            </tr>
          </thead>
          <tbody id="li-queue-tbody">
            <tr><td colspan="7" class="px-4 py-6 text-center text-slate-500">Loading…</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- ICP Settings -->
    <div class="mt-10 border-t border-slate-800 pt-8">
      <h3 class="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-4">ICP Settings</h3>
      <p class="text-xs text-slate-500 mb-4">Defines who the discovery agent promotes into this queue. Changes take effect on the next 7am run.</p>
      <form id="icp-form" onsubmit="saveICP(event)" class="space-y-4 max-w-xl">
        <div>
          <label class="block text-xs text-slate-400 mb-1">Job Titles (comma-separated)</label>
          <input id="icp-titles" type="text" class="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200" />
        </div>
        <div>
          <label class="block text-xs text-slate-400 mb-1">Industries (comma-separated)</label>
          <input id="icp-industries" type="text" class="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200" />
        </div>
        <div class="flex gap-4">
          <div class="flex-1">
            <label class="block text-xs text-slate-400 mb-1">Company size min</label>
            <input id="icp-size-min" type="number" class="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200" />
          </div>
          <div class="flex-1">
            <label class="block text-xs text-slate-400 mb-1">Company size max</label>
            <input id="icp-size-max" type="number" class="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200" />
          </div>
        </div>
        <div>
          <label class="block text-xs text-slate-400 mb-1">Geographies (comma-separated)</label>
          <input id="icp-geos" type="text" class="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200" />
        </div>
        <button type="submit" class="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium rounded-lg transition-colors">Save ICP</button>
        <span id="icp-saved-msg" class="hidden text-green-400 text-sm ml-3">Saved</span>
      </form>
    </div>

  </div>
</div>

<!-- Add Prospect Modal -->
<div id="add-prospect-modal" class="hidden fixed inset-0 bg-black/60 z-50 flex items-center justify-center">
  <div class="bg-slate-900 border border-slate-700 rounded-xl p-6 w-full max-w-md">
    <h3 class="text-lg font-semibold text-slate-100 mb-4">Add Prospect Manually</h3>
    <form id="add-prospect-form" onsubmit="submitAddProspect(event)" class="space-y-3">
      <div>
        <label class="block text-xs text-slate-400 mb-1">LinkedIn URL *</label>
        <input id="ap-url" type="url" required placeholder="https://linkedin.com/in/..." class="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200" />
      </div>
      <div>
        <label class="block text-xs text-slate-400 mb-1">Full Name *</label>
        <input id="ap-name" type="text" required class="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200" />
      </div>
      <div>
        <label class="block text-xs text-slate-400 mb-1">Company *</label>
        <input id="ap-company" type="text" required class="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200" />
      </div>
      <div>
        <label class="block text-xs text-slate-400 mb-1">Job Title *</label>
        <input id="ap-title" type="text" required class="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200" />
      </div>
      <div>
        <label class="block text-xs text-slate-400 mb-1">Industry *</label>
        <input id="ap-industry" type="text" required class="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200" />
      </div>
      <div class="flex gap-3 pt-2">
        <button type="submit" class="flex-1 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium rounded-lg transition-colors">Add to Queue</button>
        <button type="button" onclick="hideAddProspectModal()" class="flex-1 py-2 bg-slate-700 hover:bg-slate-600 text-slate-300 text-sm font-medium rounded-lg transition-colors">Cancel</button>
      </div>
      <p id="ap-error" class="hidden text-red-400 text-xs"></p>
    </form>
  </div>
</div>

<script>
const _liHeaders = () => ({
  'Content-Type': 'application/json',
  'Authorization': `Bearer ${localStorage.getItem('access_token') || ''}`,
});

const _STATUS_LABELS = {
  pending: { label: 'Pending', cls: 'bg-slate-700 text-slate-300' },
  connection_sent: { label: 'Connection sent', cls: 'bg-blue-900 text-blue-300' },
  connected: { label: 'Connected', cls: 'bg-cyan-900 text-cyan-300' },
  message_2_sent: { label: 'Msg 2 sent', cls: 'bg-yellow-900 text-yellow-300' },
  message_3_sent: { label: 'Msg 3 sent', cls: 'bg-orange-900 text-orange-300' },
  replied: { label: 'Replied', cls: 'bg-green-900 text-green-300' },
  qualified: { label: 'Qualified', cls: 'bg-indigo-900 text-indigo-300' },
  disqualified: { label: 'Disqualified', cls: 'bg-red-900 text-red-300' },
};

async function loadLinkedInQueue() {
  const status = document.getElementById('li-status-filter').value;
  const url = `/api/v1/linkedin/prospects${status ? '?status=' + status : ''}`;
  const resp = await fetch(url, { credentials: 'include', headers: _liHeaders() });
  if (!resp.ok) return;
  const prospects = await resp.json();
  const tbody = document.getElementById('li-queue-tbody');
  if (!prospects.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="px-4 py-6 text-center text-slate-500">No prospects in queue</td></tr>';
    return;
  }
  tbody.innerHTML = prospects.map(p => {
    const s = _STATUS_LABELS[p.status] || { label: p.status, cls: 'bg-slate-700 text-slate-300' };
    return `<tr class="border-t border-slate-800 hover:bg-slate-800/40">
      <td class="px-4 py-3"><a href="${p.linkedin_url}" target="_blank" class="text-indigo-400 hover:underline">${p.name}</a></td>
      <td class="px-4 py-3 text-slate-400">${p.company_name || '—'}</td>
      <td class="px-4 py-3 text-slate-400">${p.job_title || '—'}</td>
      <td class="px-4 py-3"><span class="px-2 py-0.5 rounded-full text-xs font-medium ${s.cls}">${s.label}</span></td>
      <td class="px-4 py-3 text-slate-400">${p.fit_score ?? '—'}</td>
      <td class="px-4 py-3 text-slate-500 text-xs">${p.source}</td>
      <td class="px-4 py-3 flex gap-2 text-xs">
        <button onclick="advanceProspect('${p.id}')" class="px-2 py-1 bg-indigo-800 hover:bg-indigo-700 text-indigo-200 rounded">Advance</button>
        <button onclick="disqualifyProspect('${p.id}')" class="px-2 py-1 bg-red-900 hover:bg-red-800 text-red-300 rounded">Disqualify</button>
      </td>
    </tr>`;
  }).join('');
}

async function advanceProspect(id) {
  await fetch(`/api/v1/linkedin/prospects/${id}/advance`, { method: 'POST', headers: _liHeaders(), credentials: 'include' });
  loadLinkedInQueue();
}

async function disqualifyProspect(id) {
  if (!confirm('Disqualify this prospect?')) return;
  await fetch(`/api/v1/linkedin/prospects/${id}/disqualify`, { method: 'POST', headers: _liHeaders(), credentials: 'include' });
  loadLinkedInQueue();
}

async function loadICP() {
  const resp = await fetch('/api/v1/linkedin/icp', { credentials: 'include', headers: _liHeaders() });
  if (!resp.ok) return;
  const d = await resp.json();
  document.getElementById('icp-titles').value = (d.titles || []).join(', ');
  document.getElementById('icp-industries').value = (d.industries || []).join(', ');
  document.getElementById('icp-size-min').value = d.company_size_min ?? 10;
  document.getElementById('icp-size-max').value = d.company_size_max ?? 50;
  document.getElementById('icp-geos').value = (d.geographies || []).join(', ');
}

async function saveICP(e) {
  e.preventDefault();
  const split = v => v.split(',').map(s => s.trim()).filter(Boolean);
  const payload = {
    titles: split(document.getElementById('icp-titles').value),
    industries: split(document.getElementById('icp-industries').value),
    company_size_min: parseInt(document.getElementById('icp-size-min').value),
    company_size_max: parseInt(document.getElementById('icp-size-max').value),
    geographies: split(document.getElementById('icp-geos').value),
  };
  await fetch('/api/v1/linkedin/icp', { method: 'POST', headers: _liHeaders(), credentials: 'include', body: JSON.stringify(payload) });
  const msg = document.getElementById('icp-saved-msg');
  msg.classList.remove('hidden');
  setTimeout(() => msg.classList.add('hidden'), 2000);
}

function showAddProspectModal() { document.getElementById('add-prospect-modal').classList.remove('hidden'); }
function hideAddProspectModal() { document.getElementById('add-prospect-modal').classList.add('hidden'); }

async function submitAddProspect(e) {
  e.preventDefault();
  const errEl = document.getElementById('ap-error');
  errEl.classList.add('hidden');
  const payload = {
    linkedin_url: document.getElementById('ap-url').value.trim(),
    name: document.getElementById('ap-name').value.trim(),
    company_name: document.getElementById('ap-company').value.trim(),
    job_title: document.getElementById('ap-title').value.trim(),
    industry: document.getElementById('ap-industry').value.trim(),
  };
  const resp = await fetch('/api/v1/linkedin/prospects', { method: 'POST', headers: _liHeaders(), credentials: 'include', body: JSON.stringify(payload) });
  if (resp.ok) {
    hideAddProspectModal();
    document.getElementById('add-prospect-form').reset();
    loadLinkedInQueue();
  } else {
    const d = await resp.json();
    errEl.textContent = d.error || 'Failed to add prospect';
    errEl.classList.remove('hidden');
  }
}

// Load on section activation
document.addEventListener('DOMContentLoaded', () => {
  const section = document.body.getAttribute('data-section');
  if (section === 'linkedin') { loadLinkedInQueue(); loadICP(); }
});
document.addEventListener('sectionChange', (e) => {
  if (e.detail === 'linkedin') { loadLinkedInQueue(); loadICP(); }
});
</script>
```

- [ ] **Step 4: Commit**

```bash
git add src/marketing_ops/routes.py src/templates/admin/section_linkedin.html src/templates/marketing_ops.html
git commit -m "feat(linkedin): add LinkedIn queue UI and ICP settings panel"
```

---

## Task 11: Flesh Out `skills/linkedin_cadence/skill.md`

**Files:**
- Modify: `skills/linkedin_cadence/skill.md`

- [ ] **Step 1: Write the skill**

```markdown
---
name: linkedin-cadence
description: Standards and workflow for InboxIQ's LinkedIn outreach cadence — agent-driven prospect discovery, message drafting, and daily digest
type: process
---

# LinkedIn Cadence

Use this skill when modifying the LinkedIn outreach pipeline:
`src/tasks/linkedin.py`, `src/api/v1/linkedin.py`, `src/models/campaigns.py` (LinkedInProspect),
`src/models/marketing.py` (ICPConfig), or either DSPy script below.

## Scripts

| Script | Purpose |
| --- | --- |
| [scripts/draft_messages.py](scripts/draft_messages.py) | Drafts all 3 LinkedIn messages in one DSPy call |
| [scripts/match_post.py](scripts/match_post.py) | Selects the best blog post for message 2 |

Run standalone: `python -m skills.linkedin_cadence.scripts.draft_messages`

## Daily Pipeline (Celery beat)

| Time | Task | What it does |
| --- | --- | --- |
| 7:00am | `linkedin.discover_prospects` | Promotes qualifying Leads into LinkedInProspect queue |
| 7:30am | `linkedin.draft_messages` | Drafts 3 messages + selects blog post for each pending prospect |
| 8:00am | `linkedin.send_digest` | Emails the day's due actions to ADMIN_EMAILS |

## Cadence Rules

- **Message 1:** Connection request only. No pitch, no product mention. ≤300 chars.
- **Message 2:** Value only. Share matched blog post. No ask. ≤500 chars. Never send before `connected_at` is set.
- **Message 3:** One soft ask — "would a 15-min call make sense?" ≤400 chars. Never before message 2 is marked sent.
- **Disqualify** after 14 days with no response to message 3.

## Status Flow

```
pending → connection_sent → connected → message_2_sent → message_3_sent → replied → qualified → disqualified
```

`_advance_prospect()` in `src/api/v1/linkedin.py` handles all transitions and computes due dates:
- `connected_at` set → `message_2_due_at = connected_at + 3 days`
- `message_2_sent_at` set → `message_3_due_at = message_2_sent_at + 5 days`

## ICP

Stored in `ICPConfig` (`src/models/marketing.py`). **Never hardcoded in task code.**
Edit via Marketing Ops → LinkedIn → ICP Settings, or `POST /api/v1/linkedin/icp`.

Defaults: Founder / Head of Support / Operations Lead / Customer Success Lead · B2B SaaS, Software · 10–50 employees · UK, US, Nigeria.

## Funnel Integration

| Status reached | Lead action |
| --- | --- |
| `replied` | `lead.current_funnel_stage = "consideration"` |
| `qualified` | `lead.current_funnel_stage = "conversion"` |

Handled inside `_advance_lead_stage()` in `src/api/v1/linkedin.py`.

## Checklist Before Changing the Pipeline

- [ ] All DB writes wrapped in try/except with `db.session.rollback()` on failure
- [ ] `discover_prospects` queries scoped by `account_id`
- [ ] `_advance_prospect` handles all 7 status transitions without skipping
- [ ] DSPy scripts import `_configure_dspy()` before instantiating modules
- [ ] New Celery tasks registered in `src/celery_inboxiq.py` beat_schedule AND the `include` list
```

- [ ] **Step 2: Commit**

```bash
git add skills/linkedin_cadence/skill.md
git commit -m "feat(linkedin): flesh out linkedin_cadence skill document"
```

---

## Task 12: Final Verification

- [ ] **Step 1: Run the full test suite**

```bash
pytest tests/linkedin/ -v
```

Expected: All tests PASS.

- [ ] **Step 2: Start the dev server and verify the LinkedIn tab appears**

```bash
flask run
```

Navigate to `/marketing/linkedin` — confirm the queue table loads, the "Add Prospect" button opens the modal, and the ICP Settings form populates.

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "feat(linkedin): complete LinkedIn outreach cadence — Phase 2"
```
