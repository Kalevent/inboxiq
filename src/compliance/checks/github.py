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
