"""
InboxIQ triage utilities (copied from legacy app, kept self-contained).
"""
from __future__ import annotations

import hashlib
import re
import os
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple
import logging

# Keyword heuristics for cheap classification before any heavier model
CATEGORY_KEYWORDS = {
    "billing": ["invoice", "charge", "billing", "payment", "refund", "receipt", "credit card", "upgrade"],
    "bug": ["error", "issue", "bug", "crash", "fail", "broken", "not working", "does not work", "stacktrace"],
    "refund": ["refund", "chargeback", "cancel order", "cancel my order", "return", "money back"],
    "general": ["question", "help", "support", "info", "information", "guidance", "how do i"],
}

# Workload-suppression keywords mapped from the decision brief (auto-handled / FYI).
ACTION_FALSE_KEYWORDS = [
    "delivered",
    "delivery confirmation",
    "delivery has failed",
    "undeliverable",
    "mailer-daemon",
    "mail delivery subsystem",
    "bounce",
    "read receipt",
    "access granted",
    "account created",
    "subscription confirmed",
    "password reset",
    "plan has been updated",
    "system notification",
    "newsletter",
    "product announcement",
    "promotional",
    "sales follow up",
    "sales follow-up",
    "duplicate",
    "following up",
    "resolved",
    "status update",
    "confirmation",
    "receipt",
    "calendar invite",
    "calendar update",
    "meeting invite",
    "ics",
    "out of office",
    "ooo",
    "automatic reply",
    "auto-reply",
    "auto response",
]

# Guardrail triggers that should always be surfaced (decision brief safety rules).
ACTION_TRUE_KEYWORDS = [
    "billing",
    "invoice",
    "payment",
    "refund",
    "chargeback",
    "access",
    "login",
    "outage",
    "cannot login",
    "can't login",
    "error",
    "bug",
    "issue",
]

SENTIMENT_KEYWORDS = {
    "negative": ["angry", "frustrated", "upset", "unhappy", "terrible", "worst", "cancel", "complaint", "disappointed"],
    "positive": ["love", "great", "thanks", "amazing", "appreciate", "happy"],
}

PRIORITY_KEYWORDS = {
    "P0": ["urgent", "asap", "immediately", "outage", "down", "cannot login", "can't login", "critical", "breach"],
    "P1": ["soon", "priority", "important", "please resolve", "follow up"],
}

INTENT_KEYWORDS = {
    "billing": CATEGORY_KEYWORDS["billing"],
    "incident": ["outage", "down", "cannot login", "can't login", "incident", "breach"],
    "bug": CATEGORY_KEYWORDS["bug"],
    "feature": ["feature", "roadmap", "request", "would like", "could you add", "new capability"],
    "how_to": ["how do i", "how to", "guide", "instructions", "walkthrough"],
    "general": CATEGORY_KEYWORDS["general"],
}

VIP_EMAILS = [e.strip().lower() for e in os.getenv("INBOXIQ_VIP_EMAILS", "").split(",") if e.strip()]
PROMO_KEYWORDS = [
    "sale",
    "% off",
    "percent off",
    "discount",
    "deal",
    "offer",
    "promo",
    "promotion",
    "clearance",
    "flash sale",
    "ends tonight",
    "last chance",
    "save up to",
    "save $",
]
PROMO_SENDER_TAGS = [
    "newsletter",
    "mailer",
    "mailchimp",
    "sendgrid",
    "campaign",
    "promo",
    "offers",
    "deals",
    "marketing",
    "noreply",
    "no-reply",
    "bounce",
]
QUESTION_STARTERS = [
    "who",
    "what",
    "when",
    "where",
    "why",
    "how",
    "can you",
    "could you",
    "would you",
    "is it",
    "are you",
    "do you",
    "did you",
    "please",
    "help",
]


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


def _score_keywords(text: str, keywords: List[str]) -> Tuple[int, List[str]]:
    hits = [kw for kw in keywords if kw in text]
    return len(hits), hits


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


def _detect_intent(text: str) -> Tuple[str, List[str]]:
    best = ("general", [])
    for intent, keywords in INTENT_KEYWORDS.items():
        hits = [kw for kw in keywords if kw in text]
        if hits and len(hits) > len(best[1]):
            best = (intent, hits)
    return best


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


def _classify_category(text: str) -> Tuple[str, float, List[str]]:
    best = ("general", 0, [])
    for cat, keywords in CATEGORY_KEYWORDS.items():
        score, hits = _score_keywords(text, keywords)
        if score > best[1]:
            best = (cat, score, hits)
    cat, score, hits = best
    confidence = min(1.0, 0.2 + (score * 0.15))
    return cat, confidence, hits


def _classify_sentiment(text: str) -> Tuple[str, float, List[str]]:
    best = ("neutral", 0, [])
    for sentiment, keywords in SENTIMENT_KEYWORDS.items():
        score, hits = _score_keywords(text, keywords)
        if score > best[1]:
            best = (sentiment, score, hits)
    sentiment, score, hits = best
    confidence = min(1.0, 0.25 + (score * 0.2)) if sentiment != "neutral" else 0.4
    return sentiment, confidence, hits


def _classify_priority(text: str, sentiment: str, category: str) -> Tuple[str, float, List[str]]:
    base_priority = "P1"
    trace_hits: List[str] = []
    for priority, keywords in PRIORITY_KEYWORDS.items():
        score, hits = _score_keywords(text, keywords)
        if score and priority == "P0":
            return "P0", min(1.0, 0.4 + (score * 0.2)), hits
        if score and priority == "P1":
            trace_hits.extend(hits)
            base_priority = "P1"
    if sentiment == "negative" and category in ("billing", "bug", "refund"):
        trace_hits.append("negative_sentiment_escalation")
        return "P0", 0.55, trace_hits
    if category == "general" and sentiment == "neutral" and not trace_hits:
        return "P2", 0.45, trace_hits
    return base_priority, 0.5 if trace_hits else 0.35, trace_hits


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


def _strip_quoted_reply(body: str) -> str:
    """
    Remove common quoted/replied sections to detect emails with no new content.
    """
    if not body:
        return ""
    lines = body.splitlines()
    filtered = []
    for line in lines:
        lower = line.lower().strip()
        if lower.startswith(">"):
            continue
        if lower.startswith("on ") and " wrote:" in lower:
            continue
        if lower.startswith("from:"):
            continue
        if "-----original message-----" in lower:
            continue
        filtered.append(line)
    return "\n".join(filtered).strip()


def _has_meaningful_new_content(body: str) -> bool:
    stripped = _strip_quoted_reply(body)
    # Treat very short residual content as lacking new info.
    return len(stripped) >= 40


def _is_bulk_sender(email: str) -> bool:
    lower = (email or "").lower()
    return any(tag in lower for tag in PROMO_SENDER_TAGS)


def _is_promo_email(subject: str, body: str, from_email: str) -> bool:
    text = f"{subject} {body}".lower()
    hits = [kw for kw in PROMO_KEYWORDS if kw in text]
    if not hits:
        return False
    return _is_bulk_sender(from_email) or "unsubscribe" in text or len(hits) >= 2


def _looks_like_marketing(subject: str, body: str, from_email: str) -> bool:
    text = f"{subject} {body}".lower()
    if _is_promo_email(subject, body, from_email):
        return True
    if _is_bulk_sender(from_email) and any(tag in text for tag in ("unsubscribe", "newsletter", "view in browser", "manage preferences")):
        return True
    return False


def _looks_like_human_question(text: str, from_email: str) -> bool:
    if "?" not in text:
        return False
    if _is_bulk_sender(from_email):
        return False
    parts = re.split(r"(?<=[?])\s+", text.strip())
    questions = [p.strip() for p in parts if p.strip().endswith("?")]
    if not questions:
        return False
    candidate = questions[-1].lower()
    return any(candidate.startswith(starter) for starter in QUESTION_STARTERS)


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


def _decide_action_required(
    text: str,
    sentiment: str,
    intent: str,
    priority: str,
    subject: str | None = None,
    from_email: str | None = None,
    body: str | None = None,
) -> Tuple[bool | str, str]:
    """
    Explicit action_required decision following the InboxIQ decision brief.
    Returns (action_required, reason).
    """
    lowered = text.lower()
    body = body or ""
    from_email = (from_email or "").lower()

    subject = subject or ""
    if _looks_like_marketing(subject, body, from_email):
        return False, "marketing_auto_handled"
    if _looks_like_human_question(lowered, from_email):
        return True, "question_detected"
    if sentiment == "negative":
        return True, "negative_sentiment_guardrail"
    if any(kw in lowered for kw in ACTION_TRUE_KEYWORDS):
        return True, "high_risk_keyword"

    # Structured non-work cases: out-of-office, bounces, calendars, noreply with no ask, no new content.
    if any(kw in lowered for kw in ("out of office", "ooo", "automatic reply", "auto-reply", "auto response")):
        return False, "out_of_office_autoreply"
    if any(kw in lowered for kw in ("delivery has failed", "undeliverable", "mailer-daemon", "delivery failure notice", "mail delivery subsystem")):
        return False, "delivery_failure"
    if any(kw in lowered for kw in ("calendar invite", "calendar update", "meeting invite", "event invitation", "ics")):
        return False, "calendar_invite"
    if from_email and any(tag in from_email for tag in ("noreply", "no-reply", "donotreply")) and "?" not in lowered and sentiment == "neutral":
        return False, "noreply_informational"
    if not _has_meaningful_new_content(body) and "?" not in lowered and sentiment != "negative":
        return False, "no_new_content"

    if any(kw in lowered for kw in ACTION_FALSE_KEYWORDS) and "?" not in lowered:
        return False, "informational_auto_handled"

    if priority == "P2" and sentiment == "neutral" and intent == "general":
        return False, "neutral_low_priority"

    # Ambiguous / low-urgency fallback
    if priority == "P2":
        return "optional", "ambiguous_optional_follow_up"

    return True, "default_actionable"


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
    provider_thread_url = data.get("provider_thread_url") or data.get("thread_url")
    return {
        "subject": subject,
        "from_email": from_email,
        "body": body,
        "message_id": message_id,
        "provider": provider,
        "provider_thread_url": provider_thread_url,
        "received_at": data.get("received_at"),
    }


def triage_email(email: Dict[str, Any], account_id: int | None = None) -> TriageDecision:
    normalized = normalize_email_payload(email)
    account_id = account_id or email.get("account_id")
    text = f"{normalized['subject']}\n{normalized['body']}".lower()
    from_email = normalized.get("from_email", "").lower()

    override_hint = _manual_override_hint(from_email, account_id)
    if override_hint is None and _is_promo_email(normalized["subject"], normalized["body"], from_email):
        category = "general"
        intent = "general"
        priority = "P3"
        sentiment = "neutral"
        team = _assign_team(category)
        owner = _assign_owner(category)
        assigned_to = _assign_owner_name(team)
        decision_trace = ["promo_guardrail"]
        action_required = False
        return TriageDecision(
            category=category,
            priority=priority,
            sentiment=sentiment,
            entities={},
            confidence={"category": 0.6, "priority": 0.6, "sentiment": 0.4},
            needs_review=False,
            decision_trace=decision_trace,
            summary=(normalized.get("snippet") or normalized.get("body") or "")[:280],
            last_question=_extract_last_question(normalized.get("body") or ""),
            intent=intent,
            risk_flag=False,
            owner=owner,
            team=team,
            assigned_to=assigned_to,
            similar_feedback=[],
            action_required=action_required,
            ai_reason=_reason_text(action_required, "promo_guardrail"),
        )

    decision_trace: List[str] = []
    similar_feedback = []
    try:
        from src.retrieval.feedback_rag import get_similar_overrides

        similar_feedback = get_similar_overrides(normalized["subject"], normalized["body"])
        if similar_feedback:
            decision_trace.append(f"similar_feedback:{similar_feedback[0]['score']}")
    except Exception as exc:
        logging.getLogger(__name__).warning("similar feedback lookup failed: %s", exc)

    category, cat_conf, cat_hits = _classify_category(text)
    if cat_hits:
        decision_trace.append(f"category_hits:{','.join(cat_hits)}")
    sentiment, sent_conf, sent_hits = _classify_sentiment(text)
    if sent_hits:
        decision_trace.append(f"sentiment_hits:{','.join(sent_hits)}")
    priority, pri_conf, pri_hits = _classify_priority(text, sentiment, category)
    if pri_hits:
        decision_trace.append(f"priority_hits:{','.join(pri_hits)}")

    entities = _extract_entities(normalized["body"])
    if entities.get("order_ids"):
        decision_trace.append(f"order_ids:{','.join(entities['order_ids'])}")
    if entities.get("customer_ids"):
        decision_trace.append(f"customer_ids:{','.join(entities['customer_ids'])}")

    intent, intent_hits = _detect_intent(text)
    if intent_hits:
        decision_trace.append(f"intent_hits:{','.join(intent_hits)}")

    # VIP detection
    is_vip = any(v in from_email for v in VIP_EMAILS) if VIP_EMAILS else False
    if is_vip:
        decision_trace.append("vip_sender")
        priority = "P0"

    if override_hint:
        category = override_hint.get("category") or category
        intent = override_hint.get("intent") or intent
        priority = override_hint.get("priority") or priority
        sentiment = override_hint.get("sentiment") or sentiment
        decision_trace.append(f"manual_override_hint:{override_hint.get('source')}")

    risk_flag = priority == "P0" or sentiment == "negative" or is_vip
    owner = override_hint.get("owner") if override_hint else None
    team = override_hint.get("team") if override_hint else None
    assigned_to = override_hint.get("assigned_to") if override_hint else None
    if not team:
        team = _assign_team(intent or category)
    if not owner:
        owner = _assign_owner(category)
    if not assigned_to:
        assigned_to = _assign_owner_name(team)

    needs_review = bool(cat_conf < 0.35 or pri_conf < 0.35)
    confidence = {
        "category": round(cat_conf, 2),
        "priority": round(pri_conf, 2),
        "sentiment": round(sent_conf, 2),
    }
    action_required_override = override_hint.get("action_required") if override_hint else None
    action_required, action_reason = _decide_action_required(
        text,
        sentiment,
        intent,
        priority,
        subject=normalized.get("subject"),
        from_email=from_email,
        body=normalized.get("body"),
    )
    if action_required_override is not None:
        action_required = action_required_override
        action_reason = "manual_override_hint"
    decision_trace.append(f"action_required:{action_required}")

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
        ai_reason=_reason_text(action_required, action_reason),
    )


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
