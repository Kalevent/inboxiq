# LinkedIn Cadence Data Quality + Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the LinkedIn cadence acceptance-rate collapse (8.3% → 0% over 5 days) by repairing data quality, hardening the DSPy agent, adding domain observability, and cleaning the polluted prospect queue — so future outreach goes only to verified ICP matches with real titles and companies.

**Architecture:** Three layers fail today: (1) the upstream MCP `extract_company_name` produces junk strings from search-result titles; (2) the `Lead`/`LinkedInProspect` schema and copy logic drop `job_title` even when MCPs return it; (3) the agent wrapper marks LLM give-ups as `success` and exposes no domain metrics, so the failure was invisible in Prometheus/Grafana. Fixes follow the data flow: validate at MCP boundary → validate at save_lead → fix schema → propagate fields → tighten DSPy signature/goal → fix telemetry → expose metrics → alert. Each fix is independently testable.

**Tech Stack:** Python 3.11 / Flask / SQLAlchemy / Celery / DSPy ReAct / Phoenix (Arize) / Prometheus + Grafana / pytest

---

## Pre-flight: stop the bleeding (no code; one-shot ops)

### Task 0: Pause cadence + audit polluted queue

**Files:** none (kubectl ops + DB updates)

- [ ] **Step 0.1: Disable LinkedIn beat schedule entries**

Run from project root:
```bash
kubectl exec -n kaley deploy/inboxiq-beat -- printenv | grep -i linkedin
# Confirm beat is the place that schedules linkedin.* tasks
```

Then patch the beat ConfigMap to disable `linkedin.discover_prospects`, `linkedin.draft_messages`, `linkedin.enrich_linkedin_urls`, `linkedin.send_digest` for 72h:
```bash
kubectl edit configmap inboxiq-beat-config -n kaley
# Comment out the four linkedin.* entries; save
kubectl rollout restart deployment/inboxiq-beat -n kaley
```

- [ ] **Step 0.2: Bulk-flag polluted prospects to `needs_review`**

Run via `kubectl exec -n kaley deploy/inboxiq -- python -c "..."`:
```python
from src.app import create_app
from src.extensions import db
from src.models.campaigns import LinkedInProspect
import re

GARBAGE_PATTERNS = [
    r"^\$",                          # "$12"
    r"^\d",                          # "30 Top..." / "10 Fastest"
    r"^Series\s+[A-E]",              # "Series B"
    r"^Top\s+\d",                    # "Top 5..."
    r"^Best\s+\d",                   # "Best 8..."
    r"^List of",                     # "List of Funded SaaS..."
    r"^Understanding",               # "Understanding Seed Rounds..."
    r"^Apply With",                  # "Apply With MISD"
    r"^How (To|to|do)",
    r"^Exclusive$",
    r"^Fundraising$",
    r"raises\s+\$",                  # "Yuma AI Raises $5 Million..."
    r"\d+(\.\d+)?\s*[Mm]illion",
    r"Pre-?seed|Pre-?Series",
]
GARBAGE_RE = re.compile("|".join(GARBAGE_PATTERNS))

app = create_app()
with app.app_context():
    rows = db.session.query(LinkedInProspect).filter(
        LinkedInProspect.status.in_(["pending", "connection_sent"]),
    ).all()
    flagged = 0
    for p in rows:
        co = (p.company_name or "").strip()
        if not co or len(co) < 4 or GARBAGE_RE.search(co):
            p.status = "needs_review"
            p.notes = (p.notes or "") + f"\n[2026-05-10 audit] flagged garbage company_name={co!r}"
            flagged += 1
    if flagged:
        try:
            db.session.commit()
            print(f"flagged {flagged}")
        except Exception:
            db.session.rollback()
            raise
```

- [ ] **Step 0.3: Snapshot baseline metrics for later comparison**

```bash
kubectl exec -n kaley deploy/inboxiq -- python -c "
from src.app import create_app
from src.extensions import db
from src.models.campaigns import LinkedInProspect
from sqlalchemy import func
app = create_app()
with app.app_context():
    rows = db.session.query(LinkedInProspect.status, func.count()).group_by(LinkedInProspect.status).all()
    for r in rows: print(r)
" > /tmp/inboxiq-cadence-baseline-2026-05-10.txt
cat /tmp/inboxiq-cadence-baseline-2026-05-10.txt
```

- [ ] **Step 0.4: Commit nothing yet — pre-flight only.** Proceed to Task 1.

---

## File Structure (locked decisions)

**Modify:**
- `src/mcp/lead_discovery_mcp.py` — strengthen `extract_company_name` + add validators
- `src/agents/funnel_discovery.py` — broaden `_tool_save_lead` validation
- `src/models/leads.py` — add `job_title` column
- `src/models/campaigns.py` — confirm `LinkedInProspect.job_title` column exists; add if missing
- `src/agents/linkedin_cadence.py` — propagate `job_title` through enrich + promote
- `src/agents/base.py` — strict `success` evaluation, max_iters telemetry
- `src/dspy/signatures.py` — add structured `LinkedInUrlSelection` signature
- `src/tasks/linkedin.py` — tighten enrichment goal prompt
- `src/monitoring/observability.py` — register Prometheus counters/gauges/histograms
- `src/funnel/lead_qualifier.py` (or wherever `fit_score` is set) — replace binary 7 with graded 4-10

**Create:**
- `tests/mcp/test_extract_company_name.py`
- `tests/agents/test_funnel_discovery_save_lead.py`
- `tests/agents/test_linkedin_cadence_propagation.py`
- `tests/agents/test_base_agent_success_eval.py`
- `tests/dspy/test_linkedin_url_selection_signature.py`
- `tests/monitoring/test_linkedin_metrics.py`
- `src/k8s/grafana-dashboards/linkedin-cadence.json` — Grafana dashboard JSON
- `src/k8s/prometheus-rules/linkedin-cadence-alerts.yaml` — PrometheusRule CR

---

## Phase 1: Data validation hardening (Tasks 1–3)

### Task 1: Tighten `extract_company_name` + add validator

**Files:**
- Modify: `src/mcp/lead_discovery_mcp.py:56-62`
- Test: `tests/mcp/test_extract_company_name.py` (create)

- [ ] **Step 1.1: Write the failing test**

```python
# tests/mcp/test_extract_company_name.py
import pytest
from src.mcp.lead_discovery_mcp import extract_company_name, looks_like_real_company

@pytest.mark.parametrize("title,expected", [
    ("Sprinto - About Us", "Sprinto"),
    ("Acme Inc. | Customer Stories", "Acme"),
    ("Harver Series B Funding", "Harver Series B Funding"),
])
def test_extract_company_name_valid(title, expected):
    assert extract_company_name(title) == expected

@pytest.mark.parametrize("candidate", [
    "$12",
    "Series B",
    "30 Top B2B SaaS Companies & Startups [2026]",
    "Apply With MISD",
    "10 Fastest",
    "Exclusive",
    "Fundraising",
    "Understanding Seed Rounds, Series A, B, and C",
    "Yuma AI Raises $5 Million to Transform E",
    "List of SaaS Investors & VC Firms",
    "How to Outsource Customer Support",
    "abc",  # too short
    "",
    "   ",
])
def test_looks_like_real_company_rejects_junk(candidate):
    assert looks_like_real_company(candidate) is False

@pytest.mark.parametrize("candidate", [
    "Sprinto",
    "Harver",
    "Acme Corporation",
    "Stripe",
    "Notion Labs",
])
def test_looks_like_real_company_accepts_real(candidate):
    assert looks_like_real_company(candidate) is True
```

- [ ] **Step 1.2: Run test to verify it fails**

```bash
cd /Users/kofi/inboxiq && pytest tests/mcp/test_extract_company_name.py -v
```
Expected: FAIL with `ImportError: cannot import name 'looks_like_real_company'`

- [ ] **Step 1.3: Implement `looks_like_real_company` and tighten extract**

Replace `src/mcp/lead_discovery_mcp.py:56-62` with:
```python
import re

_GARBAGE_PATTERNS = re.compile(
    r"^(\$|\d|Series\s+[A-E]\b|Top\s+\d|Best\s+\d|List\s+of|"
    r"Understanding|Apply\s+With|How\s+[Tt]o|How\s+do|Why\s|What\s+is|"
    r"Exclusive$|Fundraising$|The\s+\d+|Guide\s+to)",
    re.IGNORECASE,
)
_FUNDING_KEYWORDS = re.compile(
    r"(raises\s+\$|\d+(\.\d+)?\s*[Mm]illion|pre-?seed|pre-?series|"
    r"Series\s+[A-E]\s+(Funding|Round)|valuation)",
    re.IGNORECASE,
)
_MIN_COMPANY_LEN = 4
_MAX_COMPANY_LEN = 70


def looks_like_real_company(candidate: str) -> bool:
    """Reject junk strings that aren't actually company names."""
    if not candidate:
        return False
    s = candidate.strip()
    if len(s) < _MIN_COMPANY_LEN or len(s) > _MAX_COMPANY_LEN:
        return False
    if _GARBAGE_PATTERNS.search(s):
        return False
    if _FUNDING_KEYWORDS.search(s):
        return False
    if not re.search(r"[A-Za-z]{3,}", s):
        return False
    return True


def extract_company_name(title: str) -> str:
    """Extract company name from search result title. Returns "" if not parseable."""
    if not title:
        return ""
    name = re.split(r"[\-\|–:]", title)[0].strip()
    name = re.sub(
        r"\s+(Inc|LLC|Ltd|Corporation|Corp|Company|Co)\.?$",
        "",
        name,
        flags=re.IGNORECASE,
    ).strip()
    return name
```

- [ ] **Step 1.4: Run tests, verify pass**

```bash
cd /Users/kofi/inboxiq && pytest tests/mcp/test_extract_company_name.py -v
```
Expected: 13 PASS

- [ ] **Step 1.5: Wire validator into MCP search results**

Find the call sites in `src/mcp/lead_discovery_mcp.py` (lines 139, 340) where `extract_company_name(...)` is appended to the candidate list. Change to:
```python
company_name = extract_company_name(result.get("title", ""))
if not looks_like_real_company(company_name):
    continue
# ... existing append logic
```

- [ ] **Step 1.6: Commit**

```bash
git add src/mcp/lead_discovery_mcp.py tests/mcp/test_extract_company_name.py
git commit -m "fix(lead_discovery): reject junk company_name candidates from search titles"
```

---

### Task 2: Strengthen `funnel_discovery._tool_save_lead` validation

**Files:**
- Modify: `src/agents/funnel_discovery.py:142-152`
- Test: `tests/agents/test_funnel_discovery_save_lead.py` (create)

- [ ] **Step 2.1: Write the failing test**

```python
# tests/agents/test_funnel_discovery_save_lead.py
import pytest
from unittest.mock import patch
from src.agents.funnel_discovery import FunnelDiscoveryAgent


@pytest.fixture
def agent():
    return FunnelDiscoveryAgent(account_id=1)


@pytest.mark.parametrize("company_name", [
    "$12", "Series B", "Exclusive", "Apply With MISD",
    "10 Fastest", "30 Top B2B SaaS Companies & Startups [2026]",
    "Understanding Seed Rounds, Series A, B, and C",
    "abc",  # too short
])
def test_save_lead_rejects_garbage(agent, company_name):
    result = agent._tool_save_lead(
        company_name=company_name, email="x@example.com",
        industry="SaaS", fit_score=7, source="searxng_discovery",
    )
    assert result["created"] is False
    assert result["reason"] == "not_a_company"


def test_save_lead_accepts_real_company(agent, app_context):
    with patch("src.agents.funnel_discovery.qualify_visitor") as q:
        result = agent._tool_save_lead(
            company_name="Sprinto", email="x@sprinto.com",
            industry="SaaS", fit_score=7, source="searxng_discovery",
        )
    assert result["created"] is True
```

- [ ] **Step 2.2: Run test, verify failure**

```bash
cd /Users/kofi/inboxiq && pytest tests/agents/test_funnel_discovery_save_lead.py -v
```
Expected: tests for `$12`, `Series B`, `Exclusive`, etc. FAIL (currently slip through validation)

- [ ] **Step 2.3: Replace validation block**

Replace lines 142-152 of `src/agents/funnel_discovery.py` with:
```python
from src.mcp.lead_discovery_mcp import looks_like_real_company

if not looks_like_real_company(company_name):
    return {"created": False, "reason": "not_a_company"}
```

- [ ] **Step 2.4: Run tests, verify pass**

```bash
cd /Users/kofi/inboxiq && pytest tests/agents/test_funnel_discovery_save_lead.py -v
```
Expected: all PASS

- [ ] **Step 2.5: Commit**

```bash
git add src/agents/funnel_discovery.py tests/agents/test_funnel_discovery_save_lead.py
git commit -m "fix(funnel_discovery): use shared looks_like_real_company validator"
```

---

### Task 3: Add `job_title` column to `Lead` and `LinkedInProspect`

**Files:**
- Modify: `src/models/leads.py:30-32` (insert `job_title`)
- Verify: `src/models/campaigns.py` (LinkedInProspect already has `job_title` per cadence agent code that references `prospect.job_title` — but worth verifying)
- Test: `tests/models/test_lead_job_title.py` (create)

- [ ] **Step 3.1: Write failing test**

```python
# tests/models/test_lead_job_title.py
from src.models.leads import Lead

def test_lead_has_job_title_column():
    assert "job_title" in Lead.__table__.columns
    col = Lead.__table__.columns["job_title"]
    assert col.nullable is True
    assert str(col.type).startswith("VARCHAR")
```

- [ ] **Step 3.2: Run test, verify failure**

```bash
cd /Users/kofi/inboxiq && pytest tests/models/test_lead_job_title.py -v
```
Expected: FAIL — column missing

- [ ] **Step 3.3: Add column to `Lead` model**

In `src/models/leads.py`, after line 31 (`industry = ...`), add:
```python
    job_title = db.Column(db.String(255), nullable=True, comment="Decision maker role e.g. 'Director of Customer Support'")
```

Also add to the `to_dict()` method around line 89:
```python
            "job_title": self.job_title,
```

- [ ] **Step 3.4: Verify `LinkedInProspect.job_title` exists**

```bash
grep -n "job_title" /Users/kofi/inboxiq/src/models/campaigns.py
```
Expected: at least one `job_title = db.Column(...)` line. If missing, add the same column to `LinkedInProspect`.

- [ ] **Step 3.5: Run test, verify pass**

```bash
cd /Users/kofi/inboxiq && pytest tests/models/test_lead_job_title.py -v
```

- [ ] **Step 3.6: Tell user to generate + run migration**

Per `CLAUDE.md`: do NOT create migration files directly. Output:
```
Run: flask db migrate -m "add job_title to leads (and linkedin_prospects if missing)"
Review the generated migration in src/migrations/versions/, then: flask db upgrade
DO NOT run this in a worktree — only on main after PR merge.
```

- [ ] **Step 3.7: Commit (model only — migration applied separately)**

```bash
git add src/models/leads.py src/models/campaigns.py tests/models/test_lead_job_title.py
git commit -m "feat(leads): add job_title column to Lead (and LinkedInProspect if missing)"
```

---

## Phase 2: Field propagation (Tasks 4–5)

### Task 4: Propagate `job_title` through `_tool_enrich_lead_linkedin_url`

**Files:**
- Modify: `src/agents/linkedin_cadence.py:128-158`
- Test: `tests/agents/test_linkedin_cadence_propagation.py` (create)

- [ ] **Step 4.1: Write failing test**

```python
# tests/agents/test_linkedin_cadence_propagation.py
import pytest
from unittest.mock import MagicMock
from src.agents.linkedin_cadence import LinkedInCadenceAgent
from src.models.leads import Lead
from src.extensions import db

def test_enrich_persists_job_title(app_context, account):
    lead = Lead(
        account_id=account.id, name="Jazmyne Cavitt",
        email="j@sprinto.com", company_name="Sprinto",
        source="searxng_discovery", fit_score=7,
    )
    db.session.add(lead); db.session.commit()
    agent = LinkedInCadenceAgent(account_id=account.id)
    result = agent._tool_enrich_lead_linkedin_url(
        lead_id=str(lead.id),
        linkedin_url="https://www.linkedin.com/in/jazmyne-cavitt",
        name="Jazmyne Cavitt",
        job_title="Director, Customer Support",
    )
    assert result["saved"] is True
    db.session.refresh(lead)
    assert lead.job_title == "Director, Customer Support"
    assert lead.linkedin_url == "https://www.linkedin.com/in/jazmyne-cavitt"
```

- [ ] **Step 4.2: Run test, verify failure**

```bash
cd /Users/kofi/inboxiq && pytest tests/agents/test_linkedin_cadence_propagation.py::test_enrich_persists_job_title -v
```
Expected: FAIL — `job_title` parameter not accepted

- [ ] **Step 4.3: Update tool signature + persistence**

In `src/agents/linkedin_cadence.py`, change `_tool_enrich_lead_linkedin_url` (line 128) signature and body:

```python
def _tool_enrich_lead_linkedin_url(
    self,
    lead_id: str,
    linkedin_url: str,
    name: str = "",
    job_title: str = "",
) -> Dict[str, Any]:
    """
    Save a verified LinkedIn URL, name, and job_title to a Lead.
    Call after find_decision_makers + browser_snapshot confirm the URL.
    """
    from src.models.leads import Lead
    clean_url = linkedin_url.split("?")[0]
    self.tool_calls.append({
        "tool": "enrich_lead_linkedin_url",
        "input": {"lead_id": lead_id, "linkedin_url": clean_url, "job_title": job_title},
    })
    lead = db.session.query(Lead).filter_by(id=lead_id, account_id=self.account_id).first()
    if not lead:
        return {"saved": False, "error": "lead not found"}
    if not (clean_url.startswith("https://www.linkedin.com/") or clean_url.startswith("https://linkedin.com/")):
        return {"saved": False, "error": "invalid linkedin_url"}

    effective_name = name if (name and (not lead.name or lead.name == lead.company_name)) else lead.name
    if effective_name and not name_url_tokens_match(effective_name, clean_url):
        log.warning(
            "linkedin enrichment refused: name/url mismatch lead=%s name=%r url=%s",
            lead_id, effective_name, clean_url,
        )
        return {"saved": False, "error": "name/url mismatch"}

    lead.linkedin_url = clean_url
    if name and (not lead.name or lead.name == lead.company_name):
        lead.name = name
    if job_title:
        lead.job_title = job_title.strip()[:255]
    try:
        db.session.commit()
        return {"saved": True}
    except Exception as exc:
        db.session.rollback()
        return {"saved": False, "error": str(exc)}
```

- [ ] **Step 4.4: Run test, verify pass**

```bash
cd /Users/kofi/inboxiq && pytest tests/agents/test_linkedin_cadence_propagation.py::test_enrich_persists_job_title -v
```

- [ ] **Step 4.5: Commit**

```bash
git add src/agents/linkedin_cadence.py tests/agents/test_linkedin_cadence_propagation.py
git commit -m "feat(linkedin_cadence): persist job_title in enrich_lead_linkedin_url"
```

---

### Task 5: Copy `job_title` in `_tool_add_to_prospect_queue`

**Files:**
- Modify: `src/agents/linkedin_cadence.py:178-188`
- Test: `tests/agents/test_linkedin_cadence_propagation.py` (extend)

- [ ] **Step 5.1: Add failing test**

Append to `tests/agents/test_linkedin_cadence_propagation.py`:
```python
def test_promote_copies_job_title(app_context, account):
    from src.models.campaigns import LinkedInProspect
    lead = Lead(
        account_id=account.id, name="Jazmyne Cavitt",
        email="j@sprinto.com", company_name="Sprinto",
        source="searxng_discovery", fit_score=7,
        job_title="Director, Customer Support",
        linkedin_url="https://www.linkedin.com/in/jazmyne-cavitt",
    )
    db.session.add(lead); db.session.commit()
    agent = LinkedInCadenceAgent(account_id=account.id)
    res = agent._tool_add_to_prospect_queue(str(lead.id))
    assert res["created"] is True
    p = db.session.query(LinkedInProspect).filter_by(lead_id=lead.id).one()
    assert p.job_title == "Director, Customer Support"
```

- [ ] **Step 5.2: Run, verify fail**

```bash
cd /Users/kofi/inboxiq && pytest tests/agents/test_linkedin_cadence_propagation.py::test_promote_copies_job_title -v
```

- [ ] **Step 5.3: Add `job_title=lead.job_title` to LinkedInProspect kwargs**

In `src/agents/linkedin_cadence.py`, modify the `LinkedInProspect(...)` constructor (around line 178) to include:
```python
        prospect = LinkedInProspect(
            account_id=self.account_id,
            lead_id=lead.id,
            name=lead.name,
            company_name=lead.company_name,
            industry=lead.industry,
            job_title=lead.job_title,  # NEW
            linkedin_url=lead.linkedin_url,
            source="auto",
            status="pending",
            fit_score=lead.fit_score,
        )
```

- [ ] **Step 5.4: Run, verify pass**

- [ ] **Step 5.5: Commit**

```bash
git add src/agents/linkedin_cadence.py tests/agents/test_linkedin_cadence_propagation.py
git commit -m "feat(linkedin_cadence): copy job_title from Lead to LinkedInProspect"
```

---

## Phase 3: DSPy / agent hardening (Tasks 6–8)

### Task 6: Structured `LinkedInUrlSelection` DSPy signature

**Files:**
- Modify: `src/dspy/signatures.py`
- Test: `tests/dspy/test_linkedin_url_selection_signature.py` (create)

- [ ] **Step 6.1: Write failing test**

```python
# tests/dspy/test_linkedin_url_selection_signature.py
import dspy
from src.dspy.signatures import LinkedInUrlSelection

def test_signature_has_structured_fields():
    sig = LinkedInUrlSelection
    assert "lead_name" in sig.input_fields
    assert "lead_company" in sig.input_fields
    assert "candidate_profiles" in sig.input_fields
    assert "selected_url" in sig.output_fields
    assert "selected_name" in sig.output_fields
    assert "selected_job_title" in sig.output_fields
    assert "skip_reason" in sig.output_fields

def test_signature_docstring_constrains_skip():
    assert "skip" in LinkedInUrlSelection.__doc__.lower()
    assert "no clear match" in LinkedInUrlSelection.__doc__.lower()
```

- [ ] **Step 6.2: Run, verify fail**

- [ ] **Step 6.3: Add the signature**

Append to `src/dspy/signatures.py`:
```python
class LinkedInUrlSelection(dspy.Signature):
    """
    Pick the LinkedIn profile URL that belongs to the named lead at the named company.

    Strict rules:
      - Return skip_reason and empty selected_url if there is NO clear match.
      - "Clear match" = the candidate name matches lead_name AND the candidate's
        current employer matches lead_company.
      - NEVER pick a profile just because the person was mentioned in an article
        or news headline. Funding announcements, listicles, and blog posts are
        never valid sources for company affiliation.
      - The selected_job_title must come from the candidate's LinkedIn profile,
        not from a search result snippet.
    """
    lead_name = dspy.InputField(desc="The lead's full name")
    lead_company = dspy.InputField(desc="The lead's company")
    lead_industry = dspy.InputField(desc="Expected industry for ICP fit")
    candidate_profiles = dspy.InputField(
        desc="JSON list of {name, job_title, company, linkedin_url, snippet} from MCP search"
    )
    selected_url = dspy.OutputField(desc="The chosen linkedin.com/in/... URL, or empty if no match")
    selected_name = dspy.OutputField(desc="The name on the selected profile")
    selected_job_title = dspy.OutputField(desc="The role from the selected profile")
    skip_reason = dspy.OutputField(
        desc="If no clear match, explain why in one short phrase. Empty if a URL was selected."
    )
```

- [ ] **Step 6.4: Run, verify pass**

- [ ] **Step 6.5: Commit**

```bash
git add src/dspy/signatures.py tests/dspy/test_linkedin_url_selection_signature.py
git commit -m "feat(dspy): add structured LinkedInUrlSelection signature with skip path"
```

---

### Task 7: Tighten enrichment goal prompt + use new signature

**Files:**
- Modify: `src/tasks/linkedin.py:130-132`
- Modify: `src/agents/linkedin_cadence.py` — override `_get_signature` to return `LinkedInUrlSelection` for the enrich path (or accept the new signature via constructor)

- [ ] **Step 7.1: Replace goal text**

In `src/tasks/linkedin.py` line 130-132:
```python
        LinkedInCadenceAgent(account_id=account_id).execute(
            "Enrich qualifying leads with LinkedIn URLs. "
            "For EACH lead from get_qualifying_leads:\n"
            "  1. Call find_decision_makers with the lead's company domain.\n"
            "  2. From the candidates, pick at most ONE profile where BOTH the name "
            "matches the lead AND the current employer matches the lead's company. "
            "If no candidate satisfies both, SKIP this lead — do not call enrich_lead_linkedin_url.\n"
            "  3. Verify the chosen profile by browser_navigate + browser_snapshot. "
            "If the snapshot shows a different person or different employer, SKIP.\n"
            "  4. Call enrich_lead_linkedin_url with the verified URL, name, and job_title from the profile.\n"
            "Stop after processing 10 leads or when no qualifying leads remain. "
            "It is BETTER to skip a lead than to attach a wrong URL."
        )
```

- [ ] **Step 7.2: Add a no-write smoke test**

```python
# tests/tasks/test_enrich_goal_prompt.py
def test_enrich_goal_includes_skip_directive():
    from src.tasks.linkedin import enrich_linkedin_urls
    import inspect
    src_text = inspect.getsource(enrich_linkedin_urls)
    assert "SKIP" in src_text
    assert "do not call enrich_lead_linkedin_url" in src_text
```

- [ ] **Step 7.3: Commit**

```bash
git add src/tasks/linkedin.py tests/tasks/test_enrich_goal_prompt.py
git commit -m "fix(linkedin): tighten enrich goal — skip on weak match, cap at 10 leads/run"
```

---

### Task 8: Strict `success` evaluation in `BaseAgent`

**Files:**
- Modify: `src/agents/base.py:65-91`
- Test: `tests/agents/test_base_agent_success_eval.py` (create)

- [ ] **Step 8.1: Write failing test**

```python
# tests/agents/test_base_agent_success_eval.py
from unittest.mock import patch, MagicMock
from src.agents.base import BaseAgent

class _Dummy(BaseAgent):
    agent_name = "dummy"
    mcp_server_labels = []
    def _get_tools(self): return []

@patch("src.agents.base.dspy")
def test_status_error_when_llm_admits_failure(mock_dspy, app_context):
    mock_dspy.ReAct.return_value = MagicMock(return_value=MagicMock(
        result="Despite persistent efforts, I was unable to retrieve the qualifying leads."
    ))
    res = _Dummy(account_id=1).execute("test goal")
    assert res["success"] is False

@patch("src.agents.base.dspy")
def test_status_error_when_max_iters_hit(mock_dspy, app_context):
    # ReAct exhausts max_iters silently — pretend tool_calls hit ceiling
    agent = _Dummy(account_id=1)
    agent.max_iters = 5
    mock_dspy.ReAct.return_value = MagicMock(return_value=MagicMock(
        result="OK done"
    ))
    # Append max_iters tool calls during 'execution'
    def _fake_react(goal):
        for _ in range(agent.max_iters):
            agent.tool_calls.append({"tool": "x"})
        return MagicMock(result="OK done")
    mock_dspy.ReAct.return_value = _fake_react
    res = agent.execute("test goal")
    assert res["success"] is False
    assert "max_iters" in (res.get("error") or "")
```

- [ ] **Step 8.2: Run, verify fail**

- [ ] **Step 8.3: Add `_evaluate_success` and apply**

In `src/agents/base.py`, between line 76 and 78, replace:
```python
            result_text = prediction.result or ""
            success = True
            self.log(f"Completed: {result_text[:200]}")
```
with:
```python
            result_text = prediction.result or ""
            success, failure_reason = self._evaluate_success(result_text)
            if not success:
                error_msg = failure_reason
            self.log(f"Completed (success={success}): {result_text[:200]}")
```

Add method to the class:
```python
    _FAILURE_PHRASES = (
        "unable to retrieve",
        "could not retrieve",
        "despite persistent efforts",
        "i was unable",
        "no qualifying leads found",
    )

    def _evaluate_success(self, result_text: str) -> tuple[bool, str | None]:
        """Return (success, failure_reason). Conservative: any failure phrase => False."""
        lowered = (result_text or "").lower()
        for phrase in self._FAILURE_PHRASES:
            if phrase in lowered:
                return False, f"llm_admitted_failure: {phrase}"
        if len(self.tool_calls) >= self.max_iters:
            return False, f"max_iters_hit ({self.max_iters})"
        return True, None
```

- [ ] **Step 8.4: Run tests, verify pass**

- [ ] **Step 8.5: Commit**

```bash
git add src/agents/base.py tests/agents/test_base_agent_success_eval.py
git commit -m "fix(agents): mark LLM give-ups and max_iters hits as status=error"
```

---

## Phase 4: Observability (Tasks 9–11)

### Task 9: Domain Prometheus metrics

**Files:**
- Modify: `src/monitoring/observability.py` (or create if absent)
- Modify: `src/agents/base.py` — emit metrics
- Modify: `src/api/v1/linkedin.py:_advance_prospect` — emit transition metric
- Test: `tests/monitoring/test_linkedin_metrics.py`

- [ ] **Step 9.1: Write failing test**

```python
# tests/monitoring/test_linkedin_metrics.py
from prometheus_client import REGISTRY

def test_metric_registry_has_linkedin_metrics():
    from src.monitoring import metrics  # new module
    names = {m.name for m in REGISTRY.collect()}
    assert "inboxiq_linkedin_prospect_status_transitions_total" in names
    assert "inboxiq_agent_react_max_iters_hit_total" in names
    assert "inboxiq_agent_status" in names
    assert "inboxiq_mcp_tool_call_duration_seconds" in names
```

- [ ] **Step 9.2: Run, verify fail**

- [ ] **Step 9.3: Create `src/monitoring/metrics.py`**

```python
"""Prometheus metrics for the InboxIQ outreach pipeline."""
from prometheus_client import Counter, Histogram, Gauge

linkedin_status_transitions = Counter(
    "inboxiq_linkedin_prospect_status_transitions_total",
    "LinkedInProspect status transitions",
    ["from_status", "to_status", "account_id"],
)

agent_react_max_iters_hit = Counter(
    "inboxiq_agent_react_max_iters_hit_total",
    "DSPy ReAct loops that hit max_iters without finishing",
    ["agent_name"],
)

agent_status = Counter(
    "inboxiq_agent_status",
    "Agent invocation outcome (success vs error vs llm_give_up)",
    ["agent_name", "status"],
)

mcp_tool_call_duration = Histogram(
    "inboxiq_mcp_tool_call_duration_seconds",
    "Duration of MCP tool calls from agents",
    ["server_label", "tool"],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60),
)

linkedin_acceptance_ratio = Gauge(
    "inboxiq_linkedin_acceptance_ratio",
    "Rolling 7d connection-accepted / connection-sent ratio",
    ["account_id"],
)
```

- [ ] **Step 9.4: Wire into `BaseAgent._store_event`**

In `src/agents/base.py:_store_event`, before the DB write, add:
```python
from src.monitoring.metrics import agent_status, agent_react_max_iters_hit
status_label = "success" if success else ("max_iters" if error_msg and "max_iters" in error_msg else "llm_give_up" if error_msg and "llm_admitted_failure" in error_msg else "error")
agent_status.labels(agent_name=self.agent_name, status=status_label).inc()
if status_label == "max_iters":
    agent_react_max_iters_hit.labels(agent_name=self.agent_name).inc()
```

- [ ] **Step 9.5: Wire into `_advance_prospect`**

In `src/api/v1/linkedin.py`, inside `_advance_prospect`, after `prospect.status = new_status`:
```python
from src.monitoring.metrics import linkedin_status_transitions
linkedin_status_transitions.labels(
    from_status=transition_from,  # capture before reassignment
    to_status=new_status,
    account_id=str(prospect.account_id),
).inc()
```
(Capture `transition_from = prospect.status` at the top of the function before mutating.)

- [ ] **Step 9.6: Add Celery task that updates `linkedin_acceptance_ratio` gauge daily**

```python
# in src/tasks/linkedin.py, add:
@shared_task(name="linkedin.update_acceptance_ratio_gauge")
def update_acceptance_ratio_gauge():
    from datetime import datetime, timezone, timedelta
    from src.models.campaigns import LinkedInProspect
    from src.monitoring.metrics import linkedin_acceptance_ratio
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    for account_id in _all_account_ids():
        sent = db.session.query(LinkedInProspect).filter(
            LinkedInProspect.account_id == account_id,
            LinkedInProspect.connection_sent_at >= cutoff,
        ).count()
        accepted = db.session.query(LinkedInProspect).filter(
            LinkedInProspect.account_id == account_id,
            LinkedInProspect.connected_at >= cutoff,
        ).count()
        ratio = (accepted / sent) if sent > 0 else 0.0
        linkedin_acceptance_ratio.labels(account_id=str(account_id)).set(ratio)
```
Register in `src/celery_inboxiq.py` beat_schedule (every 30 minutes).

- [ ] **Step 9.7: Run tests, verify pass**

- [ ] **Step 9.8: Commit**

```bash
git add src/monitoring/metrics.py src/agents/base.py src/api/v1/linkedin.py src/tasks/linkedin.py src/celery_inboxiq.py tests/monitoring/test_linkedin_metrics.py
git commit -m "feat(monitoring): expose linkedin/agent/mcp domain prometheus metrics"
```

---

### Task 10: Grafana dashboard JSON

**Files:**
- Create: `src/k8s/grafana-dashboards/linkedin-cadence.json`

- [ ] **Step 10.1: Write the dashboard JSON**

Panels:
1. Acceptance ratio over time — `inboxiq_linkedin_acceptance_ratio`
2. Status distribution (stacked bar) — sum by status from transitions counter
3. Agent outcome breakdown — `rate(inboxiq_agent_status[1h])` by status
4. ReAct max_iters rate — `rate(inboxiq_agent_react_max_iters_hit_total[6h])`
5. MCP tool latency p50/p95 — histogram quantile from `inboxiq_mcp_tool_call_duration_seconds`

Place full JSON in the file (do NOT truncate). Use existing dashboards under `src/k8s/` as reference for the JSON shape.

- [ ] **Step 10.2: Add to ConfigMap discovery**

If existing dashboards are loaded via a ConfigMap labeled `grafana_dashboard=1`, add the new file to that ConfigMap manifest.

- [ ] **Step 10.3: Commit**

```bash
git add src/k8s/grafana-dashboards/linkedin-cadence.json
git commit -m "feat(grafana): add LinkedIn cadence dashboard"
```

---

### Task 11: Prometheus alert rules

**Files:**
- Create: `src/k8s/prometheus-rules/linkedin-cadence-alerts.yaml`

- [ ] **Step 11.1: Write rule manifest**

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: linkedin-cadence-alerts
  namespace: kaley
  labels:
    release: kube-prometheus-stack
spec:
  groups:
  - name: linkedin-cadence
    interval: 60s
    rules:
    - alert: LinkedInAcceptanceRatioLow
      expr: inboxiq_linkedin_acceptance_ratio < 0.15
      for: 6h
      labels:
        severity: warning
      annotations:
        summary: "LinkedIn acceptance ratio below 15% for 6h on account {{ $labels.account_id }}"
        runbook: "Pause cadence, audit recent prospects for data quality."
    - alert: LinkedInAgentLLMGiveUp
      expr: increase(inboxiq_agent_status{agent_name="linkedin_cadence",status="llm_give_up"}[1h]) > 3
      for: 30m
      labels:
        severity: warning
      annotations:
        summary: "linkedin_cadence agent LLM giving up >3x/hr"
    - alert: LinkedInAgentMaxItersHit
      expr: increase(inboxiq_agent_react_max_iters_hit_total{agent_name="linkedin_cadence"}[1h]) > 5
      for: 30m
      labels:
        severity: warning
      annotations:
        summary: "linkedin_cadence agent hitting max_iters — tools or prompt broken"
```

- [ ] **Step 11.2: Apply manifest in CI/CD**

Confirm rule loads: `kubectl get prometheusrule -n kaley linkedin-cadence-alerts`

- [ ] **Step 11.3: Commit**

```bash
git add src/k8s/prometheus-rules/linkedin-cadence-alerts.yaml
git commit -m "feat(alerting): linkedin cadence alert rules (acceptance, give-up, max_iters)"
```

---

### Task 14: Link `AgentEvent` rows to Phoenix traces (C3)

**Files:**
- Modify: `src/models/ai.py` — add `trace_id` column to `AgentEvent`
- Modify: `src/agents/base.py:_store_event` — populate from current OTel span
- Test: `tests/agents/test_agent_event_trace_id.py` (create)

- [ ] **Step 14.1: Write failing test**

```python
# tests/agents/test_agent_event_trace_id.py
from unittest.mock import patch, MagicMock
from src.agents.base import BaseAgent
from src.models.ai import AgentEvent

class _Dummy(BaseAgent):
    agent_name = "trace_test"
    mcp_server_labels = []
    def _get_tools(self): return []

def test_agent_event_has_trace_id_column():
    assert "trace_id" in AgentEvent.__table__.columns

@patch("src.agents.base.dspy")
@patch("src.agents.base.trace")
def test_store_event_populates_trace_id_from_current_span(mock_trace, mock_dspy, app_context, db):
    span = MagicMock()
    span.get_span_context.return_value = MagicMock(trace_id=0xabc123, is_valid=True)
    mock_trace.get_current_span.return_value = span
    mock_dspy.ReAct.return_value = MagicMock(return_value=MagicMock(result="OK"))
    _Dummy(account_id=1).execute("test")
    row = db.session.query(AgentEvent).filter_by(agent_name="trace_test").one()
    assert row.trace_id == format(0xabc123, "032x")
```

- [ ] **Step 14.2: Run, verify fail**

```bash
pytest tests/agents/test_agent_event_trace_id.py -v
```

- [ ] **Step 14.3: Add column to `AgentEvent`**

In `src/models/ai.py`, add to the `AgentEvent` class:
```python
    trace_id = db.Column(db.String(32), nullable=True, index=True, comment="OpenTelemetry trace_id (32-hex) for Phoenix correlation")
```

- [ ] **Step 14.4: Populate from current span**

In `src/agents/base.py`, at top:
```python
from opentelemetry import trace
```

In `_store_event`, before the `event = AgentEvent(...)` construction:
```python
trace_id_hex = None
try:
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx.is_valid:
        trace_id_hex = format(ctx.trace_id, "032x")
except Exception:
    trace_id_hex = None
```

Pass `trace_id=trace_id_hex` into `AgentEvent(...)`.

- [ ] **Step 14.5: Tell user to migrate**

```
Run: flask db migrate -m "add trace_id to agent_events"
Review then: flask db upgrade  (on main, NOT in worktree)
```

- [ ] **Step 14.6: Commit**

```bash
git add src/models/ai.py src/agents/base.py tests/agents/test_agent_event_trace_id.py
git commit -m "feat(observability): link AgentEvent rows to Phoenix traces via trace_id"
```

---

## Phase 5: Cleanup (Tasks 12–13)

### Task 12: Repair `fit_score` to be graded, not binary

**Files:**
- Investigate: locate the scorer (`src/funnel/lead_qualifier.py` or `src/dspy/lead_scoring.py`)
- Modify: scorer signature/logic
- Test: assert score distribution is non-degenerate

- [ ] **Step 12.1: Locate the scorer**

```bash
grep -rn "fit_score" /Users/kofi/inboxiq/src/funnel /Users/kofi/inboxiq/src/dspy 2>/dev/null | grep -v "filter_by\|>=\|.fit_score" | head
```

- [ ] **Step 12.2: Add a test asserting graded distribution**

```python
def test_fit_score_distribution_is_graded():
    # Run scorer on 50 synthetic leads; assert >=3 distinct scores in [4..10]
    ...
```

- [ ] **Step 12.3: Replace binary "return 7" logic**

Implement graded scoring: weight industry match (3pt), title match (3pt), company size match (2pt), recency (1pt), enrichment completeness (1pt) → sum 0-10.

- [ ] **Step 12.4: Backfill `fit_score` for existing Leads (one-shot script)**

- [ ] **Step 12.5: Commit**

```bash
git commit -m "fix(scoring): replace binary fit_score=7 with graded 4-10 distribution"
```

---

### Task 13: Re-enable cadence + verify acceptance recovers

**Files:** kubectl ops only

- [ ] **Step 13.1: Re-enable beat schedule**

Reverse Step 0.1 — uncomment the four `linkedin.*` entries.

- [ ] **Step 13.2: Run discover_prospects manually for one account, inspect output**

```bash
kubectl exec -n kaley deploy/inboxiq -- python -c "
from src.app import create_app
from src.tasks.linkedin import discover_prospects
app = create_app()
with app.app_context():
    print(discover_prospects())
"
```

- [ ] **Step 13.3: Inspect 5 newly-created prospects — assert no garbage**

Reuse the audit script from Step 0.2 but in dry-run mode.

- [ ] **Step 13.4: Send 2 connection requests manually, watch metrics for 24h**

Validation criteria:
- `inboxiq_linkedin_acceptance_ratio` ≥ 0.25 over 7 days
- `inboxiq_agent_status{status="success"}` rate > 0
- `inboxiq_agent_react_max_iters_hit_total` rate ≈ 0
- `inboxiq_linkedin_prospect_status_transitions_total{to_status="connected"}` increasing

- [ ] **Step 13.5: If validation fails, return to Phase 3 — investigate trace IDs in Phoenix**

---

## Self-Review Checklist (run before handoff)

- [ ] Each issue (A1-A6, B1-B4, C1-C4, D1-D2) maps to a task above — verify by re-reading the issue list
- [ ] No "TBD" / "implement later" / "appropriate validation" placeholders
- [ ] Function names consistent (`looks_like_real_company` everywhere — not `is_real_company` in some places)
- [ ] Migration step (Task 3.6) flagged with the worktree warning per memory: never run migrations in worktrees
- [ ] Each phase ends with a passing test before commit
- [ ] CLAUDE.md compliance: try/except + rollback around every commit; `account_id`-scoped queries

---

**Plan complete and saved to `docs/superpowers/plans/2026-05-10-linkedin-cadence-data-quality.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
