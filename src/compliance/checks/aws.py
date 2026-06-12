from __future__ import annotations
import logging
import os

import boto3

from src.compliance.runner import CheckResult, STATUS_PASS, STATUS_FAIL, STATUS_WARN, STATUS_ERROR

logger = logging.getLogger(__name__)


def _boto(service: str):
    return boto3.client(
        service,
        region_name=os.getenv("AWS_REGION", "eu-west-2"),
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
