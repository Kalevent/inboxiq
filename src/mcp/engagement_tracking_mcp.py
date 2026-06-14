"""
Engagement Tracking MCP server for Leads Funnel v2.0

Provides tools for recording and querying lead engagement events.
Tracks all touchpoints: email opens, page visits, content downloads, webinar attendance, etc.

Tools:
- track_engagement: Record new engagement event
- get_lead_engagement_history: Get all events for a specific lead
- get_engagement_score: Calculate engagement score for a lead
- get_recent_activity: Get recent engagement across all leads
- update_lead_engagement_summary: Recalculate engagement_count and last_engagement_at for a lead

Env:
- MCP_DATABASE_URL or DATABASE_URL: PostgreSQL connection string
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
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

mcp = FastMCP("engagement-tracking-mcp")


def get_conn():
    try:
        return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    except Exception as e:
        raise ToolError(f"Failed to connect to database: {e}") from e


@mcp.tool()
def track_engagement(
    lead_id: str,
    event_type: str,
    event_source: Optional[str] = None,
    event_data: Optional[Dict[str, Any]] = None,
    utm_source: Optional[str] = None,
    utm_medium: Optional[str] = None,
    utm_campaign: Optional[str] = None,
    utm_content: Optional[str] = None,
    utm_term: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None
) -> Dict[str, Any]:
    """
    Record a new engagement event for a lead.

    Args:
        lead_id: Lead UUID
        event_type: Type of event (email_open, email_click, page_visit, content_download, demo_requested, webinar_attended, etc.)
        event_source: Source system (email_campaign, website, linkedin, etc.)
        event_data: Additional event details as JSON (e.g., {url, page_title, document_name})
        utm_source: UTM source parameter
        utm_medium: UTM medium parameter
        utm_campaign: UTM campaign parameter
        utm_content: UTM content parameter
        utm_term: UTM term parameter
        ip_address: IP address of user
        user_agent: Browser user agent string

    Returns:
        Dict with event_id and confirmation message
    """
    import json

    # Validate lead exists
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM leads WHERE id = %s", [lead_id])
        if not cur.fetchone():
            raise ToolError(f"Lead {lead_id} not found")

        # Insert engagement event
        event_data_json = json.dumps(event_data) if event_data else None

        cur.execute("""
            INSERT INTO lead_engagement_events (
                lead_id, event_type, event_source, event_data,
                utm_source, utm_medium, utm_campaign, utm_content, utm_term,
                ip_address, user_agent
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, created_at
        """, [
            lead_id, event_type, event_source, event_data_json,
            utm_source, utm_medium, utm_campaign, utm_content, utm_term,
            ip_address, user_agent
        ])

        result = cur.fetchone()
        event_id = result['id']
        created_at = result['created_at']

        # Update lead engagement summary
        cur.execute("""
            UPDATE leads
            SET engagement_count = engagement_count + 1,
                last_engagement_at = %s
            WHERE id = %s
        """, [created_at, lead_id])

        conn.commit()

        return {
            "event_id": event_id,
            "lead_id": lead_id,
            "event_type": event_type,
            "created_at": created_at.isoformat(),
            "message": "Engagement tracked successfully"
        }


@mcp.tool()
def get_lead_engagement_history(
    lead_id: str,
    event_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
) -> Dict[str, Any]:
    """
    Get engagement history for a specific lead.

    Args:
        lead_id: Lead UUID
        event_type: Filter by event type (optional)
        limit: Max number of events to return (default: 50)
        offset: Pagination offset (default: 0)

    Returns:
        Dict with list of engagement events
    """
    query = """
    SELECT
        id, event_type, event_source, event_data,
        utm_source, utm_medium, utm_campaign, utm_content, utm_term,
        ip_address, created_at
    FROM lead_engagement_events
    WHERE lead_id = %s
    """
    params = [lead_id]

    if event_type:
        query += " AND event_type = %s"
        params.append(event_type)

    query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(query, params)
        results = cur.fetchall()

        # Get total count
        count_query = "SELECT COUNT(*) as total FROM lead_engagement_events WHERE lead_id = %s"
        count_params = [lead_id]
        if event_type:
            count_query += " AND event_type = %s"
            count_params.append(event_type)

        cur.execute(count_query, count_params)
        total = cur.fetchone()['total']

        return {
            "lead_id": lead_id,
            "total_events": total,
            "events": [dict(row) for row in results],
            "limit": limit,
            "offset": offset
        }


@mcp.tool()
def get_engagement_score(
    lead_id: str,
    days: int = 30
) -> Dict[str, Any]:
    """
    Calculate engagement score for a lead based on recent activity.

    Scoring:
    - email_open: 1 point
    - email_click: 3 points
    - page_visit: 2 points
    - content_download: 5 points
    - demo_requested: 10 points
    - webinar_attended: 8 points
    - trial_started: 15 points
    - custom events: 1 point default

    Args:
        lead_id: Lead UUID
        days: Number of days to look back (default: 30)

    Returns:
        Dict with engagement score, event breakdown, and score category
    """
    event_weights = {
        'email_open': 1,
        'email_click': 3,
        'page_visit': 2,
        'content_download': 5,
        'demo_requested': 10,
        'webinar_attended': 8,
        'trial_started': 15,
        'pricing_page_view': 4,
        'case_study_view': 3,
        'documentation_view': 2
    }

    cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

    query = """
    SELECT
        event_type,
        COUNT(*) as event_count
    FROM lead_engagement_events
    WHERE lead_id = %s AND created_at >= %s
    GROUP BY event_type
    """

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(query, [lead_id, cutoff_date])
        results = cur.fetchall()

        # Calculate score
        total_score = 0
        event_breakdown = {}

        for row in results:
            event_type = row['event_type']
            count = row['event_count']
            weight = event_weights.get(event_type, 1)  # Default 1 point for unknown events
            points = count * weight

            total_score += points
            event_breakdown[event_type] = {
                'count': count,
                'weight': weight,
                'points': points
            }

        # Categorize score
        if total_score >= 50:
            category = 'highly_engaged'
        elif total_score >= 20:
            category = 'engaged'
        elif total_score >= 5:
            category = 'somewhat_engaged'
        else:
            category = 'low_engagement'

        return {
            "lead_id": lead_id,
            "days_analyzed": days,
            "total_score": total_score,
            "category": category,
            "event_breakdown": event_breakdown
        }


@mcp.tool()
def get_recent_activity(
    event_type: Optional[str] = None,
    hours: int = 24,
    limit: int = 100
) -> Dict[str, Any]:
    """
    Get recent engagement activity across all leads.

    Args:
        event_type: Filter by event type (optional)
        hours: Number of hours to look back (default: 24)
        limit: Max number of events to return (default: 100)

    Returns:
        Dict with list of recent engagement events
    """
    cutoff_time = (datetime.now() - timedelta(hours=hours)).isoformat()

    query = """
    SELECT
        lee.id, lee.lead_id, lee.event_type, lee.event_source,
        lee.event_data, lee.created_at,
        l.name as lead_name, l.email as lead_email, l.company_name,
        l.current_funnel_stage
    FROM lead_engagement_events lee
    JOIN leads l ON lee.lead_id = l.id
    WHERE lee.created_at >= %s
    """
    params = [cutoff_time]

    if event_type:
        query += " AND lee.event_type = %s"
        params.append(event_type)

    query += " ORDER BY lee.created_at DESC LIMIT %s"
    params.append(limit)

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(query, params)
        results = cur.fetchall()

        return {
            "hours_analyzed": hours,
            "event_count": len(results),
            "events": [dict(row) for row in results]
        }


@mcp.tool()
def update_lead_engagement_summary(lead_id: str) -> Dict[str, Any]:
    """
    Recalculate engagement_count and last_engagement_at for a lead.
    Useful after bulk data import or correction.

    Args:
        lead_id: Lead UUID

    Returns:
        Dict with updated engagement count and last engagement timestamp
    """
    with get_conn() as conn, conn.cursor() as cur:
        # Validate lead exists
        cur.execute("SELECT id FROM leads WHERE id = %s", [lead_id])
        if not cur.fetchone():
            raise ToolError(f"Lead {lead_id} not found")

        # Recalculate summary
        cur.execute("""
            UPDATE leads
            SET engagement_count = (
                SELECT COUNT(*) FROM lead_engagement_events WHERE lead_id = %s
            ),
            last_engagement_at = (
                SELECT MAX(created_at) FROM lead_engagement_events WHERE lead_id = %s
            )
            WHERE id = %s
            RETURNING engagement_count, last_engagement_at
        """, [lead_id, lead_id, lead_id])

        result = cur.fetchone()
        conn.commit()

        return {
            "lead_id": lead_id,
            "engagement_count": result['engagement_count'],
            "last_engagement_at": result['last_engagement_at'].isoformat() if result['last_engagement_at'] else None,
            "message": "Engagement summary updated successfully"
        }


if __name__ == "__main__":
    mcp.run()
