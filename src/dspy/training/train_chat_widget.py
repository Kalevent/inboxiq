"""
DSPy training pipeline for the chat widget reply module.

Run manually once you have real chat data:
    flask train-chat-widget

Or from Python:
    from src.dspy.training.train_chat_widget import train_chat_widget_module
    train_chat_widget_module()

Training examples live in dspy_artifacts/chat_widget_examples.json.
Add new examples there to improve Aria's responses and intent detection.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_EXAMPLES_PATH = Path(__file__).parents[3] / "dspy_artifacts" / "chat_widget_examples.json"


def _load_examples(dspy: Any) -> list:
    if not _EXAMPLES_PATH.exists():
        logger.warning("No chat widget examples file found at %s", _EXAMPLES_PATH)
        return []
    with open(_EXAMPLES_PATH) as f:
        raw = json.load(f)
    examples = []
    for row in raw:
        ex = dspy.Example(
            account_name=row.get("account_name", "InboxIQ"),
            visitor_name=row.get("visitor_name", ""),
            knowledge_base=row.get("knowledge_base", ""),
            branch=row.get("branch", "demo"),
            conversation_history=row.get("conversation_history", "[]"),
            message=row["message"],
            reply=row.get("reply", ""),
            intent=row.get("intent", "none"),
        ).with_inputs("account_name", "visitor_name", "knowledge_base", "branch", "conversation_history", "message")
        examples.append(ex)
    logger.info("Loaded %d chat widget training examples", len(examples))
    return examples


def _metric(example: Any, prediction: Any, trace: Any = None) -> bool:
    valid_intents = {"none", "book_demo", "needs_human"}
    reply = getattr(prediction, "reply", "") or ""
    intent = (getattr(prediction, "intent", "") or "").strip().lower()
    if len(reply.strip()) < 20:
        return False
    if intent not in valid_intents:
        return False
    if getattr(example, "intent", None):
        return intent == example.intent.strip().lower()
    return True


def train_chat_widget_module() -> Any | None:
    """
    Run BootstrapFewShot optimisation on the chat widget reply module.
    Returns the compiled module, or None if training failed.
    """
    try:
        from dspy.teleprompt import BootstrapFewShot
        from src.dspy.config import _configure_dspy
        from src.dspy.signatures import build_chat_widget_reply
        from src.dspy.cache import _save_compiled_module
    except ImportError as exc:
        logger.error("DSPy training dependencies missing: %s", exc)
        return None

    _, model_id, dspy = _configure_dspy()
    examples = _load_examples(dspy)
    if len(examples) < 3:
        logger.warning("Need at least 3 examples to train — got %d. Add more to dspy_artifacts/chat_widget_examples.json", len(examples))
        return None

    # Split: use last 20% as eval set if we have enough examples
    split = max(1, len(examples) * 8 // 10)
    trainset = examples[:split]
    evalset = examples[split:] or examples[:1]

    logger.info("Training chat widget module: %d train, %d eval", len(trainset), len(evalset))

    try:
        base_module = build_chat_widget_reply(dspy)
        optimizer = BootstrapFewShot(metric=_metric, max_bootstrapped_demos=3, max_labeled_demos=4)
        compiled = optimizer.compile(base_module, trainset=trainset)

        artifact_key = f"chat_widget_{model_id}"
        _save_compiled_module(dspy, compiled, artifact_key, None, None)
        logger.info("Chat widget module compiled and saved as '%s'", artifact_key)
        return compiled
    except Exception as exc:
        logger.error("Chat widget training failed: %s", exc, exc_info=True)
        return None
