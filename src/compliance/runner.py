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
