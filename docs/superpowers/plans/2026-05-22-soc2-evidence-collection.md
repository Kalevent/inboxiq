# SOC2 Evidence Collection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Monthly Celery task that checks AWS, GitHub, and Stripe config against SOC2 controls, saves a structured JSON evidence report to S3, and displays a live summary in the admin panel.

**Architecture:** Three independent check modules (aws, github, stripe) each return a list of `CheckResult` dataclasses. A central runner collects them all, serialises to JSON, uploads to `s3://kalevent-uploads/compliance/reports/YYYY-MM/`, and stores the S3 key in a lightweight DB row so the admin API can retrieve the latest report without hitting S3 on every request.

**Tech Stack:** Python 3.11, boto3 (already installed), Celery Beat, Flask admin API, Jinja2 admin template, requests (already installed for GitHub API).

---

## File Map

| File | Role |
|---|---|
| `src/compliance/__init__.py` | Empty module init |
| `src/compliance/runner.py` | `CheckResult` dataclass + `run_all_checks()` orchestrator |
| `src/compliance/checks/aws.py` | 5 AWS checks (IAM MFA, root keys, S3 public access, CloudTrail, RDS encryption) |
| `src/compliance/checks/github.py` | 3 GitHub checks (branch protection, org 2FA, admin list) |
| `src/compliance/checks/stripe_checks.py` | 2 Stripe checks (webhook endpoints, webhook secret present) |
| `src/compliance/report.py` | Serialise results → JSON, upload to S3, return S3 key |
| `src/tasks/compliance.py` | `@celery.task` wrapper — calls runner + report, saves DB row |
| `src/models/compliance.py` | `ComplianceReport` SQLAlchemy model (id, period, s3_key, summary_json, created_at) |
| `src/api/v1/admin_compliance.py` | `GET /api/v1/admin/compliance/latest` — returns latest report JSON from S3 |
| `src/templates/admin/section_compliance.html` | Admin panel section: pass/warn/fail badges per check |
| `tests/compliance/test_checks.py` | Unit tests for all check functions (mocked boto3/requests) |

**Modified files:**
| File | Change |
|---|---|
| `src/celery_inboxiq.py` | Add beat schedule entry + explicit import |
| `src/config.py` | Add `GITHUB_TOKEN`, `GITHUB_ORG`, `GITHUB_REPO` config vars |
| `src/prod.env` | Add placeholder env vars |
| `src/templates/admin.html` | `{% include 'admin/section_compliance.html' %}` |
| `src/api/v1/__init__.py` | Register admin_compliance blueprint routes |

---

## Task 1: CheckResult model and runner skeleton

**Files:**
- Create: `src/compliance/__init__.py`
- Create: `src/compliance/runner.py`
- Create: `src/compliance/checks/__init__.py`
- Create: `tests/compliance/__init__.py`
- Create: `tests/compliance/test_checks.py` (partial — runner tests only)

- [ ] **Step 1: Write the failing test**

```python
# tests/compliance/test_checks.py
from src.compliance.runner import CheckResult, STATUS_PASS, STATUS_FAIL, STATUS_WARN, STATUS_ERROR

def test_check_result_fields():
    r = CheckResult(
        id="aws.iam.mfa_all_users",
        title="MFA enabled for all IAM users",
        status=STATUS_PASS,
        soc2_controls=["CC6.1"],
        details="3/3 users have MFA",
        evidence=[{"username": "kofi", "mfa_active": True}],
    )
    assert r.id == "aws.iam.mfa_all_users"
    assert r.status == "PASS"
    assert "CC6.1" in r.soc2_controls
    assert r.evidence[0]["username"] == "kofi"


def test_run_all_checks_returns_list():
    from unittest.mock import patch
    with patch("src.compliance.checks.aws.run_aws_checks", return_value=[]) as ma, \
         patch("src.compliance.checks.github.run_github_checks", return_value=[]) as mg, \
         patch("src.compliance.checks.stripe_checks.run_stripe_checks", return_value=[]) as ms:
        from src.compliance.runner import run_all_checks
        results = run_all_checks()
        assert isinstance(results, list)
        ma.assert_called_once()
        mg.assert_called_once()
        ms.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/compliance/test_checks.py::test_check_result_fields tests/compliance/test_checks.py::test_run_all_checks_returns_list -v
```
Expected: `ModuleNotFoundError: No module named 'src.compliance'`

- [ ] **Step 3: Create module files**

```python
# src/compliance/__init__.py
# (empty)
```

```python
# src/compliance/checks/__init__.py
# (empty)
```

```python
# src/compliance/runner.py
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

STATUS_PASS  = "PASS"
STATUS_WARN  = "WARN"
STATUS_FAIL  = "FAIL"
STATUS_ERROR = "ERROR"


@dataclass
class CheckResult:
    id: str
    title: str
    status: str                          # PASS | WARN | FAIL | ERROR
    soc2_controls: list[str]
    details: str
    evidence: list[dict[str, Any]] = field(default_factory=list)


def run_all_checks() -> list[CheckResult]:
    """Run all compliance checks and return combined results. Never raises."""
    results: list[CheckResult] = []
    from src.compliance.checks import aws, github, stripe_checks
    for runner, name in [
        (aws.run_aws_checks, "aws"),
        (github.run_github_checks, "github"),
        (stripe_checks.run_stripe_checks, "stripe"),
    ]:
        try:
            results.extend(runner())
        except Exception as exc:
            logger.error("compliance check module %s failed: %s", name, exc)
    return results
```

- [ ] **Step 4: Create stub check modules (needed for import)**

```python
# src/compliance/checks/aws.py
from src.compliance.runner import CheckResult
def run_aws_checks() -> list[CheckResult]:
    return []
```

```python
# src/compliance/checks/github.py
from src.compliance.runner import CheckResult
def run_github_checks() -> list[CheckResult]:
    return []
```

```python
# src/compliance/checks/stripe_checks.py
from src.compliance.runner import CheckResult
def run_stripe_checks() -> list[CheckResult]:
    return []
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/compliance/test_checks.py::test_check_result_fields tests/compliance/test_checks.py::test_run_all_checks_returns_list -v
```
Expected: `2 passed`

- [ ] **Step 6: Commit**

```bash
git add src/compliance/ tests/compliance/
git commit -m "feat(compliance): add CheckResult model and runner skeleton"
```

---

## Task 2: AWS checks

**Files:**
- Modify: `src/compliance/checks/aws.py`
- Modify: `tests/compliance/test_checks.py` (add AWS tests)

The five checks and their SOC2 mappings:
| Check ID | What it tests | SOC2 control |
|---|---|---|
| `aws.iam.mfa_all_users` | All IAM users (not service accounts) have MFA active | CC6.1 |
| `aws.iam.no_root_access_keys` | Root account has no active access keys | CC6.1 |
| `aws.s3.block_public_access` | All S3 buckets have BlockPublicAcls+IgnorePublicAcls | CC6.1 |
| `aws.cloudtrail.enabled` | At least one CloudTrail trail is logging | CC7.2 |
| `aws.rds.encryption_at_rest` | All RDS instances have `StorageEncrypted=True` | CC6.1 |

- [ ] **Step 1: Write failing AWS tests**

Add to `tests/compliance/test_checks.py`:

```python
from unittest.mock import MagicMock, patch
from src.compliance.runner import STATUS_PASS, STATUS_FAIL, STATUS_WARN, STATUS_ERROR


# ── AWS helpers ──────────────────────────────────────────────────────────────

def _iam_client(users=None, root_has_keys=False):
    """Build a mock IAM client."""
    client = MagicMock()
    users = users or [{"UserName": "kofi", "UserId": "AID1"}]
    client.list_users.return_value = {"Users": users}
    # MFA devices per user
    def mfa_side_effect(UserName):
        return {"MFADevices": [{"SerialNumber": "arn:mfa:1"}]}
    client.list_mfa_devices.side_effect = mfa_side_effect
    # Root summary
    summary = {"AccountMFAEnabled": 1, "AccountAccessKeysPresent": 1 if root_has_keys else 0}
    client.get_account_summary.return_value = {"SummaryMap": summary}
    return client


def test_aws_iam_mfa_all_pass():
    from src.compliance.checks.aws import check_iam_mfa
    result = check_iam_mfa(_iam_client())
    assert result.status == STATUS_PASS
    assert result.id == "aws.iam.mfa_all_users"
    assert "CC6.1" in result.soc2_controls


def test_aws_iam_mfa_fail_when_user_missing_mfa():
    client = _iam_client()
    client.list_mfa_devices.side_effect = lambda UserName: {"MFADevices": []}
    from src.compliance.checks.aws import check_iam_mfa
    result = check_iam_mfa(client)
    assert result.status == STATUS_FAIL
    assert "kofi" in result.details


def test_aws_iam_no_root_keys_pass():
    from src.compliance.checks.aws import check_root_no_access_keys
    result = check_root_no_access_keys(_iam_client(root_has_keys=False))
    assert result.status == STATUS_PASS


def test_aws_iam_root_keys_fail():
    from src.compliance.checks.aws import check_root_no_access_keys
    result = check_root_no_access_keys(_iam_client(root_has_keys=True))
    assert result.status == STATUS_FAIL


def test_aws_s3_public_access_pass():
    s3 = MagicMock()
    s3.list_buckets.return_value = {"Buckets": [{"Name": "kalevent-uploads"}]}
    s3.get_public_access_block.return_value = {
        "PublicAccessBlockConfiguration": {
            "BlockPublicAcls": True, "IgnorePublicAcls": True,
            "BlockPublicPolicy": True, "RestrictPublicBuckets": True,
        }
    }
    from src.compliance.checks.aws import check_s3_public_access
    result = check_s3_public_access(s3)
    assert result.status == STATUS_PASS


def test_aws_cloudtrail_pass():
    ct = MagicMock()
    ct.describe_trails.return_value = {"trailList": [{"Name": "main", "HomeRegion": "us-west-2"}]}
    ct.get_trail_status.return_value = {"IsLogging": True}
    from src.compliance.checks.aws import check_cloudtrail
    result = check_cloudtrail(ct)
    assert result.status == STATUS_PASS


def test_aws_cloudtrail_fail_not_logging():
    ct = MagicMock()
    ct.describe_trails.return_value = {"trailList": [{"Name": "main", "HomeRegion": "us-west-2"}]}
    ct.get_trail_status.return_value = {"IsLogging": False}
    from src.compliance.checks.aws import check_cloudtrail
    result = check_cloudtrail(ct)
    assert result.status == STATUS_FAIL


def test_aws_rds_encryption_pass():
    rds = MagicMock()
    rds.describe_db_instances.return_value = {
        "DBInstances": [{"DBInstanceIdentifier": "inboxiq-db", "StorageEncrypted": True}]
    }
    from src.compliance.checks.aws import check_rds_encryption
    result = check_rds_encryption(rds)
    assert result.status == STATUS_PASS


def test_aws_rds_encryption_fail():
    rds = MagicMock()
    rds.describe_db_instances.return_value = {
        "DBInstances": [{"DBInstanceIdentifier": "inboxiq-db", "StorageEncrypted": False}]
    }
    from src.compliance.checks.aws import check_rds_encryption
    result = check_rds_encryption(rds)
    assert result.status == STATUS_FAIL
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/compliance/test_checks.py -k "aws" -v
```
Expected: `ImportError` or `AttributeError` on missing check functions.

- [ ] **Step 3: Implement AWS checks**

```python
# src/compliance/checks/aws.py
from __future__ import annotations
import logging
import os
from typing import Any

import boto3

from src.compliance.runner import CheckResult, STATUS_PASS, STATUS_FAIL, STATUS_WARN, STATUS_ERROR

logger = logging.getLogger(__name__)


def _boto(service: str):
    return boto3.client(
        service,
        region_name=os.getenv("AWS_REGION", "us-west-2"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )


def check_iam_mfa(iam=None) -> CheckResult:
    iam = iam or _boto("iam")
    users = iam.list_users()["Users"]
    missing = []
    evidence = []
    for u in users:
        name = u["UserName"]
        devices = iam.list_mfa_devices(UserName=name)["MFADevices"]
        has_mfa = len(devices) > 0
        evidence.append({"username": name, "mfa_active": has_mfa})
        if not has_mfa:
            missing.append(name)
    status = STATUS_PASS if not missing else STATUS_FAIL
    details = (
        f"{len(users) - len(missing)}/{len(users)} users have MFA enabled"
        if not missing
        else f"Missing MFA: {', '.join(missing)}"
    )
    return CheckResult(
        id="aws.iam.mfa_all_users",
        title="MFA enabled for all IAM users",
        status=status,
        soc2_controls=["CC6.1"],
        details=details,
        evidence=evidence,
    )


def check_root_no_access_keys(iam=None) -> CheckResult:
    iam = iam or _boto("iam")
    summary = iam.get_account_summary()["SummaryMap"]
    has_keys = summary.get("AccountAccessKeysPresent", 0) > 0
    return CheckResult(
        id="aws.iam.no_root_access_keys",
        title="Root account has no active access keys",
        status=STATUS_FAIL if has_keys else STATUS_PASS,
        soc2_controls=["CC6.1"],
        details="Root account has active access keys — delete them immediately" if has_keys else "No root access keys present",
        evidence=[{"root_access_keys_present": has_keys}],
    )


def check_s3_public_access(s3=None) -> CheckResult:
    s3 = s3 or _boto("s3")
    buckets = [b["Name"] for b in s3.list_buckets().get("Buckets", [])]
    exposed = []
    evidence = []
    for bucket in buckets:
        try:
            cfg = s3.get_public_access_block(Bucket=bucket)["PublicAccessBlockConfiguration"]
            blocked = cfg.get("BlockPublicAcls", False) and cfg.get("IgnorePublicAcls", False)
        except Exception:
            blocked = False
        evidence.append({"bucket": bucket, "public_access_blocked": blocked})
        if not blocked:
            exposed.append(bucket)
    status = STATUS_PASS if not exposed else STATUS_FAIL
    details = (
        f"All {len(buckets)} buckets block public access"
        if not exposed
        else f"Public access not fully blocked: {', '.join(exposed)}"
    )
    return CheckResult(
        id="aws.s3.block_public_access",
        title="S3 buckets block public access",
        status=status,
        soc2_controls=["CC6.1"],
        details=details,
        evidence=evidence,
    )


def check_cloudtrail(cloudtrail=None) -> CheckResult:
    ct = cloudtrail or _boto("cloudtrail")
    trails = ct.describe_trails(includeShadowTrails=False).get("trailList", [])
    active = []
    evidence = []
    for t in trails:
        name = t["Name"]
        logging_status = ct.get_trail_status(Name=name).get("IsLogging", False)
        evidence.append({"trail": name, "is_logging": logging_status})
        if logging_status:
            active.append(name)
    if not trails:
        status, details = STATUS_FAIL, "No CloudTrail trails configured"
    elif not active:
        status, details = STATUS_FAIL, f"CloudTrail trails exist but none are logging: {[t['Name'] for t in trails]}"
    else:
        status, details = STATUS_PASS, f"{len(active)} trail(s) actively logging"
    return CheckResult(
        id="aws.cloudtrail.enabled",
        title="CloudTrail logging enabled",
        status=status,
        soc2_controls=["CC7.2"],
        details=details,
        evidence=evidence,
    )


def check_rds_encryption(rds=None) -> CheckResult:
    rds = rds or _boto("rds")
    instances = rds.describe_db_instances().get("DBInstances", [])
    unencrypted = []
    evidence = []
    for db in instances:
        enc = db.get("StorageEncrypted", False)
        evidence.append({"db_instance": db["DBInstanceIdentifier"], "encrypted": enc})
        if not enc:
            unencrypted.append(db["DBInstanceIdentifier"])
    if not instances:
        status, details = STATUS_WARN, "No RDS instances found — nothing to check"
    elif unencrypted:
        status, details = STATUS_FAIL, f"Unencrypted RDS instances: {', '.join(unencrypted)}"
    else:
        status, details = STATUS_PASS, f"All {len(instances)} RDS instance(s) encrypted at rest"
    return CheckResult(
        id="aws.rds.encryption_at_rest",
        title="RDS instances encrypted at rest",
        status=status,
        soc2_controls=["CC6.1"],
        details=details,
        evidence=evidence,
    )


def run_aws_checks() -> list[CheckResult]:
    results = []
    for fn in [check_iam_mfa, check_root_no_access_keys, check_s3_public_access, check_cloudtrail, check_rds_encryption]:
        try:
            results.append(fn())
        except Exception as exc:
            results.append(CheckResult(
                id=f"aws.{fn.__name__}",
                title=fn.__name__,
                status=STATUS_ERROR,
                soc2_controls=[],
                details=f"Check failed: {exc}",
            ))
    return results
```

- [ ] **Step 4: Run AWS tests**

```bash
python -m pytest tests/compliance/test_checks.py -k "aws" -v
```
Expected: `9 passed`

- [ ] **Step 5: Commit**

```bash
git add src/compliance/checks/aws.py tests/compliance/test_checks.py
git commit -m "feat(compliance): add AWS SOC2 checks (IAM MFA, S3, CloudTrail, RDS)"
```

---

## Task 3: GitHub and Stripe checks

**Files:**
- Modify: `src/compliance/checks/github.py`
- Modify: `src/compliance/checks/stripe_checks.py`
- Modify: `src/config.py`
- Modify: `src/prod.env`
- Modify: `tests/compliance/test_checks.py` (add GitHub and Stripe tests)

GitHub uses the REST API via `requests`. Stripe uses the `stripe` SDK already installed.

- [ ] **Step 1: Add config vars**

In `src/config.py`, add inside the `Config` class:
```python
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")       # personal access token, read:org + repo scopes
GITHUB_ORG   = os.getenv("GITHUB_ORG", "k0f1")
GITHUB_REPO  = os.getenv("GITHUB_REPO", "inboxiq")
```

In `src/prod.env`, add:
```
GITHUB_TOKEN=ghp_your_token_here
GITHUB_ORG=k0f1
GITHUB_REPO=inboxiq
```

- [ ] **Step 2: Write failing GitHub and Stripe tests**

Add to `tests/compliance/test_checks.py`:

```python
# ── GitHub helpers ────────────────────────────────────────────────────────────

def _gh_response(json_data, status=200):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = json_data
    r.ok = status < 400
    return r


def test_github_branch_protection_pass():
    from src.compliance.checks.github import check_branch_protection
    protection = {
        "required_pull_request_reviews": {"required_approving_review_count": 1},
        "required_status_checks": {"strict": True, "contexts": []},
        "enforce_admins": {"enabled": True},
    }
    with patch("requests.get", return_value=_gh_response(protection)):
        result = check_branch_protection("token", "k0f1", "inboxiq")
    assert result.status == STATUS_PASS
    assert result.id == "github.branch_protection.main"


def test_github_branch_protection_fail_no_reviews():
    from src.compliance.checks.github import check_branch_protection
    with patch("requests.get", return_value=_gh_response({}, status=404)):
        result = check_branch_protection("token", "k0f1", "inboxiq")
    assert result.status == STATUS_FAIL


def test_github_org_2fa_pass():
    from src.compliance.checks.github import check_org_two_factor
    org_data = {"two_factor_requirement_enabled": True, "login": "k0f1"}
    with patch("requests.get", return_value=_gh_response(org_data)):
        result = check_org_two_factor("token", "k0f1")
    assert result.status == STATUS_PASS
    assert result.id == "github.org.two_factor_required"


def test_github_org_2fa_fail():
    from src.compliance.checks.github import check_org_two_factor
    org_data = {"two_factor_requirement_enabled": False, "login": "k0f1"}
    with patch("requests.get", return_value=_gh_response(org_data)):
        result = check_org_two_factor("token", "k0f1")
    assert result.status == STATUS_FAIL


def test_github_admin_list_pass():
    from src.compliance.checks.github import check_admin_access_list
    members = [{"login": "k0f1", "role": "admin"}, {"login": "dev2", "role": "member"}]
    with patch("requests.get", return_value=_gh_response(members)):
        result = check_admin_access_list("token", "k0f1")
    assert result.status == STATUS_PASS  # always PASS — evidence gathering only
    assert any(e["login"] == "k0f1" for e in result.evidence)


# ── Stripe helpers ────────────────────────────────────────────────────────────

def test_stripe_webhook_secret_present():
    from src.compliance.checks.stripe_checks import check_webhook_secret_configured
    from flask import Flask
    app = Flask(__name__)
    app.config["STRIPE_WEBHOOK_SECRET"] = "whsec_abc123"
    with app.app_context():
        result = check_webhook_secret_configured()
    assert result.status == STATUS_PASS
    assert result.id == "stripe.webhooks.secret_configured"


def test_stripe_webhook_secret_missing():
    from src.compliance.checks.stripe_checks import check_webhook_secret_configured
    from flask import Flask
    app = Flask(__name__)
    app.config["STRIPE_WEBHOOK_SECRET"] = None
    with app.app_context():
        result = check_webhook_secret_configured()
    assert result.status == STATUS_FAIL


def test_stripe_webhook_endpoints_registered():
    from src.compliance.checks.stripe_checks import check_webhook_endpoints
    mock_endpoint = MagicMock()
    mock_endpoint.url = "https://kalevent.com/api/v1/billing/webhooks/stripe"
    mock_endpoint.enabled_events = ["customer.subscription.updated", "invoice.paid"]
    mock_endpoint.status = "enabled"
    with patch("stripe.WebhookEndpoint.list", return_value=MagicMock(auto_spec=True, data=[mock_endpoint])):
        from flask import Flask
        app = Flask(__name__)
        app.config["STRIPE_SECRET_KEY"] = "sk_test_abc"
        with app.app_context():
            result = check_webhook_endpoints()
    assert result.status == STATUS_PASS
    assert result.id == "stripe.webhooks.endpoints_registered"
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
python -m pytest tests/compliance/test_checks.py -k "github or stripe" -v
```
Expected: `AttributeError` or `ImportError` on missing functions.

- [ ] **Step 4: Implement GitHub checks**

```python
# src/compliance/checks/github.py
from __future__ import annotations
import logging
from flask import current_app
import requests
from src.compliance.runner import CheckResult, STATUS_PASS, STATUS_FAIL, STATUS_WARN, STATUS_ERROR

logger = logging.getLogger(__name__)

_GH_API = "https://api.github.com"


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}


def check_branch_protection(token: str, org: str, repo: str) -> CheckResult:
    url = f"{_GH_API}/repos/{org}/{repo}/branches/main/protection"
    r = requests.get(url, headers=_headers(token), timeout=10)
    if not r.ok:
        return CheckResult(
            id="github.branch_protection.main",
            title="main branch has protection rules",
            status=STATUS_FAIL,
            soc2_controls=["CC8.1"],
            details=f"Branch protection not configured or API error (HTTP {r.status_code})",
        )
    data = r.json()
    has_reviews = bool(data.get("required_pull_request_reviews"))
    details = "Branch protection enabled with required PR reviews" if has_reviews else "Branch protection exists but PR reviews not required"
    return CheckResult(
        id="github.branch_protection.main",
        title="main branch has protection rules",
        status=STATUS_PASS if has_reviews else STATUS_WARN,
        soc2_controls=["CC8.1"],
        details=details,
        evidence=[{"enforce_admins": data.get("enforce_admins", {}).get("enabled"), "pr_reviews_required": has_reviews}],
    )


def check_org_two_factor(token: str, org: str) -> CheckResult:
    url = f"{_GH_API}/orgs/{org}"
    r = requests.get(url, headers=_headers(token), timeout=10)
    if not r.ok:
        return CheckResult(
            id="github.org.two_factor_required",
            title="GitHub org requires 2FA for all members",
            status=STATUS_ERROR,
            soc2_controls=["CC6.1"],
            details=f"Could not retrieve org info (HTTP {r.status_code}) — token needs read:org scope",
        )
    enabled = r.json().get("two_factor_requirement_enabled", False)
    return CheckResult(
        id="github.org.two_factor_required",
        title="GitHub org requires 2FA for all members",
        status=STATUS_PASS if enabled else STATUS_FAIL,
        soc2_controls=["CC6.1"],
        details="2FA required for all org members" if enabled else "2FA NOT required — enable in org Security settings",
        evidence=[{"org": org, "two_factor_requirement_enabled": enabled}],
    )


def check_admin_access_list(token: str, org: str) -> CheckResult:
    """Evidence-gathering only — always PASS. Records who has admin access."""
    url = f"{_GH_API}/orgs/{org}/members?role=admin&per_page=100"
    r = requests.get(url, headers=_headers(token), timeout=10)
    admins = [{"login": m["login"]} for m in (r.json() if r.ok else [])]
    return CheckResult(
        id="github.access.admin_list",
        title="GitHub org admin access list",
        status=STATUS_PASS,
        soc2_controls=["CC6.2"],
        details=f"{len(admins)} admin(s) recorded for periodic access review",
        evidence=admins,
    )


def run_github_checks() -> list[CheckResult]:
    token = current_app.config.get("GITHUB_TOKEN") or ""
    org   = current_app.config.get("GITHUB_ORG") or "k0f1"
    repo  = current_app.config.get("GITHUB_REPO") or "inboxiq"
    if not token:
        return [CheckResult(
            id="github.config.missing_token",
            title="GitHub checks skipped",
            status=STATUS_WARN,
            soc2_controls=["CC6.1", "CC8.1"],
            details="GITHUB_TOKEN not configured — set it to enable GitHub compliance checks",
        )]
    results = []
    for fn, kwargs in [
        (check_branch_protection, {"token": token, "org": org, "repo": repo}),
        (check_org_two_factor,    {"token": token, "org": org}),
        (check_admin_access_list, {"token": token, "org": org}),
    ]:
        try:
            results.append(fn(**kwargs))
        except Exception as exc:
            results.append(CheckResult(id=f"github.{fn.__name__}", title=fn.__name__, status=STATUS_ERROR, soc2_controls=[], details=str(exc)))
    return results
```

- [ ] **Step 5: Implement Stripe checks**

```python
# src/compliance/checks/stripe_checks.py
from __future__ import annotations
import logging
import stripe
from flask import current_app
from src.compliance.runner import CheckResult, STATUS_PASS, STATUS_FAIL, STATUS_ERROR

logger = logging.getLogger(__name__)


def check_webhook_secret_configured() -> CheckResult:
    secret = current_app.config.get("STRIPE_WEBHOOK_SECRET")
    return CheckResult(
        id="stripe.webhooks.secret_configured",
        title="Stripe webhook signature secret configured",
        status=STATUS_PASS if secret else STATUS_FAIL,
        soc2_controls=["CC6.6"],
        details="STRIPE_WEBHOOK_SECRET is set — incoming webhooks are signature-verified" if secret
                else "STRIPE_WEBHOOK_SECRET is missing — webhooks are NOT verified",
        evidence=[{"secret_present": bool(secret)}],
    )


def check_webhook_endpoints() -> CheckResult:
    api_key = current_app.config.get("STRIPE_SECRET_KEY")
    if not api_key:
        return CheckResult(
            id="stripe.webhooks.endpoints_registered",
            title="Stripe webhook endpoints registered",
            status=STATUS_ERROR,
            soc2_controls=["CC6.6"],
            details="STRIPE_SECRET_KEY not set — cannot check Stripe webhook endpoints",
        )
    stripe.api_key = api_key
    try:
        endpoints = stripe.WebhookEndpoint.list(limit=20)
        enabled = [e for e in endpoints.data if e.status == "enabled"]
        evidence = [{"url": e.url, "status": e.status, "events": e.enabled_events} for e in endpoints.data]
    except Exception as exc:
        return CheckResult(
            id="stripe.webhooks.endpoints_registered",
            title="Stripe webhook endpoints registered",
            status=STATUS_ERROR,
            soc2_controls=["CC6.6"],
            details=f"Stripe API error: {exc}",
        )
    status = STATUS_PASS if enabled else STATUS_FAIL
    details = (
        f"{len(enabled)} enabled webhook endpoint(s) registered"
        if enabled
        else "No enabled webhook endpoints found in Stripe"
    )
    return CheckResult(
        id="stripe.webhooks.endpoints_registered",
        title="Stripe webhook endpoints registered",
        status=status,
        soc2_controls=["CC6.6"],
        details=details,
        evidence=evidence,
    )


def run_stripe_checks() -> list[CheckResult]:
    results = []
    for fn in [check_webhook_secret_configured, check_webhook_endpoints]:
        try:
            results.append(fn())
        except Exception as exc:
            results.append(CheckResult(id=f"stripe.{fn.__name__}", title=fn.__name__, status=STATUS_ERROR, soc2_controls=[], details=str(exc)))
    return results
```

- [ ] **Step 6: Run GitHub and Stripe tests**

```bash
python -m pytest tests/compliance/test_checks.py -k "github or stripe" -v
```
Expected: `8 passed`

- [ ] **Step 7: Run full test suite**

```bash
python -m pytest tests/compliance/ -v
```
Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add src/compliance/checks/github.py src/compliance/checks/stripe_checks.py src/config.py src/prod.env tests/compliance/test_checks.py
git commit -m "feat(compliance): add GitHub and Stripe SOC2 checks"
```

---

## Task 4: Report serialiser, S3 upload, DB model, and Celery task

**Files:**
- Create: `src/compliance/report.py`
- Create: `src/models/compliance.py`
- Create: `src/tasks/compliance.py`
- Modify: `src/celery_inboxiq.py`
- Modify: `tests/compliance/test_checks.py` (add report tests)

The DB model is a single row per run — stores the S3 key and a summary so the admin API doesn't need to fetch from S3 for the list view.

- [ ] **Step 1: Write failing report and task tests**

Add to `tests/compliance/test_checks.py`:

```python
def test_build_report_json():
    from src.compliance.runner import CheckResult, STATUS_PASS, STATUS_FAIL
    from src.compliance.report import build_report_json
    results = [
        CheckResult(id="aws.iam.mfa_all_users", title="MFA", status=STATUS_PASS, soc2_controls=["CC6.1"], details="ok"),
        CheckResult(id="aws.rds.encryption", title="RDS enc", status=STATUS_FAIL, soc2_controls=["CC6.1"], details="fail"),
    ]
    report = build_report_json(results, period="2026-05")
    assert report["period"] == "2026-05"
    assert report["summary"]["pass"] == 1
    assert report["summary"]["fail"] == 1
    assert len(report["checks"]) == 2
    assert "generated_at" in report


def test_s3_key_format():
    from src.compliance.report import s3_key_for
    from datetime import date
    key = s3_key_for(date(2026, 5, 22))
    assert key == "compliance/reports/2026-05/soc2-evidence-2026-05-22.json"
```

- [ ] **Step 2: Run to verify they fail**

```bash
python -m pytest tests/compliance/test_checks.py::test_build_report_json tests/compliance/test_checks.py::test_s3_key_format -v
```
Expected: `ImportError`

- [ ] **Step 3: Implement report module**

```python
# src/compliance/report.py
from __future__ import annotations
import json
import logging
import os
from dataclasses import asdict
from datetime import date, datetime, timezone
from typing import Any

from src.compliance.runner import CheckResult, STATUS_PASS, STATUS_FAIL, STATUS_WARN, STATUS_ERROR

logger = logging.getLogger(__name__)


def s3_key_for(d: date) -> str:
    return f"compliance/reports/{d.strftime('%Y-%m')}/soc2-evidence-{d.isoformat()}.json"


def build_report_json(results: list[CheckResult], period: str) -> dict[str, Any]:
    summary = {STATUS_PASS: 0, STATUS_WARN: 0, STATUS_FAIL: 0, STATUS_ERROR: 0}
    for r in results:
        summary[r.status] = summary.get(r.status, 0) + 1
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "period": period,
        "summary": {
            "pass":  summary[STATUS_PASS],
            "warn":  summary[STATUS_WARN],
            "fail":  summary[STATUS_FAIL],
            "error": summary[STATUS_ERROR],
            "total": len(results),
        },
        "checks": [asdict(r) for r in results],
    }


def upload_report(report: dict[str, Any], s3_key: str) -> str:
    """Upload report JSON to S3. Returns the S3 key."""
    import boto3
    bucket = os.getenv("UPLOADS_BUCKET", "kalevent-uploads")
    body = json.dumps(report, indent=2, default=str).encode()
    s3 = boto3.client(
        "s3",
        region_name=os.getenv("AWS_REGION", "us-west-2"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )
    s3.put_object(
        Bucket=bucket,
        Key=s3_key,
        Body=body,
        ContentType="application/json",
        ServerSideEncryption="AES256",
    )
    logger.info("compliance report uploaded s3://%s/%s", bucket, s3_key)
    return s3_key
```

- [ ] **Step 4: Run report tests**

```bash
python -m pytest tests/compliance/test_checks.py::test_build_report_json tests/compliance/test_checks.py::test_s3_key_format -v
```
Expected: `2 passed`

- [ ] **Step 5: Create ComplianceReport model**

```python
# src/models/compliance.py
from __future__ import annotations
from uuid import uuid4
from sqlalchemy.sql import func
from src.extensions import db


class ComplianceReport(db.Model):
    __tablename__ = "compliance_reports"

    id         = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()))
    period     = db.Column(db.String(7), nullable=False)           # "2026-05"
    s3_key     = db.Column(db.String(512), nullable=False)
    summary    = db.Column(db.JSON, nullable=False, default=dict)  # {pass,warn,fail,error,total}
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
```

Tell the user to run:
```bash
flask db migrate -m "add compliance_reports table"
flask db upgrade
```

- [ ] **Step 6: Create the Celery task**

```python
# src/tasks/compliance.py
"""Monthly SOC2 evidence collection task."""
import logging
from datetime import date, datetime, timezone

from src.celery_inboxiq import celery
from src.extensions import db

logger = logging.getLogger(__name__)


@celery.task(
    name="compliance.run_soc2_evidence_collection",
    queue="inbox",
    ignore_result=True,
)
def run_soc2_evidence_collection() -> None:
    """Run all compliance checks, upload report to S3, save DB row."""
    from src.compliance.runner import run_all_checks
    from src.compliance.report import build_report_json, upload_report, s3_key_for
    from src.models.compliance import ComplianceReport

    today = date.today()
    period = today.strftime("%Y-%m")
    s3_key = s3_key_for(today)

    try:
        results = run_all_checks()
        report  = build_report_json(results, period=period)
        upload_report(report, s3_key)

        row = ComplianceReport(period=period, s3_key=s3_key, summary=report["summary"])
        db.session.add(row)
        db.session.commit()
        logger.info(
            "compliance report complete period=%s pass=%d warn=%d fail=%d",
            period, report["summary"]["pass"], report["summary"]["warn"], report["summary"]["fail"],
        )
    except Exception as exc:
        db.session.rollback()
        logger.error("compliance task failed: %s", exc)
        raise
```

- [ ] **Step 7: Register task in celery_inboxiq.py**

In `src/celery_inboxiq.py`, add to the `beat_schedule` dict (alongside `audit_log_purge`):

```python
"compliance_monthly_collection": {
    "task": "compliance.run_soc2_evidence_collection",
    "schedule": crontab(day_of_month=1, hour=9, minute=0),
    "options": {"queue": "inbox"},
},
```

At the bottom of the file, add the explicit import line:

```python
from src.tasks import compliance as _compliance_tasks  # noqa: F401
```

- [ ] **Step 8: Run all compliance tests**

```bash
python -m pytest tests/compliance/ -v
```
Expected: all passing.

- [ ] **Step 9: Commit**

```bash
git add src/compliance/report.py src/models/compliance.py src/tasks/compliance.py src/celery_inboxiq.py tests/compliance/
git commit -m "feat(compliance): report serialiser, S3 upload, DB model, monthly Celery task"
```

---

## Task 5: Admin API endpoint and UI panel

**Files:**
- Create: `src/api/v1/admin_compliance.py`
- Create: `src/templates/admin/section_compliance.html`
- Modify: `src/api/v1/__init__.py` (register routes)
- Modify: `src/templates/admin.html` (include section)

- [ ] **Step 1: Create admin API endpoint**

```python
# src/api/v1/admin_compliance.py
"""Admin endpoint: latest compliance report."""
import json
import logging
import os

from flask import jsonify
from flask_jwt_extended import jwt_required

from src.api.v1 import v1
from src.api.v1.admin import _require_admin

logger = logging.getLogger(__name__)


@v1.route("/admin/compliance/latest", methods=["GET"])
@jwt_required()
def get_latest_compliance_report():
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    from src.models.compliance import ComplianceReport
    row = ComplianceReport.query.order_by(ComplianceReport.created_at.desc()).first()
    if not row:
        return jsonify({"report": None, "message": "No compliance reports yet — run the task manually to generate the first report."})

    # Fetch full report from S3
    try:
        import boto3
        bucket = os.getenv("UPLOADS_BUCKET", "kalevent-uploads")
        s3 = boto3.client(
            "s3",
            region_name=os.getenv("AWS_REGION", "us-west-2"),
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        )
        obj = s3.get_object(Bucket=bucket, Key=row.s3_key)
        report = json.loads(obj["Body"].read())
    except Exception as exc:
        logger.error("Failed to fetch compliance report from S3: %s", exc)
        # Fall back to summary-only
        report = {"period": row.period, "summary": row.summary, "checks": [], "s3_error": str(exc)}

    return jsonify({"report": report, "s3_key": row.s3_key, "generated_at": row.created_at.isoformat()})


@v1.route("/admin/compliance/trigger", methods=["POST"])
@jwt_required()
def trigger_compliance_run():
    """Manually trigger a compliance check run. Admin only."""
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    from src.tasks.compliance import run_soc2_evidence_collection
    run_soc2_evidence_collection.delay()
    return jsonify({"status": "queued", "message": "Compliance check queued — refresh in ~30 seconds."})
```

- [ ] **Step 2: Register routes**

In `src/api/v1/__init__.py`, add:
```python
from src.api.v1 import admin_compliance  # noqa: F401
```

- [ ] **Step 3: Create admin section template**

```html
<!-- src/templates/admin/section_compliance.html -->
<section id="section-compliance" class="admin-section">
  <div class="content-container space-y-6">
    <div class="flex items-start justify-between">
      <div>
        <h1 class="text-2xl font-semibold tracking-tight">SOC2 Compliance</h1>
        <p class="text-sm text-slate-300 mt-1">Monthly automated evidence collection — AWS, GitHub, and Stripe controls.</p>
      </div>
      <button onclick="triggerComplianceRun()"
              class="rounded-lg bg-indigo-500 hover:bg-indigo-400 px-4 py-2 text-sm font-semibold text-white">
        Run now
      </button>
    </div>

    <div id="compliance-summary" class="grid grid-cols-4 gap-3"></div>
    <div id="compliance-checks" class="space-y-2"></div>
    <p id="compliance-meta" class="text-xs text-slate-500"></p>
  </div>

  <script>
    (function loadCompliance() {
      fetch('/api/v1/admin/compliance/latest', { credentials: 'include' })
        .then(r => r.json())
        .then(data => {
          const report = data.report;
          if (!report) {
            document.getElementById('compliance-summary').innerHTML =
              '<p class="text-slate-400 text-sm col-span-4">' + (data.message || 'No reports yet.') + '</p>';
            return;
          }
          const s = report.summary;
          const pill = (n, label, colour) =>
            `<div class="rounded-xl border border-slate-700 bg-slate-900/70 p-4 text-center">
               <div class="text-2xl font-bold ${colour}">${n}</div>
               <div class="text-xs text-slate-400 mt-1">${label}</div>
             </div>`;
          document.getElementById('compliance-summary').innerHTML =
            pill(s.pass,  'Pass',  'text-emerald-400') +
            pill(s.warn,  'Warn',  'text-amber-400') +
            pill(s.fail,  'Fail',  'text-red-400') +
            pill(s.error, 'Error', 'text-slate-400');

          const badge = status => ({
            PASS:  '<span class="rounded-full bg-emerald-500/20 text-emerald-300 px-2 py-0.5 text-xs font-medium">PASS</span>',
            WARN:  '<span class="rounded-full bg-amber-500/20  text-amber-300  px-2 py-0.5 text-xs font-medium">WARN</span>',
            FAIL:  '<span class="rounded-full bg-red-500/20    text-red-300    px-2 py-0.5 text-xs font-medium">FAIL</span>',
            ERROR: '<span class="rounded-full bg-slate-700     text-slate-400  px-2 py-0.5 text-xs font-medium">ERROR</span>',
          }[status] || status);

          document.getElementById('compliance-checks').innerHTML = (report.checks || []).map(c =>
            `<div class="flex items-start justify-between rounded-lg border border-slate-800 bg-slate-900/50 px-4 py-3">
               <div>
                 <div class="text-sm text-slate-100 font-medium">${escHtml(c.title)}</div>
                 <div class="text-xs text-slate-400 mt-0.5">${escHtml(c.details)}</div>
                 <div class="text-xs text-slate-600 mt-0.5">${escHtml(c.id)} · ${(c.soc2_controls || []).join(', ')}</div>
               </div>
               <div class="ml-4 shrink-0">${badge(c.status)}</div>
             </div>`
          ).join('');

          document.getElementById('compliance-meta').textContent =
            'Period: ' + report.period + ' · Generated: ' + (report.generated_at || data.generated_at || '');
        })
        .catch(err => {
          document.getElementById('compliance-summary').innerHTML =
            '<p class="text-red-400 text-sm col-span-4">Error loading report: ' + err.message + '</p>';
        });
    })();

    async function triggerComplianceRun() {
      const r = await fetch('/api/v1/admin/compliance/trigger', {
        method: 'POST', credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
      });
      const d = await r.json();
      alert(d.message || 'Queued');
    }
  </script>
</section>
```

- [ ] **Step 4: Add section to admin.html**

In `src/templates/admin.html`, find the last `{% include 'admin/section_system.html' %}` line and add directly after:

```html
{% include 'admin/section_compliance.html' %}
```

Also add a nav entry for Compliance alongside the other sections in admin.html's sidebar/nav (look for the nav list where `section-system` appears and add):

```html
<a href="#section-compliance" class="admin-nav-item">Compliance</a>
```

- [ ] **Step 5: Run full test suite**

```bash
python -m pytest tests/compliance/ tests/billing/ -v
```
Expected: all passing.

- [ ] **Step 6: Commit**

```bash
git add src/api/v1/admin_compliance.py src/templates/admin/section_compliance.html src/templates/admin.html src/api/v1/__init__.py
git commit -m "feat(compliance): admin panel section and API endpoints for SOC2 report"
```

---

## Self-Review

**Spec coverage:**
- ✅ AWS checks: IAM MFA, root keys, S3 public access, CloudTrail, RDS encryption
- ✅ GitHub checks: branch protection, org 2FA, admin access list
- ✅ Stripe checks: webhook secret present, endpoint registered
- ✅ SOC2 control mapping on every check (CC6.1, CC6.2, CC6.6, CC7.2, CC8.1)
- ✅ JSON report saved to S3 `compliance/reports/YYYY-MM/`
- ✅ Admin panel summary with pass/warn/fail counts and per-check detail
- ✅ Monthly Celery Beat schedule (1st of month, 09:00 UTC)
- ✅ Manual trigger button in admin panel
- ✅ Tests for every check function

**Migration reminder:** After Task 4, run:
```bash
flask db migrate -m "add compliance_reports table"
flask db upgrade
```

**Env vars to add to Kubernetes secret:**
```
GITHUB_TOKEN=ghp_...   # read:org + repo scopes
GITHUB_ORG=k0f1
GITHUB_REPO=inboxiq
```
