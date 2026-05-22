from flask import request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from src.api.v1 import v1
from src.models.addons import AccountAddOn
from src.extensions import db


@v1.route("/addons/finance", methods=["GET"])
@jwt_required()
def get_finance_addon():
    account_id = int(get_jwt_identity())
    addon = AccountAddOn.query.filter_by(
        account_id=account_id,
        addon_type="finance",
    ).first()
    if not addon:
        return jsonify({
            "addon_type": "finance",
            "status": "inactive",
            "transactions_this_month": 0,
            "config_json": {},
        }), 200
    return jsonify(addon.to_dict()), 200


@v1.route("/addons/finance/activate", methods=["POST"])
@jwt_required()
def activate_finance_addon():
    """
    Activate or reconfigure the Finance add-on.

    Body:
        {
            "mode": "direct_sync" | "csv_export",
            "stripe_provider_id": "<WebhookProvider id>",
            "qb_provider_id": "<WebhookProvider id>",   // required for direct_sync
            "csv_email": "accounting@company.com"        // required for csv_export
        }
    """
    account_id = int(get_jwt_identity())
    data = request.get_json() or {}

    mode = data.get("mode")
    if mode not in ("direct_sync", "csv_export"):
        return jsonify({"error": "mode must be 'direct_sync' or 'csv_export'"}), 400

    stripe_provider_id = data.get("stripe_provider_id")
    if not stripe_provider_id:
        return jsonify({"error": "stripe_provider_id is required"}), 400

    if mode == "direct_sync" and not data.get("qb_provider_id"):
        return jsonify({"error": "qb_provider_id is required for direct_sync mode"}), 400

    if mode == "csv_export" and not data.get("csv_email"):
        return jsonify({"error": "csv_email is required for csv_export mode"}), 400

    config = {
        "mode": mode,
        "stripe_provider_id": stripe_provider_id,
    }
    if mode == "direct_sync":
        config["qb_provider_id"] = data["qb_provider_id"]
    else:
        config["csv_email"] = data["csv_email"]

    addon = AccountAddOn.query.filter_by(
        account_id=account_id,
        addon_type="finance",
    ).first()

    if not addon:
        addon = AccountAddOn(account_id=account_id, addon_type="finance")
        db.session.add(addon)

    addon.status = "active"
    addon.config_json = config

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return jsonify(addon.to_dict()), 200


@v1.route("/addons/finance/deactivate", methods=["POST"])
@jwt_required()
def deactivate_finance_addon():
    account_id = int(get_jwt_identity())
    addon = AccountAddOn.query.filter_by(
        account_id=account_id,
        addon_type="finance",
    ).first()
    if not addon:
        return jsonify({"error": "not_found"}), 404

    addon.status = "inactive"
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return jsonify(addon.to_dict()), 200
