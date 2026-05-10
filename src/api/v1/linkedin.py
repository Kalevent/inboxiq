"""LinkedIn outreach API endpoints."""
import logging
from datetime import datetime, timedelta, timezone

from flask import Blueprint, g, jsonify, redirect, request
from src.settings import login_required_settings

from src.extensions import db
from src.models.campaigns import LinkedInProspect

log = logging.getLogger(__name__)

linkedin_api_bp = Blueprint("linkedin_api", __name__, url_prefix="/api/v1/linkedin")
linkedin_ui_bp = Blueprint("linkedin_ui", __name__)

_STATUS_TRANSITIONS = {
    "pending": ("connection_sent", "connection_sent_at"),
    "connection_sent": ("connected", "connected_at"),
    "connected": ("message_2_sent", "message_2_sent_at"),
    "message_2_sent": ("message_3_sent", "message_3_sent_at"),
    "message_3_sent": ("replied", None),
    "replied": ("qualified", None),
}


def _advance_prospect(prospect: LinkedInProspect) -> bool:
    """Advance a prospect to the next status. Returns True on success."""
    transition = _STATUS_TRANSITIONS.get(prospect.status)
    if not transition:
        return False
    from_status = prospect.status   # capture before mutation
    new_status, timestamp_field = transition
    now = datetime.now(timezone.utc)
    prospect.status = new_status
    if timestamp_field:
        setattr(prospect, timestamp_field, now)
    if timestamp_field == "connected_at":
        prospect.message_2_due_at = now + timedelta(days=3)
    if timestamp_field == "message_2_sent_at":
        prospect.message_3_due_at = now + timedelta(days=5)
    if new_status in ("replied", "qualified") and prospect.lead_id:
        _advance_lead_stage(prospect.lead_id, new_status)
    try:
        from src.monitoring.metrics import linkedin_status_transitions
        linkedin_status_transitions.labels(
            from_status=from_status,
            to_status=new_status,
            account_id=str(prospect.account_id),
        ).inc()
    except Exception:
        log.warning("failed to emit linkedin_status_transitions metric")
    return True


def _advance_lead_stage(lead_id: str, prospect_status: str):
    from src.models.leads import Lead
    lead = db.session.query(Lead).filter_by(id=lead_id).first()
    if not lead:
        return
    if prospect_status == "replied":
        lead.current_funnel_stage = "consideration"
    elif prospect_status == "qualified":
        lead.current_funnel_stage = "conversion"


# Session-auth route — used from email "Mark as sent" links
@linkedin_ui_bp.route("/marketing/linkedin/advance/<prospect_id>")
@login_required_settings
def advance_prospect(prospect_id: str):
    account_id = g.current_account_id
    prospect = db.session.query(LinkedInProspect).filter_by(
        id=prospect_id, account_id=account_id
    ).first()
    if not prospect:
        return redirect("/marketing/linkedin")
    if _advance_prospect(prospect):
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            log.exception("Failed to advance prospect %s", prospect_id)
    return redirect("/marketing/linkedin")


@linkedin_api_bp.route("/prospects/<prospect_id>/advance", methods=["POST"])
@login_required_settings
def api_advance_prospect(prospect_id: str):
    account_id = g.current_account_id
    prospect = db.session.query(LinkedInProspect).filter_by(
        id=prospect_id, account_id=account_id
    ).first()
    if not prospect:
        return jsonify({"error": "not found"}), 404
    if not _advance_prospect(prospect):
        return jsonify({"error": "no valid transition from current status"}), 400
    try:
        db.session.commit()
        return jsonify({"status": prospect.status})
    except Exception:
        db.session.rollback()
        log.exception("Failed to advance prospect %s", prospect_id)
        return jsonify({"error": "internal error"}), 500


@linkedin_api_bp.route("/prospects/<prospect_id>/disqualify", methods=["POST"])
@login_required_settings
def api_disqualify_prospect(prospect_id: str):
    account_id = g.current_account_id
    prospect = db.session.query(LinkedInProspect).filter_by(
        id=prospect_id, account_id=account_id
    ).first()
    if not prospect:
        return jsonify({"error": "not found"}), 404
    prospect.status = "disqualified"
    try:
        db.session.commit()
        return jsonify({"status": "disqualified"})
    except Exception:
        db.session.rollback()
        return jsonify({"error": "internal error"}), 500


@linkedin_api_bp.route("/prospects", methods=["POST"])
@login_required_settings
def api_add_prospect():
    """Manually add a LinkedIn prospect and trigger draft generation."""
    from src.tasks.linkedin import draft_messages_task
    account_id = g.current_account_id
    data = request.get_json(silent=True) or {}

    linkedin_url = (data.get("linkedin_url") or "").strip()
    name = (data.get("name") or "").strip()
    if not linkedin_url or not name:
        return jsonify({"error": "linkedin_url and name are required"}), 400
    if "linkedin.com" not in linkedin_url:
        return jsonify({"error": "linkedin_url must be a linkedin.com URL"}), 400

    existing = db.session.query(LinkedInProspect).filter_by(
        account_id=account_id, linkedin_url=linkedin_url
    ).first()
    if existing:
        return jsonify({"error": "prospect already in queue"}), 409

    prospect = LinkedInProspect(
        account_id=account_id,
        name=name,
        company_name=(data.get("company_name") or "").strip() or None,
        job_title=(data.get("job_title") or "").strip() or None,
        industry=(data.get("industry") or "").strip() or None,
        linkedin_url=linkedin_url,
        source="manual",
        status="pending",
        fit_score=data.get("fit_score"),
        notes=(data.get("notes") or "").strip() or None,
    )
    try:
        db.session.add(prospect)
        db.session.commit()
    except Exception:
        db.session.rollback()
        log.exception("Failed to add manual prospect")
        return jsonify({"error": "internal error"}), 500

    draft_messages_task.delay()
    return jsonify({"id": prospect.id, "status": "pending"}), 201


@linkedin_api_bp.route("/prospects", methods=["GET"])
@login_required_settings
def api_list_prospects():
    account_id = g.current_account_id
    status_filter = request.args.get("status")
    query = db.session.query(LinkedInProspect).filter_by(account_id=account_id)
    if status_filter:
        query = query.filter(LinkedInProspect.status == status_filter)
    prospects = query.order_by(LinkedInProspect.created_at.desc()).limit(200).all()
    return jsonify([{
        "id": p.id,
        "name": p.name,
        "company_name": p.company_name,
        "job_title": p.job_title,
        "linkedin_url": p.linkedin_url,
        "status": p.status,
        "fit_score": p.fit_score,
        "source": p.source,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "message_2_due_at": p.message_2_due_at.isoformat() if p.message_2_due_at else None,
        "message_3_due_at": p.message_3_due_at.isoformat() if p.message_3_due_at else None,
    } for p in prospects])


@linkedin_api_bp.route("/icp", methods=["GET"])
@login_required_settings
def api_get_icp():
    from src.models.marketing import ICPConfig
    from src.tasks.linkedin import _ICP_DEFAULTS
    account_id = g.current_account_id
    config = db.session.query(ICPConfig).filter_by(account_id=account_id).first()
    if not config:
        return jsonify(_ICP_DEFAULTS)
    return jsonify({
        "titles": config.titles,
        "industries": config.industries,
        "company_size_min": config.company_size_min,
        "company_size_max": config.company_size_max,
        "geographies": config.geographies,
    })


@linkedin_api_bp.route("/icp", methods=["POST"])
@login_required_settings
def api_save_icp():
    from src.models.marketing import ICPConfig
    account_id = g.current_account_id
    data = request.get_json(silent=True) or {}
    config = db.session.query(ICPConfig).filter_by(account_id=account_id).first()
    if not config:
        config = ICPConfig(account_id=account_id)
        db.session.add(config)
    config.titles = data.get("titles", config.titles)
    config.industries = data.get("industries", config.industries)
    config.company_size_min = int(data.get("company_size_min", config.company_size_min))
    config.company_size_max = int(data.get("company_size_max", config.company_size_max))
    config.geographies = data.get("geographies", config.geographies)
    try:
        db.session.commit()
        return jsonify({"saved": True})
    except Exception:
        db.session.rollback()
        return jsonify({"error": "internal error"}), 500
