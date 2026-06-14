"""
Stage Orchestration MCP server for Leads Funnel v2.0

Manages lead progression through funnel stages with validation and business logic.
Handles stage transitions, scoring updates, and automated stage progression rules.

Tools:
- move_lead_to_stage: Transition lead to new funnel stage
- bulk_stage_transition: Move multiple leads to new stage
- get_leads_ready_for_progression: Find leads eligible for stage advancement
- calculate_stage_readiness: Check if lead meets criteria for next stage
- get_lead_stage_history: View full stage progression history

Env:
- MCP_DATABASE_URL or DATABASE_URL: PostgreSQL connection string
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List, Optional
import psycopg2
from psycopg2.extras import RealDictCursor

try:
    from mcp.server.fastmcp import FastMCP, Context, ToolError
except ImportError:
    from mcp.server.fastmcp import FastMCP
    try:
        from mcp.types import ToolError
    except ImportError:
        class ToolError(Exception):
            pass


DATABASE_URL = (
    os.getenv("MCP_DATABASE_URL")
    or os.getenv("DATABASE_URL")
    or os.getenv("DATABASE_DEV_URL")
)

if not DATABASE_URL:
    raise RuntimeError(
        "No database URL found. Set MCP_DATABASE_URL or DATABASE_URL."
    )

mcp = FastMCP("stage-orchestration-mcp")

VALID_STAGES = ['visits', 'discovery', 'consideration', 'conversion', 'retention']


def get_conn():
    try:
        return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    except Exception as e:
        raise ToolError(f"Failed to connect to database: {e}") from e


@mcp.tool()
def move_lead_to_stage(
    lead_id: str,
    new_stage: str,
    sub_stage: Optional[str] = None,
    conversion_probability: Optional[float] = None,
    notes: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Transition a lead to a new funnel stage.

    Validates stage transition, updates lead record, creates stage history entry,
    and updates engagement tracking.

    Args:
        lead_id: Lead UUID
        new_stage: Target stage (visits, discovery, consideration, conversion, retention)
        sub_stage: Optional sub-stage (e.g., demo_requested, trial_active, onboarding)
        conversion_probability: DSPy prediction of conversion likelihood (0-1)
        notes: Optional notes about this transition
        metadata: Additional stage-specific data

    Returns:
        Dict with confirmation and updated lead info
    """
    import json

    if new_stage not in VALID_STAGES:
        raise ToolError(f"Invalid stage: {new_stage}. Must be one of {VALID_STAGES}")

    with get_conn() as conn, conn.cursor() as cur:
        # Get current lead state
        cur.execute("""
            SELECT id, current_funnel_stage, stage_entered_at, name, email
            FROM leads
            WHERE id = %s
        """, [lead_id])

        lead = cur.fetchone()
        if not lead:
            raise ToolError(f"Lead {lead_id} not found")

        old_stage = lead['current_funnel_stage']
        old_stage_entered_at = lead['stage_entered_at']

        # Validate stage progression (prevent backward movement unless intentional)
        stage_order = {stage: idx for idx, stage in enumerate(VALID_STAGES)}
        if stage_order[new_stage] < stage_order[old_stage]:
            if not notes or "manual" not in notes.lower():
                raise ToolError(
                    f"Moving backward from {old_stage} to {new_stage} requires notes with 'manual' keyword"
                )

        now = datetime.now()

        # Close current stage in history
        if old_stage:
            cur.execute("""
                UPDATE lead_funnel_stages
                SET exited_at = %s
                WHERE lead_id = %s AND stage = %s AND exited_at IS NULL
            """, [now, lead_id, old_stage])

        # Create new stage history entry
        metadata_json = json.dumps(metadata) if metadata else None

        cur.execute("""
            INSERT INTO lead_funnel_stages (
                lead_id, stage, sub_stage, entered_at,
                conversion_probability, notes, metadata_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, [
            lead_id, new_stage, sub_stage, now,
            conversion_probability, notes, metadata_json
        ])

        stage_history_id = cur.fetchone()['id']

        # Update lead record
        cur.execute("""
            UPDATE leads
            SET current_funnel_stage = %s,
                stage_entered_at = %s,
                conversion_probability = COALESCE(%s, conversion_probability),
                updated_at = %s
            WHERE id = %s
            RETURNING current_funnel_stage, stage_entered_at, fit_score, intent_score
        """, [new_stage, now, conversion_probability, now, lead_id])

        updated_lead = cur.fetchone()

        conn.commit()

        return {
            "lead_id": lead_id,
            "lead_name": lead['name'],
            "lead_email": lead['email'],
            "old_stage": old_stage,
            "new_stage": new_stage,
            "sub_stage": sub_stage,
            "stage_history_id": stage_history_id,
            "fit_score": updated_lead['fit_score'],
            "intent_score": updated_lead['intent_score'],
            "conversion_probability": conversion_probability,
            "transitioned_at": now.isoformat(),
            "message": f"Lead transitioned from {old_stage} to {new_stage}"
        }


@mcp.tool()
def bulk_stage_transition(
    lead_ids: List[str],
    new_stage: str,
    notes: Optional[str] = None
) -> Dict[str, Any]:
    """
    Move multiple leads to a new stage in bulk.

    Args:
        lead_ids: List of lead UUIDs
        new_stage: Target stage (visits, discovery, consideration, conversion, retention)
        notes: Optional notes applied to all transitions

    Returns:
        Dict with count of successful transitions and any errors
    """
    if new_stage not in VALID_STAGES:
        raise ToolError(f"Invalid stage: {new_stage}. Must be one of {VALID_STAGES}")

    successful = []
    failed = []

    for lead_id in lead_ids:
        try:
            result = move_lead_to_stage(
                lead_id=lead_id,
                new_stage=new_stage,
                notes=notes or f"Bulk transition to {new_stage}"
            )
            successful.append({
                "lead_id": lead_id,
                "old_stage": result['old_stage'],
                "new_stage": result['new_stage']
            })
        except Exception as e:
            failed.append({
                "lead_id": lead_id,
                "error": str(e)
            })

    return {
        "total_leads": len(lead_ids),
        "successful": len(successful),
        "failed": len(failed),
        "transitions": successful,
        "errors": failed
    }


@mcp.tool()
def get_leads_ready_for_progression(
    current_stage: str,
    min_fit_score: Optional[int] = None,
    min_intent_score: Optional[int] = None,
    min_engagement_count: Optional[int] = None,
    min_days_in_stage: Optional[int] = None,
    limit: int = 50
) -> Dict[str, Any]:
    """
    Find leads eligible for stage advancement based on criteria.

    Args:
        current_stage: Current stage to filter (visits, discovery, consideration, conversion, retention)
        min_fit_score: Minimum ICP fit score (0-10)
        min_intent_score: Minimum buying intent score (0-12)
        min_engagement_count: Minimum number of engagement events
        min_days_in_stage: Minimum days in current stage
        limit: Max leads to return (default: 50)

    Returns:
        Dict with list of leads ready for progression
    """
    if current_stage not in VALID_STAGES:
        raise ToolError(f"Invalid stage: {current_stage}. Must be one of {VALID_STAGES}")

    query = """
    SELECT
        id, name, email, company_name,
        current_funnel_stage, stage_entered_at,
        fit_score, intent_score, engagement_count,
        conversion_probability, last_engagement_at,
        EXTRACT(EPOCH FROM (NOW() - stage_entered_at)) / 86400 as days_in_stage
    FROM leads
    WHERE current_funnel_stage = %s
    """
    params = [current_stage]

    if min_fit_score is not None:
        query += " AND fit_score >= %s"
        params.append(min_fit_score)

    if min_intent_score is not None:
        query += " AND intent_score >= %s"
        params.append(min_intent_score)

    if min_engagement_count is not None:
        query += " AND engagement_count >= %s"
        params.append(min_engagement_count)

    if min_days_in_stage is not None:
        query += " AND EXTRACT(EPOCH FROM (NOW() - stage_entered_at)) / 86400 >= %s"
        params.append(min_days_in_stage)

    query += " ORDER BY conversion_probability DESC NULLS LAST, intent_score DESC, fit_score DESC LIMIT %s"
    params.append(limit)

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(query, params)
        results = cur.fetchall()

        leads = []
        for row in results:
            leads.append({
                "id": row['id'],
                "name": row['name'],
                "email": row['email'],
                "company_name": row['company_name'],
                "current_stage": row['current_funnel_stage'],
                "fit_score": row['fit_score'],
                "intent_score": row['intent_score'],
                "engagement_count": row['engagement_count'],
                "conversion_probability": float(row['conversion_probability']) if row['conversion_probability'] else None,
                "days_in_stage": round(float(row['days_in_stage']), 1),
                "last_engagement_at": row['last_engagement_at'].isoformat() if row['last_engagement_at'] else None
            })

        return {
            "current_stage": current_stage,
            "criteria": {
                "min_fit_score": min_fit_score,
                "min_intent_score": min_intent_score,
                "min_engagement_count": min_engagement_count,
                "min_days_in_stage": min_days_in_stage
            },
            "lead_count": len(leads),
            "leads": leads
        }


@mcp.tool()
def calculate_stage_readiness(lead_id: str) -> Dict[str, Any]:
    """
    Check if lead meets criteria for advancement to next stage.

    Returns readiness assessment with scores and recommendations.

    Args:
        lead_id: Lead UUID

    Returns:
        Dict with readiness scores, criteria met, and recommended next action
    """
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT
                id, name, email, current_funnel_stage, stage_entered_at,
                fit_score, intent_score, engagement_count, conversion_probability,
                last_engagement_at,
                EXTRACT(EPOCH FROM (NOW() - stage_entered_at)) / 86400 as days_in_stage
            FROM leads
            WHERE id = %s
        """, [lead_id])

        lead = cur.fetchone()
        if not lead:
            raise ToolError(f"Lead {lead_id} not found")

        current_stage = lead['current_funnel_stage']
        fit_score = lead['fit_score'] or 0
        intent_score = lead['intent_score'] or 0
        engagement_count = lead['engagement_count'] or 0
        days_in_stage = float(lead['days_in_stage'] or 0)

        # Stage-specific readiness criteria
        readiness_criteria = {
            'visits': {
                'next_stage': 'discovery',
                'min_engagement': 3,
                'min_fit_score': 5,
                'recommended_action': 'Send personalized cold email'
            },
            'discovery': {
                'next_stage': 'consideration',
                'min_engagement': 8,
                'min_fit_score': 6,
                'min_intent_score': 5,
                'recommended_action': 'Offer demo or free trial'
            },
            'consideration': {
                'next_stage': 'conversion',
                'min_engagement': 15,
                'min_fit_score': 7,
                'min_intent_score': 8,
                'recommended_action': 'Send proposal or pricing'
            },
            'conversion': {
                'next_stage': 'retention',
                'min_engagement': 5,
                'min_fit_score': 7,
                'recommended_action': 'Onboarding and activation campaign'
            },
            'retention': {
                'next_stage': None,
                'recommended_action': 'Upsell and referral campaigns'
            }
        }

        criteria = readiness_criteria.get(current_stage, {})
        next_stage = criteria.get('next_stage')

        # Check criteria
        checks = {}
        ready = True

        if 'min_engagement' in criteria:
            checks['engagement'] = {
                'required': criteria['min_engagement'],
                'actual': engagement_count,
                'met': engagement_count >= criteria['min_engagement']
            }
            ready = ready and checks['engagement']['met']

        if 'min_fit_score' in criteria:
            checks['fit_score'] = {
                'required': criteria['min_fit_score'],
                'actual': fit_score,
                'met': fit_score >= criteria['min_fit_score']
            }
            ready = ready and checks['fit_score']['met']

        if 'min_intent_score' in criteria:
            checks['intent_score'] = {
                'required': criteria['min_intent_score'],
                'actual': intent_score,
                'met': intent_score >= criteria['min_intent_score']
            }
            ready = ready and checks['intent_score']['met']

        # Check if stalled (too long in stage)
        stall_thresholds = {
            'visits': 14,  # 2 weeks
            'discovery': 30,  # 1 month
            'consideration': 60,  # 2 months
            'conversion': 90,  # 3 months
            'retention': 180  # 6 months
        }

        is_stalled = days_in_stage > stall_thresholds.get(current_stage, 30)

        return {
            "lead_id": lead_id,
            "lead_name": lead['name'],
            "current_stage": current_stage,
            "next_stage": next_stage,
            "days_in_stage": round(days_in_stage, 1),
            "is_stalled": is_stalled,
            "ready_for_progression": ready if next_stage else False,
            "criteria_checks": checks,
            "scores": {
                "fit_score": fit_score,
                "intent_score": intent_score,
                "engagement_count": engagement_count,
                "conversion_probability": float(lead['conversion_probability']) if lead['conversion_probability'] else None
            },
            "recommended_action": criteria.get('recommended_action', 'Continue nurturing')
        }


@mcp.tool()
def get_lead_stage_history(lead_id: str) -> Dict[str, Any]:
    """
    View full stage progression history for a lead.

    Args:
        lead_id: Lead UUID

    Returns:
        Dict with chronological list of stage transitions
    """
    with get_conn() as conn, conn.cursor() as cur:
        # Get lead info
        cur.execute("SELECT id, name, email, current_funnel_stage FROM leads WHERE id = %s", [lead_id])
        lead = cur.fetchone()
        if not lead:
            raise ToolError(f"Lead {lead_id} not found")

        # Get stage history
        cur.execute("""
            SELECT
                id, stage, sub_stage, entered_at, exited_at,
                conversion_probability, notes, metadata_json,
                EXTRACT(EPOCH FROM (COALESCE(exited_at, NOW()) - entered_at)) / 86400 as days_in_stage
            FROM lead_funnel_stages
            WHERE lead_id = %s
            ORDER BY entered_at ASC
        """, [lead_id])

        stages = cur.fetchall()

        history = []
        for row in stages:
            history.append({
                "stage_id": row['id'],
                "stage": row['stage'],
                "sub_stage": row['sub_stage'],
                "entered_at": row['entered_at'].isoformat(),
                "exited_at": row['exited_at'].isoformat() if row['exited_at'] else None,
                "days_in_stage": round(float(row['days_in_stage']), 1),
                "conversion_probability": float(row['conversion_probability']) if row['conversion_probability'] else None,
                "notes": row['notes'],
                "metadata": row['metadata_json']
            })

        return {
            "lead_id": lead_id,
            "lead_name": lead['name'],
            "lead_email": lead['email'],
            "current_stage": lead['current_funnel_stage'],
            "total_stages": len(history),
            "stage_history": history
        }


if __name__ == "__main__":
    mcp.run()
