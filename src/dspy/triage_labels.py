"""
Load triage label configuration from the database (optionally account-scoped).
"""
from __future__ import annotations

import json
import os
import logging
from typing import Any, Dict

from src.extensions import db
from src.models import TriageLabelConfig


# Default labels when no configuration exists
DEFAULT_TRIAGE_LABELS: Dict[str, Any] = {
    "priorities": ["P1", "P2", "P3", "P4"],
    "categories": [
        "support",
        "billing",
        "sales",
        "technical",
        "feedback",
        "spam",
        "marketing",
        "auto_reply",
        "other",
    ],
    "sentiments": ["positive", "neutral", "negative", "urgent"],
    "intents": [
        "question",
        "complaint",
        "request",
        "feedback",
        "bug_report",
        "feature_request",
        "general",
        "spam",
        "informational",
    ],
    "email_types": [
        "support_request",
        "sales_inquiry",
        "billing",
        "bug_report",
        "feature_request",
        "marketing",
        "newsletter",
        "spam",
        "transactional",
        "auto_reply",
        "notification",
        "internal",
        "other",
    ],
    "teams": ["support", "engineering", "sales", "billing", "management"],
    "action_required_options": ["true", "false", "optional"],
}


def _load_env_labels() -> Dict[str, Any]:
    raw = os.getenv("TRIAGE_LABELS_JSON")
    if not raw:
        return DEFAULT_TRIAGE_LABELS
    try:
        labels = json.loads(raw)
        # Merge with defaults for any missing keys
        for key, value in DEFAULT_TRIAGE_LABELS.items():
            if key not in labels:
                labels[key] = value
        return labels
    except json.JSONDecodeError:
        return DEFAULT_TRIAGE_LABELS


def get_triage_labels(account_id: int | None) -> Dict[str, Any]:
    try:
        query = TriageLabelConfig.query
        if account_id:
            scoped = (
                query.filter(TriageLabelConfig.account_id == account_id)
                .order_by(TriageLabelConfig.updated_at.desc())
                .first()
            )
            if scoped and scoped.labels:
                return scoped.labels
        global_cfg = (
            query.filter(TriageLabelConfig.account_id.is_(None))
            .order_by(TriageLabelConfig.updated_at.desc())
            .first()
        )
        if global_cfg and global_cfg.labels:
            return global_cfg.labels
    except Exception as exc:
        logging.getLogger(__name__).warning("triage label lookup failed: %s", exc)
    return _load_env_labels()


def save_triage_labels(account_id: int | None, labels: Dict[str, Any], name: str = "default") -> Dict[str, Any]:
    # Validate that all labels are single words (no spaces) to avoid confusion
    for key, values in labels.items():
        if isinstance(values, list):
            for value in values:
                if isinstance(value, str) and " " in value.strip():
                    raise ValueError(
                        f"Label '{value}' in '{key}' contains spaces. "
                        f"Labels must be single words (e.g., 'billing' not 'billing issue'). "
                        f"Use underscores for multi-word labels (e.g., 'bug_report')."
                    )

    cfg = (
        TriageLabelConfig.query.filter(
            TriageLabelConfig.account_id == account_id,
            TriageLabelConfig.name == name,
        )
        .order_by(TriageLabelConfig.updated_at.desc())
        .first()
    )
    if not cfg:
        cfg = TriageLabelConfig(account_id=account_id, name=name, labels=labels)
        db.session.add(cfg)
    else:
        cfg.labels = labels
    db.session.commit()
    return cfg.to_dict()
