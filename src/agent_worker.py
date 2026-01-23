"""
Utility worker to orchestrate intake -> (enrich) -> triage agents for InboxIQ.

This is a minimal helper and does not auto-run; call process_email_with_agents
from your worker/cron after wiring agent IDs and BASE_URL env vars.
"""
from __future__ import annotations

import os
import json
from typing import Any, Dict, Optional

import requests


def _invoke_agent(agent_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Invoke agents against the InboxIQ API.
    Always honor INBOXIQ_API_BASE_URL or API_BASE_URL; never fall back to localhost in production.
    """
    base_url = (
        os.getenv("INBOXIQ_API_BASE_URL")
        or os.getenv("API_BASE_URL")
        or "http://localhost:8000"
    )
    # InboxIQ API is served under /api/v1 in this codebase.
    url = f"{base_url.rstrip('/')}/api/v1/agents/{agent_id}/invoke"
    resp = requests.post(url, json=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()


def process_email_with_agents(raw_email: Dict[str, Any]) -> Dict[str, Any]:
    """
    Orchestrate intake -> optional enrichment -> triage. Returns a dict with details.
    Expects agent IDs in env:
      INTAKE_AGENT_ID, TRIAGE_AGENT_ID (required)
      ENRICH_AGENT_ID (optional)
    """
    intake_id = os.getenv("INTAKE_AGENT_ID")
    triage_id = os.getenv("TRIAGE_AGENT_ID")
    enrich_id = os.getenv("ENRICH_AGENT_ID")  # optional
    if not intake_id or not triage_id:
        raise RuntimeError("INTAKE_AGENT_ID and TRIAGE_AGENT_ID env vars must be set")

    result: Dict[str, Any] = {"raw": raw_email}

    # Intake (LLM)
    intake_payload = {"input": json.dumps(raw_email), "use_llm": True}
    intake_resp = _invoke_agent(intake_id, intake_payload)
    normalized = intake_resp.get("result") or intake_resp.get("llm_result") or {}
    result["intake"] = intake_resp
    result["normalized"] = normalized

    # Enrichment (optional)
    enriched: Dict[str, Any] = normalized
    if enrich_id:
        try:
            enrich_payload = {"input": json.dumps(normalized), "use_llm": True}
            enrich_resp = _invoke_agent(enrich_id, enrich_payload)
            enriched = {**normalized, "context": enrich_resp.get("result") or enrich_resp.get("llm_result")}
            result["enrich"] = enrich_resp
            result["enriched"] = enriched
        except Exception as exc:
            result["enrich_error"] = str(exc)
            enriched = normalized

    # Triage (LLM)
    triage_payload = {"input": json.dumps(enriched), "use_llm": True}
    triage_resp = _invoke_agent(triage_id, triage_payload)
    decision = triage_resp.get("result") or triage_resp.get("llm_result") or {}
    result["triage"] = triage_resp
    result["decision"] = decision

    return result
