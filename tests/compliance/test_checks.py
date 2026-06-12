from unittest.mock import MagicMock, patch
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
    with patch("src.compliance.checks.aws.run_aws_checks", return_value=[]) as ma, \
         patch("src.compliance.checks.github.run_github_checks", return_value=[]) as mg, \
         patch("src.compliance.checks.stripe_checks.run_stripe_checks", return_value=[]) as ms:
        from src.compliance.runner import run_all_checks
        results = run_all_checks()
        assert isinstance(results, list)
        ma.assert_called_once()
        mg.assert_called_once()
        ms.assert_called_once()


# ── AWS helpers ──────────────────────────────────────────────────────────────

def _iam_client(users=None, root_has_keys=False):
    """Build a mock IAM client."""
    client = MagicMock()
    users = users or [{"UserName": "kofi", "UserId": "AID1"}]
    client.list_users.return_value = {"Users": users}
    def mfa_side_effect(UserName):
        return {"MFADevices": [{"SerialNumber": "arn:mfa:1"}]}
    client.list_mfa_devices.side_effect = mfa_side_effect
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
    ct.describe_trails.return_value = {"trailList": [{"Name": "main", "HomeRegion": "eu-west-2"}]}
    ct.get_trail_status.return_value = {"IsLogging": True}
    from src.compliance.checks.aws import check_cloudtrail
    result = check_cloudtrail(ct)
    assert result.status == STATUS_PASS


def test_aws_cloudtrail_fail_not_logging():
    ct = MagicMock()
    ct.describe_trails.return_value = {"trailList": [{"Name": "main", "HomeRegion": "eu-west-2"}]}
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
    assert result.status == STATUS_PASS
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


# ── Report tests ──────────────────────────────────────────────────────────────

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
