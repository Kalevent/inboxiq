"""
Attribution MCP server for Leads Funnel v2.0

Multi-touch attribution tracking and analysis.
Records and analyzes all touchpoints in the customer journey.

Supports multiple attribution models:
- First-touch: 100% credit to first touchpoint
- Last-touch: 100% credit to last touchpoint
- Linear: Equal credit across all touchpoints
- Time-decay: More credit to recent touchpoints

Tools:
- record_touchpoint: Record new attribution touchpoint
- calculate_attribution_weights: Calculate weights for a lead's journey
- apply_attribution_model: Apply specific model to lead's touchpoints
- get_lead_touchpoints: Get full attribution history for a lead
- compare_attribution_models: Compare multiple models side-by-side

Env:
- MCP_DATABASE_URL or DATABASE_URL: PostgreSQL connection string
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
import math

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

mcp = FastMCP("attribution-mcp")


def get_conn():
    try:
        return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    except Exception as e:
        raise ToolError(f"Failed to connect to database: {e}") from e


@mcp.tool()
def record_touchpoint(
    lead_id: str,
    source: str,
    medium: Optional[str] = None,
    campaign: Optional[str] = None,
    content: Optional[str] = None,
    term: Optional[str] = None,
    touched_at: Optional[str] = None
) -> Dict[str, Any]:
    """
    Record a new attribution touchpoint for a lead.

    Args:
        lead_id: Lead UUID
        source: Attribution source (google, linkedin, email, direct, etc.)
        medium: Marketing medium (cpc, organic, social, email, etc.)
        campaign: Campaign name/ID
        content: Content identifier (ad variant, email template)
        term: Search term or keyword
        touched_at: Timestamp of touchpoint (ISO format, defaults to now)

    Returns:
        Dict with touchpoint_id and order number
    """
    if not lead_id or not source:
        raise ToolError("lead_id and source are required")

    if not touched_at:
        touched_at = datetime.now().isoformat()

    with get_conn() as conn, conn.cursor() as cur:
        # Validate lead exists
        cur.execute("SELECT id FROM leads WHERE id = %s", [lead_id])
        if not cur.fetchone():
            raise ToolError(f"Lead {lead_id} not found")

        # Get next touchpoint order
        cur.execute("""
            SELECT COALESCE(MAX(touchpoint_order), 0) + 1 as next_order
            FROM lead_attribution
            WHERE lead_id = %s
        """, [lead_id])
        touchpoint_order = cur.fetchone()['next_order']

        # Insert touchpoint
        cur.execute("""
            INSERT INTO lead_attribution (
                lead_id, touchpoint_order, source, medium, campaign,
                content, term, touched_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, [
            lead_id, touchpoint_order, source, medium, campaign,
            content, term, touched_at
        ])

        touchpoint_id = cur.fetchone()['id']

        # Update lead's first attribution if this is first touchpoint
        if touchpoint_order == 1:
            cur.execute("""
                UPDATE leads
                SET first_attribution_source = %s,
                    first_attribution_campaign = %s
                WHERE id = %s
            """, [source, campaign, lead_id])

        conn.commit()

        return {
            "touchpoint_id": touchpoint_id,
            "lead_id": lead_id,
            "touchpoint_order": touchpoint_order,
            "source": source,
            "medium": medium,
            "campaign": campaign,
            "touched_at": touched_at,
            "message": f"Touchpoint #{touchpoint_order} recorded successfully"
        }


@mcp.tool()
def calculate_attribution_weights(
    lead_id: str,
    model: str = "linear",
    decay_days: Optional[int] = 7
) -> Dict[str, Any]:
    """
    Calculate attribution weights for all touchpoints of a lead.

    Args:
        lead_id: Lead UUID
        model: Attribution model (first_touch, last_touch, linear, time_decay)
        decay_days: For time_decay model, half-life in days (default: 7)

    Returns:
        Dict with touchpoints and calculated weights
    """
    valid_models = ["first_touch", "last_touch", "linear", "time_decay"]
    if model not in valid_models:
        raise ToolError(f"Invalid model: {model}. Must be one of {valid_models}")

    with get_conn() as conn, conn.cursor() as cur:
        # Get all touchpoints for lead
        cur.execute("""
            SELECT
                id, touchpoint_order, source, medium, campaign,
                touched_at
            FROM lead_attribution
            WHERE lead_id = %s
            ORDER BY touchpoint_order ASC
        """, [lead_id])

        touchpoints = cur.fetchall()

        if not touchpoints:
            raise ToolError(f"No touchpoints found for lead {lead_id}")

        total_touchpoints = len(touchpoints)
        weighted_touchpoints = []

        if model == "first_touch":
            # First touchpoint gets 100% credit
            for i, tp in enumerate(touchpoints):
                weight = 1.0 if i == 0 else 0.0
                weighted_touchpoints.append({
                    **dict(tp),
                    "attribution_weight": weight,
                    "attribution_model": model
                })

        elif model == "last_touch":
            # Last touchpoint gets 100% credit
            for i, tp in enumerate(touchpoints):
                weight = 1.0 if i == total_touchpoints - 1 else 0.0
                weighted_touchpoints.append({
                    **dict(tp),
                    "attribution_weight": weight,
                    "attribution_model": model
                })

        elif model == "linear":
            # Equal credit to all touchpoints
            weight = 1.0 / total_touchpoints
            for tp in touchpoints:
                weighted_touchpoints.append({
                    **dict(tp),
                    "attribution_weight": weight,
                    "attribution_model": model
                })

        elif model == "time_decay":
            # Exponential decay based on time
            # More recent = higher weight
            now = datetime.now()
            decay_constant = math.log(2) / decay_days  # Half-life decay

            weights = []
            for tp in touchpoints:
                days_ago = (now - tp['touched_at']).total_seconds() / 86400
                weight = math.exp(-decay_constant * days_ago)
                weights.append(weight)

            # Normalize weights to sum to 1.0
            total_weight = sum(weights)
            normalized_weights = [w / total_weight for w in weights]

            for tp, weight in zip(touchpoints, normalized_weights):
                weighted_touchpoints.append({
                    **dict(tp),
                    "attribution_weight": round(weight, 4),
                    "attribution_model": model
                })

        return {
            "lead_id": lead_id,
            "attribution_model": model,
            "total_touchpoints": total_touchpoints,
            "decay_days": decay_days if model == "time_decay" else None,
            "touchpoints": weighted_touchpoints
        }


@mcp.tool()
def apply_attribution_model(
    lead_id: str,
    model: str = "linear",
    decay_days: Optional[int] = 7
) -> Dict[str, Any]:
    """
    Apply attribution model and persist weights to database.

    Args:
        lead_id: Lead UUID
        model: Attribution model (first_touch, last_touch, linear, time_decay)
        decay_days: For time_decay model, half-life in days (default: 7)

    Returns:
        Dict with confirmation and updated touchpoint count
    """
    # Calculate weights
    result = calculate_attribution_weights(lead_id=lead_id, model=model, decay_days=decay_days)

    # Update database with weights
    with get_conn() as conn, conn.cursor() as cur:
        for tp in result['touchpoints']:
            cur.execute("""
                UPDATE lead_attribution
                SET attribution_model = %s,
                    attribution_weight = %s
                WHERE id = %s
            """, [model, tp['attribution_weight'], tp['id']])

        conn.commit()

        return {
            "lead_id": lead_id,
            "attribution_model": model,
            "touchpoints_updated": len(result['touchpoints']),
            "message": f"Applied {model} attribution model to {len(result['touchpoints'])} touchpoints"
        }


@mcp.tool()
def get_lead_touchpoints(
    lead_id: str,
    model: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get full attribution history for a lead with weights.

    Args:
        lead_id: Lead UUID
        model: Filter by attribution model (optional)

    Returns:
        Dict with chronological list of touchpoints and weights
    """
    query = """
    SELECT
        id, touchpoint_order, source, medium, campaign,
        content, term, attribution_model, attribution_weight,
        touched_at
    FROM lead_attribution
    WHERE lead_id = %s
    """
    params = [lead_id]

    if model:
        query += " AND attribution_model = %s"
        params.append(model)

    query += " ORDER BY touchpoint_order ASC"

    with get_conn() as conn, conn.cursor() as cur:
        # Get lead info
        cur.execute("SELECT id, name, email, current_funnel_stage FROM leads WHERE id = %s", [lead_id])
        lead = cur.fetchone()
        if not lead:
            raise ToolError(f"Lead {lead_id} not found")

        # Get touchpoints
        cur.execute(query, params)
        touchpoints = cur.fetchall()

        return {
            "lead_id": lead_id,
            "lead_name": lead['name'],
            "lead_email": lead['email'],
            "current_stage": lead['current_funnel_stage'],
            "total_touchpoints": len(touchpoints),
            "touchpoints": [dict(tp) for tp in touchpoints]
        }


@mcp.tool()
def compare_attribution_models(
    lead_id: str,
    models: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Compare multiple attribution models side-by-side for a lead.

    Shows how credit distribution changes across models.

    Args:
        lead_id: Lead UUID
        models: List of models to compare (default: all 4 models)

    Returns:
        Dict with comparison table showing weights per touchpoint per model
    """
    if not models:
        models = ["first_touch", "last_touch", "linear", "time_decay"]

    comparison = {}

    for model in models:
        result = calculate_attribution_weights(lead_id=lead_id, model=model)
        comparison[model] = result['touchpoints']

    # Build comparison table
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT touchpoint_order, source, medium, campaign, touched_at
            FROM lead_attribution
            WHERE lead_id = %s
            ORDER BY touchpoint_order ASC
        """, [lead_id])

        touchpoints = cur.fetchall()

        comparison_table = []
        for tp in touchpoints:
            row = {
                "touchpoint_order": tp['touchpoint_order'],
                "source": tp['source'],
                "medium": tp['medium'],
                "campaign": tp['campaign'],
                "touched_at": tp['touched_at'].isoformat(),
                "weights": {}
            }

            for model in models:
                # Find weight for this touchpoint in this model
                for model_tp in comparison[model]:
                    if model_tp['touchpoint_order'] == tp['touchpoint_order']:
                        row["weights"][model] = model_tp['attribution_weight']
                        break

            comparison_table.append(row)

        return {
            "lead_id": lead_id,
            "models_compared": models,
            "total_touchpoints": len(touchpoints),
            "comparison_table": comparison_table
        }


if __name__ == "__main__":
    mcp.run()
