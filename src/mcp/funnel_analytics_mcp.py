"""
Funnel Analytics MCP server for Leads Funnel v2.0

Provides tools for querying funnel metrics, conversion analysis, and attribution reporting.
Agents use this to understand funnel performance and make data-driven decisions.

Tools:
- get_funnel_metrics: Get metrics for specific stage/date range
- get_conversion_rates: Calculate stage-to-stage conversion rates
- get_stage_velocity: Average time leads spend in each stage
- get_attribution_report: Multi-touch attribution analysis
- get_cohort_analysis: Track cohort progression through funnel

Env:
- MCP_DATABASE_URL or DATABASE_URL: PostgreSQL connection string
"""
from __future__ import annotations

import os
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional
import psycopg2
from psycopg2.extras import RealDictCursor

try:
    from mcp.server.fastmcp import FastMCP, Context, ToolError
except ImportError:
    from mcp.server.fastmcp import FastMCP, Context
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

mcp = FastMCP("funnel-analytics-mcp")


def get_conn():
    try:
        return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    except Exception as e:
        raise ToolError(f"Failed to connect to database: {e}")


@mcp.tool()
def get_funnel_metrics(
    stage: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    source: Optional[str] = None,
    campaign: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get aggregated funnel metrics for specified stage and date range.

    Args:
        stage: Funnel stage (visits, discovery, consideration, conversion, retention). If None, returns all stages.
        start_date: Start date (YYYY-MM-DD). Defaults to 30 days ago.
        end_date: End date (YYYY-MM-DD). Defaults to today.
        source: Filter by attribution source (optional)
        campaign: Filter by campaign (optional)

    Returns:
        Dict with keys: stage, entries, exits, conversions_to_next, conversion_rate, avg_time_in_stage_hours
    """
    if not start_date:
        start_date = (date.today() - timedelta(days=30)).isoformat()
    if not end_date:
        end_date = date.today().isoformat()

    query = """
    SELECT
        stage,
        SUM(entries) as total_entries,
        SUM(exits) as total_exits,
        SUM(conversions_to_next) as total_conversions,
        AVG(conversion_rate) as avg_conversion_rate,
        AVG(avg_time_in_stage_hours) as avg_time_in_stage_hours,
        SUM(total_cost) as total_cost,
        AVG(cost_per_entry) as avg_cost_per_entry
    FROM funnel_metrics_daily
    WHERE metric_date >= %s AND metric_date <= %s
    """
    params = [start_date, end_date]

    if stage:
        query += " AND stage = %s"
        params.append(stage)
    if source:
        query += " AND source = %s"
        params.append(source)
    if campaign:
        query += " AND campaign = %s"
        params.append(campaign)

    query += " GROUP BY stage ORDER BY CASE stage WHEN 'visits' THEN 1 WHEN 'discovery' THEN 2 WHEN 'consideration' THEN 3 WHEN 'conversion' THEN 4 WHEN 'retention' THEN 5 END"

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(query, params)
        results = cur.fetchall()

        return {
            "start_date": start_date,
            "end_date": end_date,
            "metrics": [dict(row) for row in results]
        }


@mcp.tool()
def get_conversion_rates(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    source: Optional[str] = None
) -> Dict[str, Any]:
    """
    Calculate stage-to-stage conversion rates across the full funnel.

    Args:
        start_date: Start date (YYYY-MM-DD). Defaults to 30 days ago.
        end_date: End date (YYYY-MM-DD). Defaults to today.
        source: Filter by attribution source (optional)

    Returns:
        Dict with conversion rates between each stage pair
    """
    if not start_date:
        start_date = (date.today() - timedelta(days=30)).isoformat()
    if not end_date:
        end_date = date.today().isoformat()

    # Query to get counts at each stage entry during the period
    query = """
    WITH stage_counts AS (
        SELECT
            current_funnel_stage as stage,
            COUNT(*) as lead_count
        FROM leads
        WHERE stage_entered_at >= %s AND stage_entered_at <= %s
    """
    params = [start_date, end_date]

    if source:
        query += " AND first_attribution_source = %s"
        params.append(source)

    query += """
        GROUP BY current_funnel_stage
    )
    SELECT
        stage,
        lead_count
    FROM stage_counts
    ORDER BY CASE stage WHEN 'visits' THEN 1 WHEN 'discovery' THEN 2 WHEN 'consideration' THEN 3 WHEN 'conversion' THEN 4 WHEN 'retention' THEN 5 END
    """

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(query, params)
        results = cur.fetchall()

        # Calculate conversion rates between stages
        stage_counts = {row['stage']: row['lead_count'] for row in results}
        stages = ['visits', 'discovery', 'consideration', 'conversion', 'retention']

        conversion_rates = {}
        for i in range(len(stages) - 1):
            from_stage = stages[i]
            to_stage = stages[i + 1]
            from_count = stage_counts.get(from_stage, 0)
            to_count = stage_counts.get(to_stage, 0)

            if from_count > 0:
                rate = (to_count / from_count) * 100
            else:
                rate = 0

            conversion_rates[f"{from_stage}_to_{to_stage}"] = {
                "from_count": from_count,
                "to_count": to_count,
                "conversion_rate": round(rate, 2)
            }

        return {
            "start_date": start_date,
            "end_date": end_date,
            "source": source,
            "stage_counts": stage_counts,
            "conversion_rates": conversion_rates
        }


@mcp.tool()
def get_stage_velocity(
    stage: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Calculate average time leads spend in each funnel stage (velocity analysis).

    Args:
        stage: Specific stage to analyze. If None, returns all stages.
        start_date: Start date (YYYY-MM-DD). Defaults to 30 days ago.
        end_date: End date (YYYY-MM-DD). Defaults to today.

    Returns:
        Dict with average time in stage (hours and days) plus percentile distribution
    """
    if not start_date:
        start_date = (date.today() - timedelta(days=30)).isoformat()
    if not end_date:
        end_date = date.today().isoformat()

    query = """
    SELECT
        stage,
        COUNT(*) as total_leads,
        AVG(EXTRACT(EPOCH FROM (COALESCE(exited_at, NOW()) - entered_at)) / 3600) as avg_hours,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (COALESCE(exited_at, NOW()) - entered_at)) / 3600) as median_hours,
        PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (COALESCE(exited_at, NOW()) - entered_at)) / 3600) as p25_hours,
        PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (COALESCE(exited_at, NOW()) - entered_at)) / 3600) as p75_hours
    FROM lead_funnel_stages
    WHERE entered_at >= %s AND entered_at <= %s
    """
    params = [start_date, end_date]

    if stage:
        query += " AND stage = %s"
        params.append(stage)

    query += " GROUP BY stage ORDER BY CASE stage WHEN 'visits' THEN 1 WHEN 'discovery' THEN 2 WHEN 'consideration' THEN 3 WHEN 'conversion' THEN 4 WHEN 'retention' THEN 5 END"

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(query, params)
        results = cur.fetchall()

        velocity_data = []
        for row in results:
            velocity_data.append({
                "stage": row['stage'],
                "total_leads": row['total_leads'],
                "avg_hours": round(float(row['avg_hours'] or 0), 2),
                "avg_days": round(float(row['avg_hours'] or 0) / 24, 2),
                "median_hours": round(float(row['median_hours'] or 0), 2),
                "p25_hours": round(float(row['p25_hours'] or 0), 2),
                "p75_hours": round(float(row['p75_hours'] or 0), 2)
            })

        return {
            "start_date": start_date,
            "end_date": end_date,
            "velocity": velocity_data
        }


@mcp.tool()
def get_attribution_report(
    model: str = "first_touch",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 20
) -> Dict[str, Any]:
    """
    Generate multi-touch attribution report showing which sources/campaigns drive conversions.

    Args:
        model: Attribution model (first_touch, last_touch, linear, time_decay). Default: first_touch
        start_date: Start date (YYYY-MM-DD). Defaults to 30 days ago.
        end_date: End date (YYYY-MM-DD). Defaults to today.
        limit: Max number of sources to return. Default: 20

    Returns:
        Dict with top sources/campaigns ranked by attributed conversions
    """
    if not start_date:
        start_date = (date.today() - timedelta(days=30)).isoformat()
    if not end_date:
        end_date = date.today().isoformat()

    # Query attribution data based on model
    if model == "first_touch":
        query = """
        SELECT
            source,
            campaign,
            COUNT(*) as lead_count,
            SUM(CASE WHEN l.current_funnel_stage = 'conversion' THEN 1 ELSE 0 END) as conversions,
            ROUND(100.0 * SUM(CASE WHEN l.current_funnel_stage = 'conversion' THEN 1 ELSE 0 END) / COUNT(*), 2) as conversion_rate
        FROM lead_attribution la
        JOIN leads l ON la.lead_id = l.id
        WHERE la.touchpoint_order = 1
        AND la.touched_at >= %s AND la.touched_at <= %s
        GROUP BY source, campaign
        ORDER BY conversions DESC, lead_count DESC
        LIMIT %s
        """
    elif model == "last_touch":
        query = """
        WITH last_touches AS (
            SELECT DISTINCT ON (lead_id)
                lead_id, source, campaign, touched_at
            FROM lead_attribution
            WHERE touched_at >= %s AND touched_at <= %s
            ORDER BY lead_id, touchpoint_order DESC
        )
        SELECT
            lt.source,
            lt.campaign,
            COUNT(*) as lead_count,
            SUM(CASE WHEN l.current_funnel_stage = 'conversion' THEN 1 ELSE 0 END) as conversions,
            ROUND(100.0 * SUM(CASE WHEN l.current_funnel_stage = 'conversion' THEN 1 ELSE 0 END) / COUNT(*), 2) as conversion_rate
        FROM last_touches lt
        JOIN leads l ON lt.lead_id = l.id
        GROUP BY lt.source, lt.campaign
        ORDER BY conversions DESC, lead_count DESC
        LIMIT %s
        """
    else:
        # Linear or time_decay: use weighted attribution
        query = """
        SELECT
            source,
            campaign,
            COUNT(DISTINCT lead_id) as lead_count,
            SUM(CASE WHEN l.current_funnel_stage = 'conversion' THEN attribution_weight ELSE 0 END) as weighted_conversions,
            ROUND(100.0 * SUM(CASE WHEN l.current_funnel_stage = 'conversion' THEN attribution_weight ELSE 0 END) / COUNT(DISTINCT lead_id), 2) as conversion_rate
        FROM lead_attribution la
        JOIN leads l ON la.lead_id = l.id
        WHERE la.attribution_model = %s
        AND la.touched_at >= %s AND la.touched_at <= %s
        GROUP BY source, campaign
        ORDER BY weighted_conversions DESC, lead_count DESC
        LIMIT %s
        """
        params = [model, start_date, end_date, limit]

    if model in ["first_touch", "last_touch"]:
        params = [start_date, end_date, limit]

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(query, params)
        results = cur.fetchall()

        return {
            "attribution_model": model,
            "start_date": start_date,
            "end_date": end_date,
            "top_sources": [dict(row) for row in results]
        }


@mcp.tool()
def get_cohort_analysis(
    cohort_date: str,
    cohort_period_days: int = 7
) -> Dict[str, Any]:
    """
    Track cohort progression through funnel stages over time.

    Args:
        cohort_date: Cohort start date (YYYY-MM-DD) - leads who entered funnel on this date
        cohort_period_days: Number of days to include in cohort (default: 7 for weekly cohorts)

    Returns:
        Dict showing how many leads from cohort reached each stage, with timing
    """
    cohort_end = (datetime.fromisoformat(cohort_date) + timedelta(days=cohort_period_days)).isoformat()

    query = """
    WITH cohort_leads AS (
        SELECT id
        FROM leads
        WHERE created_at >= %s AND created_at < %s
    ),
    stage_progression AS (
        SELECT
            lfs.stage,
            COUNT(DISTINCT lfs.lead_id) as leads_reached,
            AVG(EXTRACT(EPOCH FROM (lfs.entered_at - l.created_at)) / 86400) as avg_days_to_reach
        FROM lead_funnel_stages lfs
        JOIN leads l ON lfs.lead_id = l.id
        WHERE lfs.lead_id IN (SELECT id FROM cohort_leads)
        GROUP BY lfs.stage
    )
    SELECT
        stage,
        leads_reached,
        ROUND(avg_days_to_reach::numeric, 2) as avg_days_to_reach
    FROM stage_progression
    ORDER BY CASE stage WHEN 'visits' THEN 1 WHEN 'discovery' THEN 2 WHEN 'consideration' THEN 3 WHEN 'conversion' THEN 4 WHEN 'retention' THEN 5 END
    """

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(query, [cohort_date, cohort_end])
        results = cur.fetchall()

        # Also get total cohort size
        cur.execute("SELECT COUNT(*) as cohort_size FROM leads WHERE created_at >= %s AND created_at < %s", [cohort_date, cohort_end])
        cohort_size = cur.fetchone()['cohort_size']

        return {
            "cohort_date": cohort_date,
            "cohort_period_days": cohort_period_days,
            "cohort_size": cohort_size,
            "stage_progression": [dict(row) for row in results]
        }


if __name__ == "__main__":
    mcp.run()
