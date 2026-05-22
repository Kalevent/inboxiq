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
