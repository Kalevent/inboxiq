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

    try:
        import boto3
        bucket = os.getenv("UPLOADS_BUCKET", "kalevent-uploads")
        s3 = boto3.client(
            "s3",
            region_name=os.getenv("AWS_REGION", "eu-west-2"),
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        )
        obj = s3.get_object(Bucket=bucket, Key=row.s3_key)
        report = json.loads(obj["Body"].read())
    except Exception as exc:
        logger.error("Failed to fetch compliance report from S3: %s", exc)
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
