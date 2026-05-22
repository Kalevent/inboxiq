"""Monthly SOC2 evidence collection task."""
import logging
from datetime import date

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
