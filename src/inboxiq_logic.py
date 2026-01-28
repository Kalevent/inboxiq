"""
InboxIQ triage utilities (copied from legacy app, kept self-contained).
"""
from __future__ import annotations

import hashlib
import json
import re
import os
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from typing import Any, Dict, List
import logging

def _env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.lower() in ("1", "true", "yes", "on")


@dataclass
class TriageDecision:
    category: str
    priority: str
    sentiment: str
    entities: Dict[str, Any]
    confidence: Dict[str, float]
    needs_review: bool = False
    decision_trace: List[str] = field(default_factory=list)
    summary: str | None = None
    last_question: str | None = None
    intent: str | None = None
    risk_flag: bool = False
    owner: str | None = None
    team: str | None = None
    assigned_to: str | None = None
    similar_feedback: List[Dict[str, Any]] = field(default_factory=list)
    action_required: bool | str | None = None  # true | false | "optional"
    ai_reason: str | None = None

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "priority": self.priority,
            "sentiment": self.sentiment,
            "entities": self.entities,
            "confidence": self.confidence,
            "needs_review": self.needs_review,
            "decision_trace": self.decision_trace,
            "summary": self.summary,
            "last_question": self.last_question,
            "intent": self.intent,
            "risk_flag": self.risk_flag,
            "owner": self.owner,
            "team": self.team,
            "assigned_to": self.assigned_to,
            "similar_feedback": self.similar_feedback,
            "action_required": self.action_required,
            "ai_reason": self.ai_reason,
        }


def _extract_last_question(text: str) -> str | None:
    if not text:
        return None
    # Grab the last sentence ending with a question mark.
    parts = re.split(r"(?<=[?])\s+", text.strip())
    questions = [p for p in parts if p.strip().endswith("?")]
    return questions[-1].strip() if questions else None


def _normalize_choice(value: str | None, allowed: list[str], default: str) -> str:
    if not value:
        return default
    cleaned = str(value).strip()
    if not cleaned:
        return default
    lowered = cleaned.lower()
    for entry in allowed:
        if lowered == str(entry).lower():
            return str(entry)
    return default


def _normalize_priority(value: str | None, allowed: list[str]) -> str:
    if not value:
        return allowed[2] if len(allowed) > 2 else (allowed[0] if allowed else "P2")
    cleaned = str(value).strip().upper()
    if cleaned in [str(a).upper() for a in allowed]:
        return cleaned
    if cleaned in {"0", "P0", "CRITICAL", "URGENT", "HIGH"}:
        return "P0"
    if cleaned in {"1", "P1"}:
        return "P1"
    if cleaned in {"2", "P2", "MEDIUM"}:
        return "P2"
    if cleaned in {"3", "P3", "LOW"}:
        return "P3"
    return "P2"


def _normalize_action_required(value: object | None) -> bool | str | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    lowered = str(value).strip().lower()
    if lowered in ("true", "yes", "required", "action_required", "action required"):
        return True
    if lowered in ("false", "no", "auto", "informational", "auto_handled", "auto-handled"):
        return False
    if lowered in ("optional", "maybe"):
        return "optional"
    return None


def compute_due_at(priority: str) -> datetime | None:
    """
    Simple SLA mapping to a due_at timestamp.
    P0: +1h, P1: +4h, P2+: +24h.
    """
    now = datetime.now(timezone.utc)
    if priority == "P0":
        return now + timedelta(hours=1)
    if priority == "P1":
        return now + timedelta(hours=4)
    return now + timedelta(hours=24)


def _reason_text(action_required: bool | str, reason: str) -> str:
    if action_required is True:
        return "Action required — customer needs help." if reason == "default_actionable" else f"Action required ({reason.replace('_', ' ')})."
    if action_required == "optional":
        return "Optional follow-up when capacity allows."
    return "Informational / auto-handled."


def normalize_email_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    subject = (data.get("subject") or "").strip()
    from_email = (data.get("from_email") or data.get("from") or "").strip()
    body = (data.get("body") or data.get("text") or data.get("snippet") or "").strip()
    if not subject or not from_email:
        raise ValueError("subject and from_email are required for triage")
    message_id = data.get("message_id") or data.get("id")
    if not message_id:
        digest = hashlib.sha1(f"{from_email}-{subject}-{body}".encode("utf-8")).hexdigest()
        message_id = f"msg-{digest}"
    provider = data.get("provider") or data.get("source") or "unknown"
    source = data.get("source") or data.get("provider") or "unknown"
    provider_thread_url = data.get("provider_thread_url") or data.get("thread_url")
    return {
        "subject": subject,
        "from_email": from_email,
        "body": body,
        "message_id": message_id,
        "provider": provider,
        "source": source,
        "channel": data.get("channel") or source,
        "use_case": data.get("use_case"),
        "context": data.get("context"),
        "provider_thread_url": provider_thread_url,
        "received_at": data.get("received_at"),
    }


def _safe_json(val: Any) -> Dict[str, Any]:
    if not val or not isinstance(val, str):
        return {}
    try:
        return json.loads(val)
    except Exception:
        return {}


def run_dspy_decision(email: Dict[str, Any], account_id: int | None = None) -> TriageDecision:
    normalized = normalize_email_payload(email)
    account_id = account_id or email.get("account_id")

    if not _env_bool("DSPY_ENABLED", True):
        raise RuntimeError("DSPy triage is required. Set DSPY_ENABLED=1 and configure a model.")

    try:
        from src.dspy_triage import run_dspy_triage
        from src.triage_labels import get_triage_labels

        label_config = get_triage_labels(account_id)
        categories = label_config.get("categories", [])
        priorities = label_config.get("priorities", [])
        sentiments = label_config.get("sentiments", [])
        intents = label_config.get("intents", [])

        dspy_context = {"labels": label_config}
        extra_context = email.get("context") or email.get("metadata") or email.get("payload_context")
        if extra_context:
            dspy_context["payload_context"] = extra_context

        dspy_result = run_dspy_triage(normalized, context=dspy_context or None, labels=label_config, account_id=account_id)

        category = _normalize_choice(dspy_result.get("category"), categories, (categories[0] if categories else "general"))
        priority = _normalize_priority(dspy_result.get("priority"), priorities)
        sentiment = _normalize_choice(dspy_result.get("sentiment"), sentiments, (sentiments[0] if sentiments else "neutral"))
        intent = _normalize_choice(dspy_result.get("intent"), intents, (intents[0] if intents else "general"))
        action_required = _normalize_action_required(dspy_result.get("action_required"))
        ai_reason = (dspy_result.get("ai_reason") or "").strip() or None

        team = (dspy_result.get("team") or "").strip() or None
        owner = (dspy_result.get("owner") or "").strip() or None
        assigned_to = (dspy_result.get("assigned_to") or "").strip() or None

        if action_required is None:
            action_required = "optional"
            decision_trace = list(dspy_result.get("decision_trace") or [])
            decision_trace.append("dspy_action_required_missing")
        else:
            decision_trace = list(dspy_result.get("decision_trace") or [])
            if not decision_trace:
                decision_trace = ["dspy"]

        risk_flag = priority == "P0" or sentiment == "negative"
        entities = _safe_json(dspy_result.get("entities_json")) or {}

        confidence = {"category": 0.55, "priority": 0.55, "sentiment": 0.55}
        needs_review = False if action_required is not None else True

        return TriageDecision(
            category=category,
            priority=priority,
            sentiment=sentiment,
            entities=entities,
            confidence=confidence,
            needs_review=needs_review,
            decision_trace=decision_trace,
            summary=(normalized.get("snippet") or normalized.get("body") or "")[:280],
            last_question=_extract_last_question(normalized.get("body") or ""),
            intent=intent,
            risk_flag=risk_flag,
            owner=owner,
            team=team,
            assigned_to=assigned_to,
            similar_feedback=[],
            action_required=action_required,
            ai_reason=ai_reason or _reason_text(action_required, "dspy"),
        )
    except Exception as exc:
        logging.getLogger(__name__).warning("dspy triage failed: %s", exc)
        raise RuntimeError("DSPy triage failed.") from exc

    raise RuntimeError("DSPy triage required and did not complete.")


def sample_messages() -> List[Dict[str, str]]:
    return [
        {
            "subject": "Payment failed for invoice 8831",
            "from_email": "billing@contoso.com",
            "body": "Hi team, our card was charged twice for invoice #8831 yesterday. Please refund the duplicate charge and confirm once resolved. This is urgent.",
            "provider": "demo",
            "message_id": "demo-1",
            "provider_thread_url": "https://mail.example.com/thread/demo-1",
        },
        {
            "subject": "App crash on login",
            "from_email": "maria@example.com",
            "body": "I cannot login to the dashboard. It keeps saying unexpected error and crashes. Happening since this morning. Please fix ASAP.",
            "provider": "demo",
            "message_id": "demo-2",
            "provider_thread_url": "https://mail.example.com/thread/demo-2",
        },
        {
            "subject": "Requesting refund for order ORD-4451",
            "from_email": "support@quickship.com",
            "body": "The last shipment arrived damaged. We need a refund against order ORD-4451. Let me know the steps.",
            "provider": "demo",
            "message_id": "demo-3",
            "provider_thread_url": "https://mail.example.com/thread/demo-3",
        },
        {
            "subject": "How do I add a teammate?",
            "from_email": "founder@startup.io",
            "body": "Quick question: how can I add two more teammates to our workspace? Is it part of our current plan?",
            "provider": "demo",
            "message_id": "demo-4",
            "provider_thread_url": "https://mail.example.com/thread/demo-4",
        },
    ]
