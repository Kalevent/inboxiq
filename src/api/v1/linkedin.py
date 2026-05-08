"""LinkedIn outreach API endpoints."""
import logging
from datetime import datetime, timedelta, timezone

from flask import Blueprint, g, jsonify, redirect, request
from src.settings import login_required_settings

from src.extensions import db
from src.models.campaigns import LinkedInProspect
from src.models.marketing import ICPExperiment, ICPVariant
from src.marketing.experiment_metrics import compute_experiment_metrics

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


# ── ICP A/B Experiments — read-only ─────────────────────────────────────────

def _serialize_experiment_summary(exp) -> dict:
    return {
        "id": exp.id,
        "name": exp.name,
        "status": exp.status,
        "traffic_split": exp.traffic_split,
        "winner_variant": exp.winner_variant,
        "created_at": exp.created_at.isoformat() if exp.created_at else None,
    }


def _serialize_variant(v) -> dict:
    return {
        "id": v.id,
        "label": v.label,
        "titles": v.titles,
        "industries": v.industries,
        "company_size_min": v.company_size_min,
        "company_size_max": v.company_size_max,
        "geographies": v.geographies,
    }


@linkedin_api_bp.route("/experiments", methods=["GET"])
@login_required_settings
def api_list_experiments():
    account_id = g.current_account_id
    exps = (
        ICPExperiment.query
        .filter_by(account_id=account_id)
        .order_by(ICPExperiment.created_at.desc())
        .all()
    )
    return jsonify({"experiments": [_serialize_experiment_summary(e) for e in exps]})


@linkedin_api_bp.route("/experiments/<exp_id>", methods=["GET"])
@login_required_settings
def api_get_experiment(exp_id: str):
    account_id = g.current_account_id
    exp = ICPExperiment.query.filter_by(id=exp_id, account_id=account_id).first()
    if not exp:
        return jsonify({"error": "not found"}), 404
    variants = ICPVariant.query.filter_by(experiment_id=exp.id).all()
    return jsonify({
        **_serialize_experiment_summary(exp),
        "variants": [_serialize_variant(v) for v in variants],
        "metrics": compute_experiment_metrics(exp),
    })


@linkedin_api_bp.route("/experiments", methods=["POST"])
@login_required_settings
def api_create_experiment():
    account_id = g.current_account_id
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    traffic_split = body.get("traffic_split") or {"A": 50, "B": 50}
    variants = body.get("variants") or []

    if not name:
        return jsonify({"error": "name is required"}), 422
    if len(variants) != 2 or {v.get("label") for v in variants} != {"A", "B"}:
        return jsonify({"error": "must include exactly two variants with labels A and B"}), 422
    if not isinstance(traffic_split, dict) or set(traffic_split.keys()) != {"A", "B"}:
        return jsonify({"error": "traffic_split must have keys A and B"}), 422
    try:
        sa = int(traffic_split["A"]); sb = int(traffic_split["B"])
    except (TypeError, ValueError):
        return jsonify({"error": "traffic_split values must be integers"}), 422
    if sa < 0 or sb < 0 or sa + sb != 100:
        return jsonify({"error": "traffic_split values must be non-negative and sum to 100"}), 422

    if ICPExperiment.query.filter_by(account_id=account_id, status="running").first():
        return jsonify({"error": "another experiment is already running for this account"}), 409

    exp = ICPExperiment(account_id=account_id, name=name, traffic_split=traffic_split, status="running")
    db.session.add(exp)
    db.session.flush()
    for v in variants:
        db.session.add(ICPVariant(
            experiment_id=exp.id,
            label=v["label"],
            titles=v.get("titles") or [],
            industries=v.get("industries") or [],
            geographies=v.get("geographies") or [],
            company_size_min=v.get("company_size_min"),
            company_size_max=v.get("company_size_max"),
        ))
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    fresh_variants = ICPVariant.query.filter_by(experiment_id=exp.id).all()
    return jsonify({
        **_serialize_experiment_summary(exp),
        "variants": [_serialize_variant(v) for v in fresh_variants],
        "metrics": compute_experiment_metrics(exp),
    }), 201


@linkedin_api_bp.route("/experiments/<exp_id>", methods=["PATCH"])
@login_required_settings
def api_patch_experiment(exp_id: str):
    account_id = g.current_account_id
    exp = ICPExperiment.query.filter_by(id=exp_id, account_id=account_id).first()
    if not exp:
        return jsonify({"error": "not found"}), 404

    body = request.get_json(silent=True) or {}
    new_status = body.get("status")
    new_split = body.get("traffic_split")
    new_winner = body.get("winner_variant")

    if new_status is not None:
        if new_status not in ("running", "paused", "completed"):
            return jsonify({"error": "status must be running|paused|completed"}), 422
        if new_status == "running":
            other = ICPExperiment.query.filter(
                ICPExperiment.account_id == account_id,
                ICPExperiment.status == "running",
                ICPExperiment.id != exp.id,
            ).first()
            if other:
                return jsonify({"error": "another experiment is already running for this account"}), 409
        exp.status = new_status

    if new_split is not None:
        if (not isinstance(new_split, dict)
                or set(new_split.keys()) != {"A", "B"}):
            return jsonify({"error": "traffic_split must have keys A and B"}), 422
        try:
            sa = int(new_split["A"]); sb = int(new_split["B"])
        except (TypeError, ValueError):
            return jsonify({"error": "traffic_split values must be integers"}), 422
        if sa < 0 or sb < 0 or sa + sb != 100:
            return jsonify({"error": "traffic_split values must be non-negative and sum to 100"}), 422
        exp.traffic_split = new_split

    if new_winner is not None:
        if exp.status != "completed":
            return jsonify({"error": "winner_variant can only be set when status='completed'"}), 422
        if new_winner not in ("A", "B"):
            return jsonify({"error": "winner_variant must be A or B"}), 422
        exp.winner_variant = new_winner

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    fresh_variants = ICPVariant.query.filter_by(experiment_id=exp.id).all()
    return jsonify({
        **_serialize_experiment_summary(exp),
        "variants": [_serialize_variant(v) for v in fresh_variants],
        "metrics": compute_experiment_metrics(exp),
    })


@linkedin_api_bp.route("/experiments/<exp_id>", methods=["DELETE"])
@login_required_settings
def api_delete_experiment(exp_id: str):
    account_id = g.current_account_id
    exp = ICPExperiment.query.filter_by(id=exp_id, account_id=account_id).first()
    if not exp:
        return jsonify({"error": "not found"}), 404
    db.session.delete(exp)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return ("", 204)
