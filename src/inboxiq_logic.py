"""
InboxIQ triage utilities (copied from legacy app, kept self-contained).
"""
from __future__ import annotations

import hashlib
import re
import os
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from typing import Any, Dict, List
import logging

VIP_EMAILS = [e.strip().lower() for e in os.getenv("INBOXIQ_VIP_EMAILS", "").split(",") if e.strip()]
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


def _extract_entities(text: str) -> Dict[str, Any]:
    entities: Dict[str, Any] = {"order_ids": [], "customer_ids": []}
    order_matches = re.findall(r"(order|invoice|ticket)[\s#:]*([\w-]{3,})", text, flags=re.IGNORECASE)
    customer_matches = re.findall(r"(customer|account)[\s#:]*([A-Z0-9-]{3,})", text, flags=re.IGNORECASE)

    for _, match in order_matches:
        entities["order_ids"].append(match)
    for _, match in customer_matches:
        entities["customer_ids"].append(match)

    entities["order_ids"] = list(dict.fromkeys(entities["order_ids"]))
    entities["customer_ids"] = list(dict.fromkeys(entities["customer_ids"]))
    return entities


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


def _assign_owner(category: str) -> str:
    mapping = {
        "billing": "Billing Team",
        "refund": "Billing Team",
        "bug": "Engineering Triage",
        "incident": "Incident Response",
        "general": "Support",
    }
    return mapping.get(category, "Support")


def _assign_team(category: str) -> str:
    mapping = {
        "billing": "Billing",
        "refund": "Billing",
        "bug": "Engineering",
        "incident": "Incident Response",
        "feature": "Product",
        "how_to": "Support",
        "general": "Support",
    }
    return mapping.get(category, "Support")


def _assign_owner_name(team: str) -> str:
    # Placeholder owner per team; replace with real user/team mapping if available.
    mapping = {
        "Billing": "billing-queue",
        "Engineering": "eng-triage",
        "Incident Response": "incident-queue",
        "Product": "product-queue",
        "Support": "support-queue",
    }
    return mapping.get(team, "support-queue")


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


def _manual_override_hint(from_email: str, account_id: int | None = None) -> Dict[str, Any] | None:
    """Return the latest manual override for an email or its domain."""
    try:
        from src.models import Ticket
    except Exception:
        return None

    if not from_email:
        return None

    def _query():
        q = Ticket.query.filter(Ticket.manual_override.is_(True))
        if account_id:
            q = q.filter(Ticket.account_id == account_id)
        return q

    hint_source = None
    ticket = _query().filter(Ticket.from_email.ilike(from_email)).order_by(Ticket.updated_at.desc()).first()
    if not ticket and "@" in from_email:
        domain = from_email.split("@", 1)[1].lower()
        ticket = (
            _query()
            .filter(Ticket.from_email.ilike(f"%@{domain}"))
            .order_by(Ticket.updated_at.desc())
            .first()
        )
        hint_source = f"domain:{domain}" if ticket else None
    if not ticket:
        return None

    decision = ticket.decision or {}
    return {
        "category": ticket.category,
        "priority": ticket.priority,
        "sentiment": ticket.sentiment or "neutral",
        "intent": decision.get("intent"),
        "action_required": decision.get("action_required"),
        "team": ticket.team or decision.get("team"),
        "assigned_to": ticket.assigned_to or decision.get("assigned_to"),
        "owner": ticket.owner or decision.get("owner"),
        "source": hint_source or "sender",
    }


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
        "provider_thread_url": provider_thread_url,
        "received_at": data.get("received_at"),
    }


def triage_email(email: Dict[str, Any], account_id: int | None = None) -> TriageDecision:
    normalized = normalize_email_payload(email)
    account_id = account_id or email.get("account_id")
    from_email = normalized.get("from_email", "").lower()

    override_hint = _manual_override_hint(from_email, account_id)

    decision_trace: List[str] = []
    similar_feedback = []
    try:
        from src.retrieval.feedback_rag import get_similar_overrides

        similar_feedback = get_similar_overrides(normalized["subject"], normalized["body"])
        if similar_feedback:
            decision_trace.append(f"similar_feedback:{similar_feedback[0]['score']}")
    except Exception as exc:
        logging.getLogger(__name__).warning("similar feedback lookup failed: %s", exc)

    if not _env_bool("DSPY_ENABLED", False):
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
        if similar_feedback:
            dspy_context["similar_feedback"] = similar_feedback[:1]
        extra_context = email.get("context") or email.get("metadata") or email.get("payload_context")
        if extra_context:
            dspy_context["payload_context"] = extra_context

        dspy_result = run_dspy_triage(normalized, context=dspy_context or None, labels=label_config)
        decision_trace.append("dspy")

        category = _normalize_choice(dspy_result.get("category"), categories, (categories[0] if categories else "general"))
        priority = _normalize_priority(dspy_result.get("priority"), priorities)
        sentiment = _normalize_choice(dspy_result.get("sentiment"), sentiments, (sentiments[0] if sentiments else "neutral"))
        intent = _normalize_choice(dspy_result.get("intent"), intents, (intents[0] if intents else "general"))
        action_required = _normalize_action_required(dspy_result.get("action_required"))
        ai_reason = (dspy_result.get("ai_reason") or "").strip() or None

        team = (dspy_result.get("team") or "").strip() or None
        owner = (dspy_result.get("owner") or "").strip() or None
        assigned_to = (dspy_result.get("assigned_to") or "").strip() or None

        if override_hint:
            category = override_hint.get("category") or category
            intent = override_hint.get("intent") or intent
            priority = override_hint.get("priority") or priority
            sentiment = override_hint.get("sentiment") or sentiment
            decision_trace.append(f"manual_override_hint:{override_hint.get('source')}")

        is_vip = any(v in from_email for v in VIP_EMAILS) if VIP_EMAILS else False
        if is_vip:
            decision_trace.append("vip_sender")
            priority = "P0"

        if not team:
            team = _assign_team(intent or category)
        if not owner:
            owner = _assign_owner(category)
        if not assigned_to:
            assigned_to = _assign_owner_name(team)

        action_required_override = override_hint.get("action_required") if override_hint else None
        if action_required_override is not None:
            action_required = action_required_override
            decision_trace.append("manual_override_action_required")

        if action_required is None:
            action_required = "optional"
            decision_trace.append("dspy_action_required_missing")

        risk_flag = priority == "P0" or sentiment == "negative" or is_vip
        entities = _extract_entities(normalized["body"])
        if entities.get("order_ids"):
            decision_trace.append(f"order_ids:{','.join(entities['order_ids'])}")
        if entities.get("customer_ids"):
            decision_trace.append(f"customer_ids:{','.join(entities['customer_ids'])}")

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
            similar_feedback=similar_feedback,
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
