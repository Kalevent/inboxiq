"""
Lightweight DSPy evaluation harness for InboxIQ triage.
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, Iterable

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.app import create_app
from src.models.tickets import Ticket
from src.dspy import run_dspy_triage
from src.dspy.triage_labels import get_triage_labels


def _label_from_ticket(ticket: Ticket) -> Dict[str, Any]:
    decision = ticket.decision or {}
    return {
        "category": ticket.category,
        "priority": ticket.priority,
        "sentiment": ticket.sentiment,
        "intent": decision.get("intent") or "general",
        "action_required": decision.get("action_required"),
    }


def _payload_from_ticket(ticket: Ticket) -> Dict[str, Any]:
    return {
        "subject": ticket.subject,
        "from_email": ticket.from_email,
        "body": ticket.body_preview or "",
        "provider": ticket.provider or "unknown",
        "message_id": ticket.message_id,
    }


def _accuracy(pairs: Iterable[tuple[Any, Any]]) -> float:
    total = 0
    ok = 0
    for expected, actual in pairs:
        if expected is None:
            continue
        total += 1
        if expected == actual:
            ok += 1
    return (ok / total) if total else 0.0


def evaluate(limit: int = 200, account_id: int | None = None) -> Dict[str, float]:
    query = Ticket.query
    if account_id:
        query = query.filter(Ticket.account_id == account_id)
    samples = (
        query.filter(Ticket.manual_override.is_(True))
        .order_by(Ticket.updated_at.desc())
        .limit(limit)
        .all()
    )

    expected = []
    predicted = []
    labels = get_triage_labels(account_id)
    for ticket in samples:
        expected.append(_label_from_ticket(ticket))
        predicted.append(run_dspy_triage(_payload_from_ticket(ticket), labels=labels))

    metrics = {
        "category_acc": _accuracy((e["category"], p.get("category")) for e, p in zip(expected, predicted)),
        "priority_acc": _accuracy((e["priority"], p.get("priority")) for e, p in zip(expected, predicted)),
        "sentiment_acc": _accuracy((e["sentiment"], p.get("sentiment")) for e, p in zip(expected, predicted)),
        "intent_acc": _accuracy((e["intent"], p.get("intent")) for e, p in zip(expected, predicted)),
        "action_required_acc": _accuracy((e["action_required"], p.get("action_required")) for e, p in zip(expected, predicted)),
    }
    return metrics


def main() -> None:
    app = create_app()
    with app.app_context():
        limit = int(os.getenv("DSPY_EVAL_LIMIT", "200"))
        account_id = os.getenv("DSPY_EVAL_ACCOUNT_ID")
        account_val = int(account_id) if account_id else None
        metrics = evaluate(limit=limit, account_id=account_val)
        for key, value in metrics.items():
            print(f"{key}: {value:.2%}")


if __name__ == "__main__":
    main()
