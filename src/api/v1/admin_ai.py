"""Admin AI status endpoints — read-only artifact metadata and training data export."""
import json
import logging
import re
from pathlib import Path

from flask import jsonify, Response
from flask_jwt_extended import jwt_required

from src.api.v1 import v1
from src.api.v1.admin import _require_admin

logger = logging.getLogger(__name__)

_EXAMPLES_PATH = Path(__file__).parents[3] / "dspy_artifacts" / "chat_widget_examples.json"
_HTML_TAG = re.compile(r"<[^>]+>")


@v1.route("/admin/ai/chat-widget-status", methods=["GET"])
@jwt_required()
def admin_chat_widget_status():
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    try:
        from src.dspy.config import _configure_dspy
        from src.dspy.cache import _load_compiled_meta
        from src.models.misc import AriaConversation

        _, model_id, _ = _configure_dspy()
        artifact_key = f"chat_widget_{model_id}"
        meta = _load_compiled_meta(artifact_key, None)

        example_count = 0
        if _EXAMPLES_PATH.exists():
            try:
                example_count = len(json.loads(_EXAMPLES_PATH.read_text()))
            except Exception:
                pass

        conversation_count = AriaConversation.query.count()

        return jsonify({
            "artifact": meta,
            "example_count": example_count,
            "conversation_count": conversation_count,
            "model_id": model_id,
        })
    except Exception as exc:
        logger.error("chat-widget-status failed: %s", exc)
        return jsonify({"error": str(exc)}), 500


@v1.route("/admin/ai/export-training-examples", methods=["GET"])
@jwt_required()
def admin_export_training_examples():
    """Export saved Aria conversations as DSPy training examples JSON.
    Download and review, then drop into dspy_artifacts/chat_widget_examples.json and retrain locally."""
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    try:
        from src.models.misc import AriaConversation

        convs = AriaConversation.query.order_by(AriaConversation.created_at.desc()).all()
        examples = []
        for conv in convs:
            example = _format_as_training_example(conv)
            if example:
                examples.append(example)

        content = json.dumps(examples, indent=2, ensure_ascii=False)
        return Response(
            content,
            mimetype="application/json",
            headers={"Content-Disposition": "attachment; filename=aria_training_examples.json"},
        )
    except Exception as exc:
        logger.error("export-training-examples failed: %s", exc)
        return jsonify({"error": str(exc)}), 500


def _format_as_training_example(conv) -> dict | None:
    """Convert an AriaConversation row into a DSPy training example dict."""
    try:
        messages = json.loads(conv.messages or "[]")
    except Exception:
        return None

    if not messages:
        return None

    # Find the last user→bot exchange: the message that triggered the intent
    last_user_idx = None
    last_bot_idx = None
    for i in range(len(messages) - 1, -1, -1):
        if last_bot_idx is None and messages[i].get("role") == "bot":
            last_bot_idx = i
        elif last_bot_idx is not None and messages[i].get("role") == "user":
            last_user_idx = i
            break

    if last_user_idx is None or last_bot_idx is None:
        return None

    message = messages[last_user_idx].get("text", "").strip()
    reply_raw = messages[last_bot_idx].get("text", "").strip()
    reply = _HTML_TAG.sub("", reply_raw)  # strip HTML from bot replies
    history = messages[:last_user_idx]

    if not message or not reply:
        return None

    return {
        "account_name": "InboxIQ",
        "visitor_name": conv.visitor_name or "",
        "branch": conv.branch or "demo",
        "conversation_history": json.dumps(history),
        "message": message,
        "knowledge_base": "",
        "reply": reply,
        "intent": conv.intent,
    }
