from __future__ import annotations

from flask import jsonify, request
from flask_jwt_extended import jwt_required

# from . import v1
from src.api.v1 import v1
def _safe_json() -> dict:
    try:
        return request.get_json() or {}
    except Exception:
        return {}


@v1.route("/leads/sourcing/run", methods=["POST"])
@jwt_required(optional=True)
def run_lead_sourcing():
    """
    Trigger the autonomous lead sourcing flow (search -> fetch -> extract -> verify/probe -> upsert).
    """
    from src.leads.tasks import sourcing_job

    payload = _safe_json()
    agent_id = payload.get("agent_id")
    queries = payload.get("queries") or []
    max_results = int(payload.get("max_results", 5) or 5)
    send_probe = bool(payload.get("send_probe", False))

    if not agent_id:
        return jsonify({"error": "agent_id is required"}), 400
    if not isinstance(queries, list) or not queries:
        return jsonify({"error": "queries must be a non-empty list of strings"}), 400

    try:
        async_result = sourcing_job.apply_async(args=[agent_id, queries, max_results, send_probe])
    except Exception as exc:
        return jsonify({"error": f"Failed to enqueue sourcing job: {exc}"}), 500

    return jsonify({"task_id": async_result.id, "queued": True})


@v1.route("/leads/tasks/<task_id>", methods=["GET"])
@jwt_required(optional=True)
def get_lead_task_status(task_id: str):
    """
    Return Celery task status/result for lead sourcing/sync tasks.
    """
    try:
        from src.celery_inboxiq import celery
        from celery.result import AsyncResult
    except Exception as exc:
        return jsonify({"error": f"Unable to load Celery backend: {exc}"}), 500

    res = AsyncResult(task_id, app=celery)
    payload = {"task_id": task_id, "state": res.state}
    if res.successful():
        payload["result"] = res.result
    elif res.failed():
        payload["error"] = str(res.result)
    return jsonify(payload)
