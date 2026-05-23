"""Admin AI status endpoints — read-only artifact metadata."""
import json
import logging
from pathlib import Path

from flask import jsonify
from flask_jwt_extended import jwt_required

from src.api.v1 import v1
from src.api.v1.admin import _require_admin

logger = logging.getLogger(__name__)

_EXAMPLES_PATH = Path(__file__).parents[3] / "dspy_artifacts" / "chat_widget_examples.json"


@v1.route("/admin/ai/chat-widget-status", methods=["GET"])
@jwt_required()
def admin_chat_widget_status():
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    try:
        from src.dspy.config import _configure_dspy
        from src.dspy.cache import _load_compiled_meta

        _, model_id, _ = _configure_dspy()
        artifact_key = f"chat_widget_{model_id}"
        meta = _load_compiled_meta(artifact_key, None)

        example_count = 0
        if _EXAMPLES_PATH.exists():
            try:
                example_count = len(json.loads(_EXAMPLES_PATH.read_text()))
            except Exception:
                pass

        return jsonify({
            "artifact": meta,
            "example_count": example_count,
            "model_id": model_id,
        })
    except Exception as exc:
        logger.error("chat-widget-status failed: %s", exc)
        return jsonify({"error": str(exc)}), 500
