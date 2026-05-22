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
