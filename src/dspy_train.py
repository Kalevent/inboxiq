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
import logging
from datetime import datetime, timezone
from dspy.teleprompt import BootstrapFewShot

from src.app import create_app
from src.models import Ticket
from src.dspy_triage import build_triage_module, _format_payload, _configure_dspy, _save_compiled_module, _load_compiled_meta
from src.extensions import db
from src.models import DspyTrainingMetric
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
    ticket_ids = [t.id for t in samples]
    existing_meta = _load_compiled_meta(model_id, account_id)
    eval_ids = []
    if existing_meta:
        eval_ids = [t_id for t_id in existing_meta.get("eval_ids", []) if t_id in ticket_ids]
    if not eval_ids:
        # Stable 80/20 split based on ticket id hash for repeatable evals.
        eval_ids = [t_id for t_id in ticket_ids if hash(str(t_id)) % 5 == 0]
    eval_set = {t_id for t_id in eval_ids}
    eval_samples = [ex for ex, t_id in zip(trainset, ticket_ids) if t_id in eval_set]
    train_samples = [ex for ex, t_id in zip(trainset, ticket_ids) if t_id not in eval_set]
    if not train_samples:
        train_samples = trainset[: max(len(trainset) - 1, 1)]
    if not eval_samples and len(trainset) > 1:
        eval_samples = trainset[-1:]
    module = build_triage_module(dspy_instance, labels)

    optimizer = BootstrapFewShot(metric=_metric)
    compiled = optimizer.compile(module, trainset=train_samples)
    train_predictions = [compiled(content=ex.content) for ex in train_samples]
    train_accuracy = sum(1 for gold, pred in zip(train_samples, train_predictions) if _metric(gold, pred)) / len(train_samples)
    eval_accuracy = None
    if eval_samples:
        eval_predictions = [compiled(content=ex.content) for ex in eval_samples]
        eval_accuracy = sum(1 for gold, pred in zip(eval_samples, eval_predictions) if _metric(gold, pred)) / len(eval_samples)

    extra_meta = {
        "eval_ids": eval_ids,
        "train_accuracy": round(train_accuracy, 4),
        "eval_accuracy": round(eval_accuracy, 4) if eval_accuracy is not None else None,
        "sample_count": len(samples),
        "eval_count": len(eval_samples),
    }
    artifact_path = _save_compiled_module(
        dspy_instance,
        compiled,
        model_id,
        account_id,
        labels=labels,
        extra_meta=extra_meta,
    )
    return {
        "status": "compiled",
        "count": len(samples),
        "artifact_path": artifact_path,
        "train_accuracy": round(train_accuracy, 4),
        "eval_accuracy": round(eval_accuracy, 4) if eval_accuracy is not None else None,
    }


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
        logging.getLogger(__name__).info(
            "DSPy train accuracy: %s eval accuracy: %s compiled_at: %s",
            result.get("train_accuracy"),
            result.get("eval_accuracy"),
            datetime.now(timezone.utc).isoformat(),
        )
        try:
            db.session.add(
                DspyTrainingMetric(
                    account_id=account_val,
                    model_id=model_id,
                    provider=(os.getenv("DSPY_PROVIDER") or "openai").lower(),
                    sample_count=result.get("count") or 0,
                    eval_count=extra_meta.get("eval_count") if "extra_meta" in locals() else None,
                    train_accuracy=result.get("train_accuracy"),
                    eval_accuracy=result.get("eval_accuracy"),
                )
            )
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            logging.getLogger(__name__).warning("Failed to persist DSPy metrics: %s", exc)


if __name__ == "__main__":
    main()
