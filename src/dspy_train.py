"""
DSPy training/optimization using BootstrapFewShot on manual overrides.
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import dspy
from dspy.teleprompt import BootstrapFewShot

from src.app import create_app
from src.models import Ticket
from src.dspy_triage import build_triage_module, _format_payload, _configure_dspy, _save_compiled_module
from src.triage_labels import get_triage_labels


def _action_required_str(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "optional"
    return str(value).lower()


def _example_from_ticket(ticket: Ticket, labels: Dict[str, Any]) -> dspy.Example:
    decision = ticket.decision or {}
    intents = labels.get("intents") or []
    default_intent = intents[0] if intents else "general"
    payload = {
        "subject": ticket.subject,
        "from_email": ticket.from_email,
        "body": ticket.body_preview or "",
        "provider": ticket.provider or "unknown",
        "message_id": ticket.message_id,
    }
    content = _format_payload(payload, context=None)
    return dspy.Example(
        content=content,
        category=ticket.category,
        priority=ticket.priority,
        sentiment=ticket.sentiment,
        intent=decision.get("intent") or default_intent,
        action_required=_action_required_str(decision.get("action_required")),
        ai_reason=decision.get("ai_reason") or "",
        team=decision.get("team") or "",
        assigned_to=decision.get("assigned_to") or "",
        owner=decision.get("owner") or "",
    )


def _metric(gold: dspy.Example, pred: dspy.Example) -> bool:
    return (
        gold.category == pred.category
        and gold.priority == pred.priority
        and gold.sentiment == pred.sentiment
        and gold.intent == pred.intent
        and gold.action_required == pred.action_required
    )


def train_from_overrides(
    account_id: int | None,
    labels: Dict[str, Any],
    dspy_instance: Any,
    model_id: str,
    limit: int,
    min_samples: int,
) -> Dict[str, Any]:
    query = Ticket.query.filter(Ticket.manual_override.is_(True))
    if account_id is not None:
        query = query.filter(Ticket.account_id == account_id)
    samples = query.order_by(Ticket.updated_at.desc()).limit(limit).all()
    if len(samples) < min_samples:
        return {"status": "skipped", "reason": "insufficient_samples", "count": len(samples)}

    trainset = [_example_from_ticket(t, labels) for t in samples]
    module = build_triage_module(dspy_instance, labels)

    optimizer = BootstrapFewShot(metric=_metric)
    compiled = optimizer.compile(module, trainset=trainset)

    artifact_path = _save_compiled_module(dspy_instance, compiled, model_id, account_id)
    return {"status": "compiled", "count": len(samples), "artifact_path": artifact_path}


def main() -> None:
    _, model_id, dspy_instance = _configure_dspy()
    app = create_app()
    with app.app_context():
        limit = int(os.getenv("DSPY_TRAIN_LIMIT", "200"))
        min_samples = int(os.getenv("DSPY_TRAIN_MIN_SAMPLES", "20"))
        account_id = os.getenv("DSPY_TRAIN_ACCOUNT_ID")
        account_val = int(account_id) if account_id else None
        labels = get_triage_labels(account_val)

        result = train_from_overrides(
            account_id=account_val,
            labels=labels,
            dspy_instance=dspy_instance,
            model_id=model_id,
            limit=limit,
            min_samples=min_samples,
        )
        if result["status"] != "compiled":
            print(f"Skipping compile: {result}")
            return

        print("BootstrapFewShot compile complete.")
        print(f"Saved compiled module: {result['artifact_path']}")


if __name__ == "__main__":
    main()
