"""
Utility worker to orchestrate intake -> (enrich) -> triage agents for InboxIQ.

DEPRECATION NOTICE:
-------------------
This module is being superseded by the integrated DSPy triage in celery_inboxiq.py
with decision_merger.py. The agent pipeline is now OPTIONAL and will gracefully
skip if INTAKE_AGENT_ID/TRIAGE_AGENT_ID are not configured.

The new flow uses:
- src/dspy_triage.py for LLM-based classification with email_type detection
- src/decision_merger.py for merging agent + DSPy decisions
- src/mcp/server.py for MCP-based classification tools

TODO: Remove this file after confirming the new triage flow works in production.
"""
from __future__ import annotations

import os
import json
import logging
from typing import Any, Dict

import requests

from src.monitoring.observability import get_tracer
from src.monitoring.sanitizer import safe_span_attribute

tracer = get_tracer(__name__)


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

    UPDATED: Agent IDs are now OPTIONAL. If not configured, returns empty result
    and lets the DSPy triage handle classification directly.

    Expects agent IDs in env (all optional now):
      INTAKE_AGENT_ID - Intake agent for normalization
      TRIAGE_AGENT_ID - Triage agent for classification
      ENRICH_AGENT_ID - Enrichment agent (optional)
    """
    with tracer.start_as_current_span("agents.pipeline") as span:
        # Record pipeline configuration
        intake_id = os.getenv("INTAKE_AGENT_ID")
        triage_id = os.getenv("TRIAGE_AGENT_ID")
        enrich_id = os.getenv("ENRICH_AGENT_ID")  # optional

        span.set_attribute("agents.intake_configured", bool(intake_id))
        span.set_attribute("agents.triage_configured", bool(triage_id))
        span.set_attribute("agents.enrich_configured", bool(enrich_id))

        # Record email metadata (sanitized)
        safe_span_attribute(span, "email.provider", raw_email.get("provider"))
        safe_span_attribute(span, "email.subject_length", len(raw_email.get("subject", "")))
        safe_span_attribute(span, "email.body_length", len(raw_email.get("body", "")))

        # CHANGED: Agent pipeline is now optional - skip gracefully if not configured
        if not intake_id or not triage_id:
            logging.getLogger(__name__).debug(
                "Agent pipeline skipped: INTAKE_AGENT_ID=%s TRIAGE_AGENT_ID=%s not fully configured",
                "set" if intake_id else "unset",
                "set" if triage_id else "unset"
            )
            # Record skip reason
            span.set_attribute("agents.skipped", True)
            span.set_attribute("agents.skip_reason", "agent_ids_not_configured")

            # Return empty result - DSPy triage will handle classification
            return {
                "raw": raw_email,
                "skipped": True,
                "reason": "agent_ids_not_configured",
                "decision": {},
            }

        result: Dict[str, Any] = {"raw": raw_email, "skipped": False}
        span.set_attribute("agents.skipped", False)

        try:
            # Intake (LLM)
            with tracer.start_as_current_span("agents.intake") as intake_span:
                safe_span_attribute(intake_span, "agent.id", intake_id)
                intake_payload = {"input": json.dumps(raw_email), "use_llm": True}
                intake_resp = _invoke_agent(intake_id, intake_payload)
                normalized = intake_resp.get("result") or intake_resp.get("llm_result") or {}
                result["intake"] = intake_resp
                result["normalized"] = normalized

                intake_span.set_attribute("agent.success", True)
                intake_span.add_event("intake_completed")

            # Enrichment (optional)
            enriched: Dict[str, Any] = normalized
            if enrich_id:
                try:
                    with tracer.start_as_current_span("agents.enrich") as enrich_span:
                        safe_span_attribute(enrich_span, "agent.id", enrich_id)
                        enrich_payload = {"input": json.dumps(normalized), "use_llm": True}
                        enrich_resp = _invoke_agent(enrich_id, enrich_payload)
                        enriched = {**normalized, "context": enrich_resp.get("result") or enrich_resp.get("llm_result")}
                        result["enrich"] = enrich_resp
                        result["enriched"] = enriched

                        enrich_span.set_attribute("agent.success", True)
                        enrich_span.add_event("enrichment_completed")
                except Exception as exc:
                    result["enrich_error"] = str(exc)
                    enriched = normalized
                    span.set_attribute("agents.enrich_failed", True)
                    span.set_attribute("agents.enrich_error", str(exc)[:200])

            # Triage (LLM)
            with tracer.start_as_current_span("agents.triage") as triage_span:
                safe_span_attribute(triage_span, "agent.id", triage_id)
                triage_payload = {"input": json.dumps(enriched), "use_llm": True}
                triage_resp = _invoke_agent(triage_id, triage_payload)
                decision = triage_resp.get("result") or triage_resp.get("llm_result") or {}
                result["triage"] = triage_resp
                result["decision"] = decision

                # Record decision results (sanitized)
                if decision:
                    safe_span_attribute(triage_span, "decision.category", decision.get("category"))
                    safe_span_attribute(triage_span, "decision.priority", decision.get("priority"))
                    safe_span_attribute(triage_span, "decision.sentiment", decision.get("sentiment"))

                triage_span.set_attribute("agent.success", True)
                triage_span.add_event("triage_completed")

            span.set_attribute("agents.pipeline_success", True)
            span.add_event("pipeline_completed", {
                "has_decision": bool(decision),
            })

        except Exception as exc:
            logging.getLogger(__name__).warning("Agent pipeline failed: %s", exc)
            result["error"] = str(exc)
            result["decision"] = {}

            span.set_attribute("agents.pipeline_success", False)
            span.set_attribute("error", True)
            span.record_exception(exc)

        return result


# -----------------------------------------------------------------------------
# DEPRECATED CODE BELOW - Kept for reference, will be removed in future version
# -----------------------------------------------------------------------------
#
# The original implementation required INTAKE_AGENT_ID and TRIAGE_AGENT_ID to be
# set, which caused failures when agents weren't configured. The new implementation
# above makes agents optional and falls back to DSPy triage.
#
# Old behavior (commented out):
# if not intake_id or not triage_id:
#     raise RuntimeError("INTAKE_AGENT_ID and TRIAGE_AGENT_ID env vars must be set")
#
# This was problematic because:
# 1. It blocked email intake if agents weren't configured
# 2. DSPy triage is now the primary classification method
# 3. Agents are supplementary and should enhance, not block, triage
# -----------------------------------------------------------------------------
