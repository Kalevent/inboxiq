"""
Admin API endpoints for Trial Onboarding monitoring

Provides metrics and monitoring for trial user onboarding emails.

Endpoints:
- GET /api/v1/admin/trial/metrics - Get trial onboarding metrics
- POST /api/v1/admin/trial/send-test - Send test onboarding email
"""
from datetime import datetime, timedelta, timezone
from flask import jsonify, request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func, case

from src.api.v1 import v1
from src.api.v1.admin import _require_admin
from src.extensions import db
from src.models.core import User, Account
from src.models.billing import CustomerBillingProfile




@v1.route("/admin/trial/metrics", methods=["GET"])
@jwt_required()
def get_trial_metrics():
    """
    Get trial onboarding metrics.

    Returns:
        - Active trial users
        - Email delivery stats (Day 1, 3, 5, 7)
        - Conversion rates
        - Days since signup distribution
    """
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    # Get recent users — extend window to 90 days to capture long-running beta trials
    ninety_days_ago = datetime.now(timezone.utc) - timedelta(days=90)

    active_trials = db.session.query(
        User.id,
        User.email,
        User.name,
        User.created_at,
        Account.id.label('account_id'),
        Account.name.label('account_name'),
        CustomerBillingProfile.trial_end.label('trial_end'),
    ).join(
        Account, User.account_id == Account.id
    ).outerjoin(
        CustomerBillingProfile, CustomerBillingProfile.account_id == Account.id
    ).filter(
        User.created_at >= ninety_days_ago
    ).order_by(
        User.created_at.desc()
    ).all()

    # Calculate days since signup for each user
    now = datetime.now(timezone.utc)
    trial_users = []
    for user in active_trials:
        days_since_signup = (now - user.created_at).days if user.created_at else 0

        # Use actual trial_end from billing profile; fall back to 7-day default
        if user.trial_end:
            trial_end_dt = user.trial_end if user.trial_end.tzinfo else user.trial_end.replace(tzinfo=timezone.utc)
            trial_days_remaining = max(0, (trial_end_dt - now).days)
        else:
            trial_days_remaining = max(0, 7 - days_since_signup)

        # Determine which emails should have been sent
        expected_emails = []
        if days_since_signup >= 0:
            expected_emails.append('Day 1')
        if days_since_signup >= 2:
            expected_emails.append('Day 3')
        if days_since_signup >= 4:
            expected_emails.append('Day 5')
        if days_since_signup >= 6:
            expected_emails.append('Day 7')

        # Determine trial status based on actual remaining days
        if trial_days_remaining == 0:
            trial_status = 'ended'
        elif trial_days_remaining < 3:
            trial_status = 'ending_soon'
        else:
            trial_status = 'active'

        # Use user.name if available, otherwise extract from email
        display_name = user.name if user.name else (user.email.split('@')[0] if user.email else "Unknown")

        trial_users.append({
            "user_id": user.id,
            "email": user.email,
            "name": display_name,
            "account_id": user.account_id,
            "account_name": user.account_name or "Unknown",
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "trial_end_at": None,  # Will add when field exists
            "days_since_signup": days_since_signup,
            "trial_days_remaining": trial_days_remaining,
            "expected_emails": expected_emails,
            "trial_status": trial_status,
            "subscription_status": "unknown"  # Will add when field exists
        })

    # Filter to only active/ending soon trials (exclude ended)
    active_only = [u for u in trial_users if u['trial_status'] != 'ended']

    # Get summary stats
    total_trials = len(active_only)
    day_1_eligible = sum(1 for u in active_only if 'Day 1' in u['expected_emails'])
    day_3_eligible = sum(1 for u in active_only if 'Day 3' in u['expected_emails'])
    day_5_eligible = sum(1 for u in active_only if 'Day 5' in u['expected_emails'])
    day_7_eligible = sum(1 for u in active_only if 'Day 7' in u['expected_emails'])

    converted = 0  # Will calculate when subscription_status field exists
    ending_soon = sum(1 for u in active_only if u['trial_status'] == 'ending_soon')

    # Distribution by days since signup (active only)
    distribution = {}
    for user in active_only:
        days = user['days_since_signup']
        if days <= 2:
            key = '0-2 days'
        elif days <= 4:
            key = '3-4 days'
        elif days <= 7:
            key = '5-7 days'
        else:
            key = '8+ days'
        distribution[key] = distribution.get(key, 0) + 1

    return jsonify({
        "summary": {
            "total_active_trials": total_trials,
            "day_1_eligible": day_1_eligible,
            "day_3_eligible": day_3_eligible,
            "day_5_eligible": day_5_eligible,
            "day_7_eligible": day_7_eligible,
            "converted": converted,
            "ending_soon": ending_soon,
            "conversion_rate": round((converted / total_trials * 100) if total_trials > 0 else 0, 1)
        },
        "distribution": distribution,
        "users": active_only
    }), 200


@v1.route("/admin/trial/send-test", methods=["POST"])
@jwt_required()
def send_test_trial_email():
    """
    Send a test trial onboarding email.

    Body:
        user_id: User ID to send email to
        day: Which day email to send (1, 3, 5, or 7)

    Returns:
        Success message
    """
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    payload = request.get_json(silent=True) or {}
    user_id = payload.get("user_id")
    day = payload.get("day")

    if not user_id:
        return jsonify({"error": "user_id required"}), 400

    if day not in [1, 3, 5, 7]:
        return jsonify({"error": "day must be 1, 3, 5, or 7"}), 400

    # Verify user exists
    user = db.session.query(User).filter(User.id == user_id).first()
    if not user:
        return jsonify({"error": f"User {user_id} not found"}), 404

    try:
        from src.trial.onboarding import send_day_email

        result = send_day_email(user_id, day)

        if result.get("status") == "sent":
            return jsonify({
                "success": True,
                "message": f"Day {day} email sent to {user.email}",
                "user_id": user_id,
                "day": day
            }), 200
        else:
            return jsonify({
                "success": False,
                "error": result.get("reason", "Unknown error"),
                "message": f"Failed to send Day {day} email"
            }), 400

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
