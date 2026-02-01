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
from src.dspy import build_triage_module, _format_payload, _configure_dspy, _save_compiled_module, _load_compiled_meta
from src.extensions import db
from src.models import DspyTrainingMetric
from src.triage_labels import get_triage_labels


# Seed examples for non-actionable emails to teach the model what to auto-handle
SEED_NON_ACTIONABLE_EXAMPLES = [
    # Spam examples
    {
        "subject": "You've won a $1000 gift card!",
        "body": "Congratulations! You've been selected to receive a $1000 gift card. Click here to claim your prize immediately! This offer expires in 24 hours.",
        "from_email": "prizes@win-now-free.com",
        "category": "spam",
        "priority": "P4",
        "sentiment": "neutral",
        "intent": "spam",
        "action_required": "false",
        "email_type": "spam",
        "ai_reason": "Auto-handled: spam email",
    },
    {
        "subject": "URGENT: Act now to claim your inheritance",
        "body": "Dear beneficiary, you have been named in a will. Please provide your bank details to receive $5,000,000.",
        "from_email": "lawyer@inheritance-claim.net",
        "category": "spam",
        "priority": "P4",
        "sentiment": "neutral",
        "intent": "spam",
        "action_required": "false",
        "email_type": "spam",
        "ai_reason": "Auto-handled: spam email",
    },
    # Marketing/Newsletter examples
    {
        "subject": "Your weekly newsletter from TechNews",
        "body": "This week's top stories in tech. View in browser. To unsubscribe, click here. Update your email preferences.",
        "from_email": "newsletter@technews.com",
        "category": "marketing",
        "priority": "P4",
        "sentiment": "neutral",
        "intent": "informational",
        "action_required": "false",
        "email_type": "newsletter",
        "ai_reason": "Auto-handled: newsletter email",
    },
    {
        "subject": "50% off - Limited time offer!",
        "body": "Don't miss our biggest sale of the year! Shop now and save. Unsubscribe from promotional emails.",
        "from_email": "marketing@store.com",
        "category": "marketing",
        "priority": "P4",
        "sentiment": "neutral",
        "intent": "promotional",
        "action_required": "false",
        "email_type": "marketing",
        "ai_reason": "Auto-handled: marketing email",
    },
    {
        "subject": "Monthly product update - January 2025",
        "body": "Here's what's new this month. New features, bug fixes, and improvements. View in browser. Manage preferences.",
        "from_email": "updates@saasproduct.io",
        "category": "marketing",
        "priority": "P4",
        "sentiment": "neutral",
        "intent": "informational",
        "action_required": "false",
        "email_type": "newsletter",
        "ai_reason": "Auto-handled: product newsletter",
    },
    # Auto-reply examples
    {
        "subject": "Out of Office: John Smith",
        "body": "I am currently out of the office until Monday, January 20th. For urgent matters, please contact jane@company.com.",
        "from_email": "john.smith@company.com",
        "category": "auto_reply",
        "priority": "P4",
        "sentiment": "neutral",
        "intent": "auto_reply",
        "action_required": "false",
        "email_type": "auto_reply",
        "ai_reason": "Auto-handled: out of office auto-reply",
    },
    {
        "subject": "Automatic Reply: Your message has been received",
        "body": "Thank you for your email. This is an automatic response to confirm we received your message. A team member will respond within 24 hours.",
        "from_email": "support@company.com",
        "category": "auto_reply",
        "priority": "P4",
        "sentiment": "neutral",
        "intent": "auto_reply",
        "action_required": "false",
        "email_type": "auto_reply",
        "ai_reason": "Auto-handled: automatic reply",
    },
    # Transactional examples
    {
        "subject": "Your order has shipped - Order #12345",
        "body": "Good news! Your order has shipped. Track your package here. This is an automated message, please do not reply.",
        "from_email": "noreply@shipping.com",
        "category": "transactional",
        "priority": "P3",
        "sentiment": "neutral",
        "intent": "notification",
        "action_required": "false",
        "email_type": "transactional",
        "ai_reason": "Auto-handled: shipping notification",
    },
    {
        "subject": "Payment receipt for invoice INV-2025-001",
        "body": "This confirms your payment of $99.00 has been processed. Thank you for your business. This is an automated receipt.",
        "from_email": "billing@service.com",
        "category": "transactional",
        "priority": "P3",
        "sentiment": "positive",
        "intent": "confirmation",
        "action_required": "false",
        "email_type": "transactional",
        "ai_reason": "Auto-handled: payment confirmation",
    },
    # Actionable support examples (for contrast)
    {
        "subject": "Cannot login to my account",
        "body": "Hi, I've been trying to login for the past hour but keep getting an error. I need to access my account urgently for a deadline. Please help!",
        "from_email": "user@customer.com",
        "category": "support",
        "priority": "P1",
        "sentiment": "negative",
        "intent": "bug_report",
        "action_required": "true",
        "email_type": "support_request",
        "ai_reason": "Action required: customer blocked from accessing account",
    },
    {
        "subject": "Request for refund - Order #98765",
        "body": "I received the wrong item and would like a refund. The order was placed last week. Please process this as soon as possible.",
        "from_email": "customer@email.com",
        "category": "billing",
        "priority": "P1",
        "sentiment": "negative",
        "intent": "refund_request",
        "action_required": "true",
        "email_type": "support_request",
        "ai_reason": "Action required: refund request from customer",
    },
]


def _env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.lower() in ("1", "true", "yes", "on")


def _seed_examples_to_dspy(labels: Dict[str, Any]) -> list:
    """Convert seed examples to DSPy Example objects for training."""
    examples = []
    for seed in SEED_NON_ACTIONABLE_EXAMPLES:
        payload = {
            "subject": seed["subject"],
            "body": seed["body"],
            "from_email": seed["from_email"],
            "provider": "seed",
        }
        content = _format_payload(payload, context=None)
        examples.append(dspy.Example(
            content=content,
            category=seed["category"],
            priority=seed["priority"],
            sentiment=seed["sentiment"],
            intent=seed.get("intent", "general"),
            action_required=seed["action_required"],
            ai_reason=seed.get("ai_reason", ""),
            team="",
            assigned_to="",
            owner="",
        ).with_inputs("content"))
    return examples


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
    ).with_inputs("content")


def _normalize_priority(value: Any) -> str:
    """
    Normalize priority value to comparable format.

    Handles multiple formats:
    - P0, P1, P2, P3, P4 -> p0, p1, p2, p3, p4
    - Low, Medium, High, Urgent, Critical -> mapped to p-levels
    - 1, 2, 3, 4 -> p1, p2, p3, p4
    """
    if value is None:
        return "p3"  # Default to medium

    val = str(value).strip().lower()

    # Direct P-level format
    if val in ("p1", "p0", "urgent", "critical", "1"):
        return "p1"
    if val in ("p2", "high", "2"):
        return "p2"
    if val in ("p3", "medium", "normal", "3"):
        return "p3"
    if val in ("p4", "low", "4"):
        return "p4"

    # Fallback: try to extract number
    for c in val:
        if c.isdigit():
            digit = int(c)
            if 1 <= digit <= 4:
                return f"p{digit}"
            if digit == 0:
                return "p1"  # P0 = urgent

    return "p3"  # Default


def _normalize_action(value: Any) -> str:
    """Normalize action_required to true/false/optional."""
    if value is None:
        return "optional"

    val = str(value).strip().lower()

    if val in ("true", "yes", "1", "required"):
        return "true"
    if val in ("false", "no", "0", "none"):
        return "false"
    if val in ("optional", "maybe", "needs_review"):
        return "optional"

    return "optional"


def _metric(gold: dspy.Example, pred: dspy.Example, trace=None) -> bool:
    """
    Metric function for DSPy BootstrapFewShot.

    Focuses on the MOST IMPORTANT fields for triage:
    - action_required (critical: determines if human needs to act)
    - priority (important: determines urgency)

    Normalizes values to handle format mismatches (P1 vs High, etc).

    Third arg (trace) is required by DSPy API.
    """
    # Normalize before comparing
    gold_action = _normalize_action(gold.action_required)
    pred_action = _normalize_action(pred.action_required)
    action_match = gold_action == pred_action

    gold_priority = _normalize_priority(gold.priority)
    pred_priority = _normalize_priority(pred.priority)
    priority_match = gold_priority == pred_priority

    # For BootstrapFewShot, we use a focused metric on the most important fields
    # This gives the optimizer more signal to learn from
    return action_match and priority_match


def _detailed_metric(gold: dspy.Example, pred: dspy.Example) -> dict:
    """
    Compute detailed per-field accuracy for reporting.

    Returns dict with per-field match status and overall scores.
    """
    fields = {
        "action_required": _normalize_action(gold.action_required) == _normalize_action(pred.action_required),
        "priority": _normalize_priority(gold.priority) == _normalize_priority(pred.priority),
        "category": str(gold.category).lower() == str(pred.category).lower(),
        "sentiment": str(gold.sentiment).lower() == str(pred.sentiment).lower(),
        "intent": str(gold.intent).lower() == str(pred.intent).lower(),
    }

    # Core accuracy: action_required + priority (weighted more heavily)
    core_correct = fields["action_required"] and fields["priority"]

    # Full accuracy: all fields
    full_correct = all(fields.values())

    # Weighted score: core fields worth more
    weights = {"action_required": 3, "priority": 2, "category": 1, "sentiment": 1, "intent": 1}
    weighted_score = sum(weights[f] * (1 if fields[f] else 0) for f in fields)
    max_score = sum(weights.values())

    return {
        "fields": fields,
        "core_correct": core_correct,
        "full_correct": full_correct,
        "weighted_score": weighted_score / max_score,
    }


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

    # Include seed examples for non-actionable emails to ensure model learns patterns
    include_seeds = _env_bool("DSPY_TRAIN_INCLUDE_SEEDS", True)
    seed_examples = _seed_examples_to_dspy(labels) if include_seeds else []

    # Allow training with seeds even if not enough manual overrides
    total_samples = len(samples) + len(seed_examples)
    if total_samples < min_samples:
        return {"status": "skipped", "reason": "insufficient_samples", "count": len(samples), "seed_count": len(seed_examples)}

    # Convert tickets to examples (these are the "real" examples from manual overrides)
    ticket_examples = [_example_from_ticket(t, labels) for t in samples]
    ticket_ids = [t.id for t in samples]

    # Determine eval set from tickets only (not seeds)
    existing_meta = _load_compiled_meta(model_id, account_id)
    eval_ids = []
    if existing_meta:
        eval_ids = [t_id for t_id in existing_meta.get("eval_ids", []) if t_id in ticket_ids]
    if not eval_ids:
        # Stable 80/20 split based on ticket id hash for repeatable evals
        eval_ids = [t_id for t_id in ticket_ids if hash(str(t_id)) % 5 == 0]

    eval_set = set(eval_ids)

    # Split ticket examples into train/eval
    train_ticket_examples = []
    eval_ticket_examples = []
    for ex, t_id in zip(ticket_examples, ticket_ids):
        if t_id in eval_set:
            eval_ticket_examples.append(ex)
        else:
            train_ticket_examples.append(ex)

    # Training set = seed examples + train ticket examples
    # (Seeds always go to training, never eval)
    train_samples = seed_examples + train_ticket_examples
    eval_samples = eval_ticket_examples

    # Ensure we have at least some training samples
    if not train_samples:
        train_samples = ticket_examples[: max(len(ticket_examples) - 1, 1)]
    if not eval_samples and len(ticket_examples) > 1:
        eval_samples = ticket_examples[-1:]

    module = build_triage_module(dspy_instance, labels)

    optimizer = BootstrapFewShot(metric=_metric)
    compiled = optimizer.compile(module, trainset=train_samples)

    # Compute training accuracy with detailed metrics
    train_predictions = [compiled(content=ex.content) for ex in train_samples]
    train_core_correct = sum(1 for gold, pred in zip(train_samples, train_predictions) if _metric(gold, pred))
    train_accuracy = train_core_correct / len(train_samples)

    # Compute detailed per-field accuracy
    train_detailed = [_detailed_metric(gold, pred) for gold, pred in zip(train_samples, train_predictions)]
    train_field_accuracy = {}
    for field in ["action_required", "priority", "category", "sentiment", "intent"]:
        correct = sum(1 for d in train_detailed if d["fields"][field])
        train_field_accuracy[field] = round(correct / len(train_detailed), 4)
    train_weighted_avg = sum(d["weighted_score"] for d in train_detailed) / len(train_detailed)

    eval_accuracy = None
    eval_field_accuracy = {}
    eval_weighted_avg = None
    if eval_samples:
        eval_predictions = [compiled(content=ex.content) for ex in eval_samples]
        eval_core_correct = sum(1 for gold, pred in zip(eval_samples, eval_predictions) if _metric(gold, pred))
        eval_accuracy = eval_core_correct / len(eval_samples)

        eval_detailed = [_detailed_metric(gold, pred) for gold, pred in zip(eval_samples, eval_predictions)]
        for field in ["action_required", "priority", "category", "sentiment", "intent"]:
            correct = sum(1 for d in eval_detailed if d["fields"][field])
            eval_field_accuracy[field] = round(correct / len(eval_detailed), 4)
        eval_weighted_avg = sum(d["weighted_score"] for d in eval_detailed) / len(eval_detailed)

    extra_meta = {
        "eval_ids": eval_ids,
        "train_accuracy": round(train_accuracy, 4),
        "eval_accuracy": round(eval_accuracy, 4) if eval_accuracy is not None else None,
        "train_weighted": round(train_weighted_avg, 4),
        "eval_weighted": round(eval_weighted_avg, 4) if eval_weighted_avg is not None else None,
        "train_field_accuracy": train_field_accuracy,
        "eval_field_accuracy": eval_field_accuracy,
        "sample_count": len(samples),
        "seed_count": len(seed_examples),
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
        "seed_count": len(seed_examples),
        "artifact_path": artifact_path,
        "train_accuracy": round(train_accuracy, 4),
        "eval_accuracy": round(eval_accuracy, 4) if eval_accuracy is not None else None,
        "train_weighted": round(train_weighted_avg, 4),
        "eval_weighted": round(eval_weighted_avg, 4) if eval_weighted_avg is not None else None,
        "train_field_accuracy": train_field_accuracy,
        "eval_field_accuracy": eval_field_accuracy,
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
