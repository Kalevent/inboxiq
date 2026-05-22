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
