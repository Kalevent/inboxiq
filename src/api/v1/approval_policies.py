"""
Prior Authorisation — ApprovalPolicy CRUD API.

Policies define which emails are auto-sent directly (bypassing the Gmail/Outlook
draft queue) when the DSPy reply confidence meets the threshold.

All routes are scoped to the authenticated account.
"""
import logging
from uuid import uuid4

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from src.extensions import db
from src.models.automation import ApprovalPolicy

bp = Blueprint("approval_policies", __name__, url_prefix="/api/v1/approval-policies")
_log = logging.getLogger(__name__)

_ALLOWED_FIELDS = {"category", "email_type", "sentiment"}
_ALLOWED_OPERATORS = {"equals", "not_equals", "contains", "not_contains", "in_list"}


def _validate_conditions(conditions) -> str | None:
    """Return an error string or None if valid."""
    if not isinstance(conditions, list):
        return "conditions must be a list"
    for c in conditions:
        if not isinstance(c, dict):
            return "each condition must be an object"
        if c.get("field") not in _ALLOWED_FIELDS:
            return f"condition field must be one of: {', '.join(sorted(_ALLOWED_FIELDS))}"
        if c.get("operator") not in _ALLOWED_OPERATORS:
            return f"condition operator must be one of: {', '.join(sorted(_ALLOWED_OPERATORS))}"
        if "value" not in c:
            return "condition must have a value"
    return None


@bp.route("", methods=["GET"])
@jwt_required()
def list_policies():
    account_id = get_jwt_identity()
    policies = (
        ApprovalPolicy.query
        .filter_by(account_id=account_id)
        .order_by(ApprovalPolicy.created_at.asc())
        .all()
    )
    return jsonify([p.to_dict() for p in policies]), 200


@bp.route("", methods=["POST"])
@jwt_required()
def create_policy():
    account_id = get_jwt_identity()

    # Auto-send approval policies are a Business plan feature
    from src.features import feature_enabled
    if not feature_enabled("audit_log", int(account_id)):
        return jsonify({"error": "Approval policies require the Business plan. Upgrade to enable auto-send workflows."}), 403

    data = request.get_json(silent=True) or {}

    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400

    conditions = data.get("conditions", [])
    err = _validate_conditions(conditions)
    if err:
        return jsonify({"error": err}), 400

    if not conditions:
        return jsonify({"error": "at least one condition is required"}), 400

    condition_logic = (data.get("condition_logic") or "AND").upper()
    if condition_logic not in ("AND", "OR"):
        return jsonify({"error": "condition_logic must be AND or OR"}), 400

    min_confidence = data.get("min_confidence", 0.85)
    try:
        min_confidence = float(min_confidence)
        if not (0.0 < min_confidence <= 1.0):
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"error": "min_confidence must be a float between 0 and 1"}), 400

    policy = ApprovalPolicy(
        id=str(uuid4()),
        account_id=account_id,
        name=name,
        description=(data.get("description") or "").strip() or None,
        conditions=conditions,
        condition_logic=condition_logic,
        min_confidence=min_confidence,
        enabled=bool(data.get("enabled", True)),
    )
    try:
        db.session.add(policy)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        _log.exception("approval_policy create failed: account=%s error=%s", account_id, exc)
        return jsonify({"error": "failed to create policy"}), 500

    return jsonify(policy.to_dict()), 201


@bp.route("/<policy_id>", methods=["GET"])
@jwt_required()
def get_policy(policy_id):
    account_id = get_jwt_identity()
    policy = ApprovalPolicy.query.filter_by(id=policy_id, account_id=account_id).first()
    if not policy:
        return jsonify({"error": "not found"}), 404
    return jsonify(policy.to_dict()), 200


@bp.route("/<policy_id>", methods=["PATCH"])
@jwt_required()
def update_policy(policy_id):
    account_id = get_jwt_identity()
    policy = ApprovalPolicy.query.filter_by(id=policy_id, account_id=account_id).first()
    if not policy:
        return jsonify({"error": "not found"}), 404

    data = request.get_json(silent=True) or {}

    if "name" in data:
        name = (data["name"] or "").strip()
        if not name:
            return jsonify({"error": "name cannot be empty"}), 400
        policy.name = name

    if "description" in data:
        policy.description = (data["description"] or "").strip() or None

    if "conditions" in data:
        err = _validate_conditions(data["conditions"])
        if err:
            return jsonify({"error": err}), 400
        if not data["conditions"]:
            return jsonify({"error": "at least one condition is required"}), 400
        policy.conditions = data["conditions"]

    if "condition_logic" in data:
        logic = (data["condition_logic"] or "").upper()
        if logic not in ("AND", "OR"):
            return jsonify({"error": "condition_logic must be AND or OR"}), 400
        policy.condition_logic = logic

    if "min_confidence" in data:
        try:
            mc = float(data["min_confidence"])
            if not (0.0 < mc <= 1.0):
                raise ValueError
            policy.min_confidence = mc
        except (TypeError, ValueError):
            return jsonify({"error": "min_confidence must be a float between 0 and 1"}), 400

    if "enabled" in data:
        policy.enabled = bool(data["enabled"])

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        _log.exception("approval_policy update failed: id=%s error=%s", policy_id, exc)
        return jsonify({"error": "failed to update policy"}), 500

    return jsonify(policy.to_dict()), 200


@bp.route("/<policy_id>", methods=["DELETE"])
@jwt_required()
def delete_policy(policy_id):
    account_id = get_jwt_identity()
    policy = ApprovalPolicy.query.filter_by(id=policy_id, account_id=account_id).first()
    if not policy:
        return jsonify({"error": "not found"}), 404

    try:
        db.session.delete(policy)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        _log.exception("approval_policy delete failed: id=%s error=%s", policy_id, exc)
        return jsonify({"error": "failed to delete policy"}), 500

    return jsonify({"deleted": True}), 200
