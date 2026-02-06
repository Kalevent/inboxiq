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


@v1.route("/leads/tasks/<task_id>", methods=["GET"])
@jwt_required(optional=True)
def get_lead_task_status(task_id: str):
    """
    Return Celery task status/result for lead sync tasks.
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
