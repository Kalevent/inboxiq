"""
ROI Calculator for Automation Studio

Calculates and tracks return on investment metrics for automation rules:
- Time saved per week/month
- Cost reduction
- Accuracy rate (how many auto-actions were correct vs. manually corrected)
- Response time impact

These metrics are displayed in the UI to show real-time value of automation.
"""

from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy import func

from src.models import AutomationRule, AutomationRuleExecution, db


def calculate_rule_roi(
    rule_id: str,
    time_period: str = "month"
) -> Dict[str, Any]:
    """
    Calculate ROI metrics for an automation rule.

    Args:
        rule_id: AutomationRule ID
        time_period: "week", "month", "quarter", "year", or "all_time"

    Returns:
        {
            "time_saved": {
                "seconds": 14400,
                "hours": 4.0,
                "display": "4 hours saved this month"
            },
            "cost_saved": {
                "amount": 60.00,
                "currency": "USD",
                "display": "$60 saved this month"
            },
            "accuracy": {
                "rate": 0.94,
                "correct": 47,
                "total": 50,
                "display": "94% accuracy (47/50)"
            },
            "executions": {
                "total": 50,
                "successful": 48,
                "failed": 2
            }
        }
    """
    rule = AutomationRule.query.filter_by(id=rule_id).first()
    if not rule:
        raise ValueError(f"Rule not found: {rule_id}")

    # Calculate date range
    start_date = _get_start_date(time_period)

    # Query executions in time period
    executions_query = AutomationRuleExecution.query.filter(
        AutomationRuleExecution.rule_id == rule_id,
        AutomationRuleExecution.created_at >= start_date
    )

    total_executions = executions_query.count()
    successful_executions = executions_query.filter(
        AutomationRuleExecution.success == True
    ).count()
    failed_executions = total_executions - successful_executions

    # Calculate time saved
    baseline_time_seconds = rule.baseline_time_per_execution or 180  # Default: 3 minutes per manual action
    total_time_saved_seconds = successful_executions * baseline_time_seconds
    time_saved_hours = total_time_saved_seconds / 3600.0

    # Calculate cost saved
    baseline_cost = float(rule.baseline_cost_per_execution or 0.75)  # Default: $0.75 per manual action
    total_cost_saved = successful_executions * baseline_cost

    # Calculate accuracy rate (tickets not reassigned = accurate routing)
    reassigned_count = executions_query.filter(
        AutomationRuleExecution.ticket_reassigned == True
    ).count()
    accurate_count = successful_executions - reassigned_count
    accuracy_rate = (accurate_count / successful_executions) if successful_executions > 0 else 0.0

    # Build response
    time_period_display = _get_time_period_display(time_period)

    return {
        "rule_id": rule_id,
        "rule_name": rule.name,
        "time_period": time_period,
        "time_saved": {
            "seconds": total_time_saved_seconds,
            "hours": round(time_saved_hours, 1),
            "display": f"{round(time_saved_hours, 1)} hours saved {time_period_display}"
        },
        "cost_saved": {
            "amount": round(total_cost_saved, 2),
            "currency": "USD",
            "display": f"${round(total_cost_saved, 2)} saved {time_period_display}"
        },
        "accuracy": {
            "rate": round(accuracy_rate, 2),
            "correct": accurate_count,
            "total": successful_executions,
            "display": f"{int(accuracy_rate * 100)}% accuracy ({accurate_count}/{successful_executions})"
        },
        "executions": {
            "total": total_executions,
            "successful": successful_executions,
            "failed": failed_executions
        }
    }


def calculate_account_roi(account_id: int, time_period: str = "month") -> Dict[str, Any]:
    """
    Calculate aggregate ROI metrics for all automation rules in an account.

    Args:
        account_id: Account ID
        time_period: "week", "month", "quarter", "year", or "all_time"

    Returns:
        {
            "total_time_saved": {...},
            "total_cost_saved": {...},
            "overall_accuracy": {...},
            "total_executions": 500,
            "active_rules": 12,
            "rules_breakdown": [...]
        }
    """
    rules = AutomationRule.query.filter_by(
        account_id=account_id,
        enabled=True
    ).all()

    # Aggregate metrics across all rules
    total_time_saved_seconds = 0
    total_cost_saved = 0.0
    total_executions = 0
    total_accurate = 0

    rules_breakdown = []

    for rule in rules:
        rule_roi = calculate_rule_roi(rule.id, time_period)

        total_time_saved_seconds += rule_roi["time_saved"]["seconds"]
        total_cost_saved += rule_roi["cost_saved"]["amount"]
        total_executions += rule_roi["executions"]["total"]
        total_accurate += rule_roi["accuracy"]["correct"]

        rules_breakdown.append({
            "rule_id": rule.id,
            "rule_name": rule.name,
            "time_saved_hours": rule_roi["time_saved"]["hours"],
            "cost_saved": rule_roi["cost_saved"]["amount"],
            "accuracy": rule_roi["accuracy"]["rate"],
            "executions": rule_roi["executions"]["total"]
        })

    # Sort by time saved (highest first)
    rules_breakdown.sort(key=lambda x: x["time_saved_hours"], reverse=True)

    time_saved_hours = total_time_saved_seconds / 3600.0
    overall_accuracy = (total_accurate / total_executions) if total_executions > 0 else 0.0

    time_period_display = _get_time_period_display(time_period)

    return {
        "account_id": account_id,
        "time_period": time_period,
        "total_time_saved": {
            "seconds": total_time_saved_seconds,
            "hours": round(time_saved_hours, 1),
            "display": f"{round(time_saved_hours, 1)} hours saved {time_period_display}"
        },
        "total_cost_saved": {
            "amount": round(total_cost_saved, 2),
            "currency": "USD",
            "display": f"${round(total_cost_saved, 2)} saved {time_period_display}"
        },
        "overall_accuracy": {
            "rate": round(overall_accuracy, 2),
            "display": f"{int(overall_accuracy * 100)}% accuracy"
        },
        "total_executions": total_executions,
        "active_rules": len(rules),
        "rules_breakdown": rules_breakdown
    }


def track_ticket_reassignment(
    ticket_id: str,
    automation_execution_id: str
) -> None:
    """
    Mark an automation execution as inaccurate when a ticket is manually reassigned.

    Used to track accuracy: if a ticket was auto-assigned by automation but then
    manually reassigned to a different team, the automation was inaccurate.

    Args:
        ticket_id: Ticket ID that was reassigned
        automation_execution_id: AutomationRuleExecution ID to mark

    Returns:
        None
    """
    execution = AutomationRuleExecution.query.filter_by(id=automation_execution_id).first()
    if execution and execution.ticket_id == ticket_id:
        execution.ticket_reassigned = True
        execution.reassignment_timestamp = datetime.utcnow()
        db.session.commit()


def update_rule_aggregate_metrics(rule_id: str) -> None:
    """
    Update aggregate metrics on AutomationRule from all executions.

    Updates:
    - total_executions
    - successful_executions
    - avg_execution_time_ms
    - accuracy_rate
    - total_time_saved_seconds
    - total_cost_saved

    Should be called periodically (e.g., nightly) or after each execution.

    Args:
        rule_id: AutomationRule ID

    Returns:
        None
    """
    rule = AutomationRule.query.filter_by(id=rule_id).first()
    if not rule:
        return

    # Count executions
    executions_query = AutomationRuleExecution.query.filter_by(rule_id=rule_id)

    total_executions = executions_query.count()
    successful_executions = executions_query.filter_by(success=True).count()

    # Average execution time
    avg_time_result = db.session.query(
        func.avg(AutomationRuleExecution.execution_time_ms)
    ).filter_by(rule_id=rule_id).scalar()

    avg_execution_time_ms = int(avg_time_result) if avg_time_result else 0

    # Accuracy rate
    reassigned_count = executions_query.filter_by(ticket_reassigned=True).count()
    accurate_count = successful_executions - reassigned_count
    accuracy_rate = (accurate_count / successful_executions) if successful_executions > 0 else 0.0

    # Time and cost saved
    baseline_time_seconds = rule.baseline_time_per_execution or 180
    baseline_cost = float(rule.baseline_cost_per_execution or 0.75)

    total_time_saved_seconds = successful_executions * baseline_time_seconds
    total_cost_saved = successful_executions * baseline_cost

    # Update rule
    rule.total_executions = total_executions
    rule.successful_executions = successful_executions
    rule.avg_execution_time_ms = avg_execution_time_ms
    rule.accuracy_rate = accuracy_rate
    rule.total_time_saved_seconds = total_time_saved_seconds
    rule.total_cost_saved = total_cost_saved

    db.session.commit()


def _get_start_date(time_period: str) -> datetime:
    """Get start date for time period."""
    now = datetime.utcnow()

    if time_period == "week":
        return now - timedelta(days=7)
    elif time_period == "month":
        return now - timedelta(days=30)
    elif time_period == "quarter":
        return now - timedelta(days=90)
    elif time_period == "year":
        return now - timedelta(days=365)
    elif time_period == "all_time":
        return datetime(2020, 1, 1)  # Beginning of time
    else:
        raise ValueError(f"Invalid time_period: {time_period}")


def _get_time_period_display(time_period: str) -> str:
    """Get display string for time period."""
    displays = {
        "week": "this week",
        "month": "this month",
        "quarter": "this quarter",
        "year": "this year",
        "all_time": "all time"
    }
    return displays.get(time_period, time_period)


# Celery task for periodic metric updates
def update_all_rule_metrics(account_id: Optional[int] = None):
    """
    Update aggregate metrics for all rules (or all rules in an account).

    Should be run as a daily Celery task.

    Args:
        account_id: Optional account ID to limit scope

    Returns:
        Number of rules updated
    """
    if account_id:
        rules = AutomationRule.query.filter_by(account_id=account_id).all()
    else:
        rules = AutomationRule.query.all()

    for rule in rules:
        update_rule_aggregate_metrics(rule.id)

    return len(rules)
