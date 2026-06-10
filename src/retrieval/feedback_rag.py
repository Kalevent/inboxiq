import math
import re
from typing import List, Dict, Any


from src.embeddings import embed_text


def _tokenize(text: str) -> List[str]:
    return [t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(t) > 2]


def _score(query_tokens: List[str], doc_tokens: List[str]) -> float:
    if not query_tokens or not doc_tokens:
        return 0.0
    qs = set(query_tokens)
    ds = set(doc_tokens)
    overlap = len(qs & ds)
    return overlap / float(len(qs) + 1)


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


def _embedding_from_row(row_embedding: Any) -> List[float]:
    # pgvector returns a list-like; JSON fallback returns list already.
    try:
        return list(row_embedding) if row_embedding is not None else []
    except Exception:
        return []


def get_similar_overrides(subject: str, body: str, limit: int = 3) -> List[Dict[str, Any]]:
    """
    Retrieval over manually corrected tickets.
    Prefers embeddings (pgvector/JSON) when available; falls back to lexical overlap.
    """
    try:
        from src.models import Ticket, TicketEmbedding
    except Exception:
        return []

    query_text = f"{subject} {body}"
    query_vec = embed_text(query_text)

    # Try vector similarity first if embeddings are present.
    embeddings = (
        TicketEmbedding.query.join(Ticket, Ticket.id == TicketEmbedding.ticket_id)
        .filter(Ticket.manual_override.is_(True), TicketEmbedding.embedding.isnot(None))
        .order_by(TicketEmbedding.updated_at.desc())
        .limit(400)
        .all()
    )
    vector_scored: List[Dict[str, Any]] = []
    if embeddings:
        for row in embeddings:
            try:
                ticket = Ticket.query.get(row.ticket_id)
            except Exception:
                ticket = None
            if not ticket:
                continue
            emb = _embedding_from_row(row.embedding)
            if not emb or len(emb) != len(query_vec):
                continue
            score = _cosine(query_vec, emb)
            if score <= 0:
                continue
            fb = (ticket.override_metadata or {}).get("feedback") or {}
            vector_scored.append(
                {
                    "ticket_id": ticket.id,
                    "subject": ticket.subject,
                    "category": ticket.category,
                    "priority": ticket.priority,
                    "team": ticket.team,
                    "assigned_to": ticket.assigned_to,
                    "feedback": fb,
                    "score": round(score, 3),
                    "source": "vector",
                }
            )
        vector_scored.sort(key=lambda x: x["score"], reverse=True)
        if vector_scored:
            return vector_scored[:limit]

    # Fallback: lexical overlap
    q_tokens = _tokenize(query_text)
    if not q_tokens:
        return []
    tickets = (
        Ticket.query.filter(Ticket.manual_override.is_(True))
        .order_by(Ticket.updated_at.desc())
        .limit(300)
        .all()
    )
    scored = []
    for t in tickets:
        doc_tokens = _tokenize(f"{t.subject} {t.body_preview}")
        score = _score(q_tokens, doc_tokens)
        if score <= 0:
            continue
        fb = (t.override_metadata or {}).get("feedback") or {}
        scored.append(
            {
                "ticket_id": t.id,
                "subject": t.subject,
                "category": t.category,
                "priority": t.priority,
                "team": t.team,
                "assigned_to": t.assigned_to,
                "feedback": fb,
                "score": round(score, 3),
                "source": "lexical",
            }
        )
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]
