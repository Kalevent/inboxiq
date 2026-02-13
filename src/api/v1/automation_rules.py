"""
Automation Studio - Rules Management API

Endpoints for creating, managing, and monitoring automation rules.
"""

from flask import request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from src.api.v1 import v1
from src.models import AutomationRule, AutomationRuleExecution, db
from src.automation.nl_parser import parse_natural_language_rule, validate_workflow_structure
from src.automation.roi_calculator import calculate_rule_roi, calculate_account_roi
from uuid import uuid4


@v1.route("/automation/rules", methods=["GET"])
@jwt_required()
def list_rules():
    """
    List all automation rules for current account.

    Query params:
        - enabled: Filter by enabled status (true/false)
        - source: Filter by source (ai_suggested, user_created, template)
        - limit: Max results (default: 100)
        - offset: Pagination offset (default: 0)

    Returns:
        {
            "rules": [...],
            "total": 50,
            "limit": 100,
            "offset": 0
        }
    """
    account_id = get_jwt_identity()

    # Build query
    query = AutomationRule.query.filter_by(account_id=account_id)

    # Filters
    enabled = request.args.get("enabled")
    if enabled is not None:
        query = query.filter_by(enabled=enabled.lower() == "true")

    source = request.args.get("source")
    if source:
        query = query.filter_by(source=source)

    # Pagination
    limit = min(int(request.args.get("limit", 100)), 1000)
    offset = int(request.args.get("offset", 0))

    total = query.count()
    rules = query.order_by(AutomationRule.created_at.desc()).limit(limit).offset(offset).all()

    return jsonify({
        "rules": [rule.to_dict() for rule in rules],
        "total": total,
        "limit": limit,
        "offset": offset
    }), 200


@v1.route("/automation/rules", methods=["POST"])
@jwt_required()
def create_rule():
    """
    Create a new automation rule.

    Body:
        {
            "name": "Route billing tickets",
            "trigger": {"event": "ticket.created", "object": "ticket"},
            "conditions": [...],
            "condition_logic": "AND",
            "actions": [...]
        }

    Returns:
        {
            "id": "rule-123",
            "name": "...",
            ...
        }
    """
    account_id = get_jwt_identity()
    data = request.get_json()

    # Validate required fields
    required = ["name", "trigger", "actions"]
    for field in required:
        if field not in data:
            return jsonify({"error": f"Missing required field: {field}"}), 400

    # Validate workflow structure
    try:
        workflow_json = {
            "name": data["name"],
            "trigger": data["trigger"],
            "conditions": data.get("conditions", []),
            "condition_logic": data.get("condition_logic", "AND"),
            "actions": data["actions"],
        }
        validated = validate_workflow_structure(workflow_json, {"account_id": account_id})
    except ValueError as e:
        return jsonify({"error": f"Invalid workflow: {str(e)}"}), 400

    # Create rule
    rule = AutomationRule(
        id=str(uuid4()),
        account_id=account_id,
        name=validated["name"],
        description=data.get("description"),
        trigger=validated["trigger"],
        conditions=validated["conditions"],
        condition_logic=validated["condition_logic"],
        actions=validated["actions"],
        enabled=data.get("enabled", True),
        stop_on_error=data.get("stop_on_error", False),
        source=data.get("source", "user_created"),
    )

    db.session.add(rule)
    db.session.commit()

    return jsonify(rule.to_dict()), 201


@v1.route("/automation/rules/from-natural-language", methods=["POST"])
@jwt_required()
def create_rule_from_nl():
    """
    Create automation rule from natural language description.

    Body:
        {
            "description": "Send refund requests over $500 to billing team"
        }

    Returns:
        {
            "id": "rule-123",
            "name": "...",
            ...
        }
    """
    account_id = get_jwt_identity()
    data = request.get_json()

    if "description" not in data:
        return jsonify({"error": "Missing 'description' field"}), 400

    nl_description = data["description"]

    try:
        # Parse natural language to workflow JSON
        workflow_json = parse_natural_language_rule(nl_description, account_id)

        # Create rule
        rule = AutomationRule(
            id=str(uuid4()),
            account_id=account_id,
            name=workflow_json["name"],
            description=nl_description,
            trigger=workflow_json["trigger"],
            conditions=workflow_json["conditions"],
            condition_logic=workflow_json["condition_logic"],
            actions=workflow_json["actions"],
            enabled=data.get("enabled", True),
            source="user_created",
        )

        db.session.add(rule)
        db.session.commit()

        return jsonify(rule.to_dict()), 201

    except Exception as e:
        return jsonify({"error": f"Failed to parse rule: {str(e)}"}), 400


@v1.route("/automation/rules/<rule_id>", methods=["GET"])
@jwt_required()
def get_rule(rule_id):
    """Get a single automation rule by ID."""
    account_id = get_jwt_identity()

    rule = AutomationRule.query.filter_by(id=rule_id, account_id=account_id).first()
    if not rule:
        return jsonify({"error": "Rule not found"}), 404

    return jsonify(rule.to_dict()), 200


@v1.route("/automation/rules/<rule_id>", methods=["PATCH"])
@jwt_required()
def update_rule(rule_id):
    """
    Update an automation rule.

    Body:
        {
            "name": "New name",
            "enabled": false,
            "conditions": [...],
            "actions": [...]
        }
    """
    account_id = get_jwt_identity()
    data = request.get_json()

    rule = AutomationRule.query.filter_by(id=rule_id, account_id=account_id).first()
    if not rule:
        return jsonify({"error": "Rule not found"}), 404

    # Update fields
    if "name" in data:
        rule.name = data["name"]
    if "description" in data:
        rule.description = data["description"]
    if "enabled" in data:
        rule.enabled = data["enabled"]
    if "conditions" in data:
        rule.conditions = data["conditions"]
    if "condition_logic" in data:
        rule.condition_logic = data["condition_logic"]
    if "actions" in data:
        rule.actions = data["actions"]
    if "stop_on_error" in data:
        rule.stop_on_error = data["stop_on_error"]

    db.session.commit()

    return jsonify(rule.to_dict()), 200


@v1.route("/automation/rules/<rule_id>", methods=["DELETE"])
@jwt_required()
def delete_rule(rule_id):
    """Delete an automation rule."""
    account_id = get_jwt_identity()

    rule = AutomationRule.query.filter_by(id=rule_id, account_id=account_id).first()
    if not rule:
        return jsonify({"error": "Rule not found"}), 404

    db.session.delete(rule)
    db.session.commit()

    return jsonify({"message": "Rule deleted"}), 200


@v1.route("/automation/rules/<rule_id>/analytics", methods=["GET"])
@jwt_required()
def get_rule_analytics(rule_id):
    """
    Get ROI analytics for a specific rule.

    Query params:
        - time_period: week, month, quarter, year, all_time (default: month)

    Returns:
        {
            "rule_id": "...",
            "rule_name": "...",
            "time_saved": {...},
            "cost_saved": {...},
            "accuracy": {...},
            "executions": {...}
        }
    """
    account_id = get_jwt_identity()

    rule = AutomationRule.query.filter_by(id=rule_id, account_id=account_id).first()
    if not rule:
        return jsonify({"error": "Rule not found"}), 404

    time_period = request.args.get("time_period", "month")

    try:
        roi_data = calculate_rule_roi(rule_id, time_period)
        return jsonify(roi_data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@v1.route("/automation/analytics", methods=["GET"])
@jwt_required()
def get_account_analytics():
    """
    Get aggregate ROI analytics for all rules in account.

    Query params:
        - time_period: week, month, quarter, year, all_time (default: month)

    Returns:
        {
            "total_time_saved": {...},
            "total_cost_saved": {...},
            "overall_accuracy": {...},
            "total_executions": 500,
            "active_rules": 12,
            "rules_breakdown": [...]
        }
    """
    account_id = get_jwt_identity()
    time_period = request.args.get("time_period", "month")

    try:
        roi_data = calculate_account_roi(account_id, time_period)
        return jsonify(roi_data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@v1.route("/automation/rules/<rule_id>/executions", methods=["GET"])
@jwt_required()
def get_rule_executions(rule_id):
    """
    Get execution history for a rule.

    Query params:
        - limit: Max results (default: 50)
        - offset: Pagination offset (default: 0)
        - success: Filter by success status (true/false)

    Returns:
        {
            "executions": [...],
            "total": 150,
            "limit": 50,
            "offset": 0
        }
    """
    account_id = get_jwt_identity()

    # Verify rule belongs to account
    rule = AutomationRule.query.filter_by(id=rule_id, account_id=account_id).first()
    if not rule:
        return jsonify({"error": "Rule not found"}), 404

    # Build query
    query = AutomationRuleExecution.query.filter_by(rule_id=rule_id)

    # Filter by success
    success = request.args.get("success")
    if success is not None:
        query = query.filter_by(success=success.lower() == "true")

    # Pagination
    limit = min(int(request.args.get("limit", 50)), 1000)
    offset = int(request.args.get("offset", 0))

    total = query.count()
    executions = query.order_by(AutomationRuleExecution.created_at.desc()).limit(limit).offset(offset).all()

    return jsonify({
        "executions": [exec.to_dict() for exec in executions],
        "total": total,
        "limit": limit,
        "offset": offset
    }), 200
