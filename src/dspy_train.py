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
from src.dspy_triage import build_triage_module, _format_payload
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


def main() -> None:
    app = create_app()
    with app.app_context():
        limit = int(os.getenv("DSPY_TRAIN_LIMIT", "200"))
        account_id = os.getenv("DSPY_TRAIN_ACCOUNT_ID")
        account_val = int(account_id) if account_id else None
        labels = get_triage_labels(account_val)

        query = Ticket.query.filter(Ticket.manual_override.is_(True))
        if account_val:
            query = query.filter(Ticket.account_id == account_val)
        samples = query.order_by(Ticket.updated_at.desc()).limit(limit).all()
        if not samples:
            print("No manual override samples found.")
            return

        trainset = [_example_from_ticket(t, labels) for t in samples]
        module = build_triage_module(dspy, labels)

        optimizer = BootstrapFewShot(metric=_metric)
        compiled = optimizer.compile(module, trainset=trainset)
        print("BootstrapFewShot compile complete.")

        # Quick sanity check on the first sample
        test = trainset[0]
        pred = compiled(content=test.content)
        print("Sample prediction:", pred)


if __name__ == "__main__":
    main()
