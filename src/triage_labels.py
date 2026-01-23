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


def _load_env_labels() -> Dict[str, Any]:
    raw = os.getenv("TRIAGE_LABELS_JSON")
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


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
