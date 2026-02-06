"""
Funnel routes for dashboard and public pages
"""
from flask import render_template, Blueprint
from flask_jwt_extended import jwt_required

funnel_bp = Blueprint("funnel", __name__, url_prefix="/funnel")


@funnel_bp.route("/dashboard", methods=["GET"])
@jwt_required(optional=True)
def funnel_dashboard():
    """
    Display funnel analytics dashboard.

    Shows 5-stage funnel metrics, conversion rates, attribution, and velocity.
    """
    return render_template("funnel/dashboard.html")
