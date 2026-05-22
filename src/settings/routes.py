import os
import secrets
import requests as requests_lib
from datetime import datetime, timedelta
from uuid import uuid4

from flask import abort, current_app, flash, g, jsonify, redirect, render_template, request, url_for
from sqlalchemy import case, or_

from src.extensions import db, limiter
from src.models.auth import Passkey, TOTPDevice
from src.models.automation import WebhookProvider
from src.models.addons import AccountAddOn
from src.models.core import User, Account, InboxConnection, AccountLLMConfig, ALLOWED_LLM_PROVIDERS
from src.models.developer import RegisteredApp, DeveloperAccessRequest, AppProductAccess, AppWebhookDelivery
from src.developer.products import PRODUCT_CATALOG
from src.models.tickets import Ticket
from src.crypto import encrypt_value, decrypt_value
from src.api.v1.access_control import account_allows_api
from src.settings import bp, login_required_settings

def _is_staff_account(user) -> bool:
  """Return True only for Kalevent internal staff accounts."""
  if not user or not user.email:
    return False
  allowed = {
    e.strip().lower()
    for e in (current_app.config.get("ADMIN_EMAILS", "") or "kofi@kalevent.com").split(",")
    if e.strip()
  }
  return user.email.lower() in allowed


_TICKET_STATUSES = ["new", "open", "auto_handled", "optional", "needs_review",
                    "meeting_scheduled", "resolved", "closed"]
_TICKET_CATEGORIES = ["support", "transactional", "scheduling", "billing", "spam", "other"]
_TICKET_PRIORITIES = ["P0", "P1", "P2", "P3", "P4"]
_TICKETS_PAGE_SIZE = 25


def _build_ticket_query(account_id, q="", status="", category="", priority="", from_date="", to_date=""):
  """Return a scoped, filtered, sorted Ticket query for the given account."""
  query = Ticket.query.filter(Ticket.account_id == account_id)

  if q:
    search_filter = or_(
      Ticket.subject.ilike(f"%{q}%"),
      Ticket.from_email.ilike(f"%{q}%"),
    )
    try:
      search_filter = or_(
        search_filter,
        Ticket.search_vec.op("@@")(db.func.plainto_tsquery("english", q))
      )
    except Exception:
      pass
    query = query.filter(search_filter)
  if status and status in _TICKET_STATUSES:
    query = query.filter(Ticket.status == status)
  if category and category in _TICKET_CATEGORIES:
    query = query.filter(Ticket.category == category)
  if priority and priority in _TICKET_PRIORITIES:
    query = query.filter(Ticket.priority == priority)
  if from_date:
    try:
      query = query.filter(Ticket.created_at >= datetime.strptime(from_date, "%Y-%m-%d"))
    except ValueError:
      pass
  if to_date:
    try:
      dt = datetime.strptime(to_date, "%Y-%m-%d") + timedelta(days=1)
      query = query.filter(Ticket.created_at < dt)
    except ValueError:
      pass

  priority_order = case(
    (Ticket.priority == "P0", 0),
    (Ticket.priority == "P1", 1),
    (Ticket.priority == "P2", 2),
    (Ticket.priority == "P3", 3),
    (Ticket.priority == "P4", 4),
    else_=5,
  )
  return query.order_by(priority_order, Ticket.created_at.desc())


RBAC_DEFAULT_ROLES = [
  {
    "key": "owner",
    "label": "Owner",
    "description": "Full control including billing, security, and role delegation.",
    "permissions": [
      "Manage billing & seats",
      "Invite/remove users",
      "Connect and disconnect email inboxes",
      "Manage integrations and security",
      "View and respond to tickets",
      "Full access to Marketing Ops",
      "Create & edit automation rules",
    ],
  },
  {
    "key": "admin",
    "label": "Admin",
    "description": "Workspace configuration without billing authority.",
    "permissions": [
      "Manage users (except owners)",
      "Connect and disconnect email inboxes",
      "Manage integrations and security",
      "View and respond to tickets",
      "Full access to Marketing Ops",
      "Create, edit & delete automation rules",
    ],
  },
  {
    "key": "agent",
    "label": "Agent",
    "description": "Day-to-day support work with no access to billing, security, or marketing.",
    "permissions": [
      "View/triage/respond to tickets",
      "Create and edit macros",
      "View connected inboxes (cannot connect or disconnect)",
      "View integrations status",
      "View automation rules (read-only)",
      "No access to Marketing Ops",
    ],
  },
  {
    "key": "viewer",
    "label": "Viewer",
    "description": "Read-only access for audits or leadership.",
    "permissions": [
      "Read tickets and metrics",
      "View connected inboxes (no configuration access)",
      "No access to Marketing Ops or Automation Studio",
    ],
  },
  {
    "key": "billing",
    "label": "Billing-only",
    "description": "Finance-only access to invoices and seats, nothing else.",
    "permissions": [
      "Manage billing & invoices",
      "View seat usage",
      "No ticket, integration, or marketing access",
    ],
  },
]


@bp.get("/settings")
@bp.get("/settings/")
@login_required_settings
def settings_root():
  """Redirect bare /settings to the default tab."""
  return redirect(url_for("settings.settings_page", tab="team"))


@bp.post("/settings/profile")
@login_required_settings
def save_profile():
  current_user = getattr(g, "current_user", None)
  if not current_user:
    return redirect(url_for("settings.settings_page", tab="profile"))
  new_name = request.form.get("display_name", "").strip()
  if new_name:
    current_user.name = new_name
    try:
      db.session.commit()
      flash("Profile saved.", "success")
    except Exception:
      db.session.rollback()
      flash("Failed to save profile. Please try again.", "error")
  return redirect(url_for("settings.settings_page", tab="profile"))


@bp.get("/settings/<tab>")
@login_required_settings
def settings_page(tab):
  allowed = {"team", "profile", "billing", "security", "integrations", "features", "ai_provider", "developer", "tickets"}
  if tab not in allowed:
    tab = "team"
  passkeys = []
  totp_devices = []
  account_id = getattr(g, "current_account_id", None)
  account = Account.query.get(account_id) if account_id else None
  seats_used = User.query.filter_by(account_id=account_id).count() if account_id else 0
  seats_limit = account.seats_limit if account else None

  # Get current plan for billing tab
  plan_name = None
  if tab == "billing" and account_id:
    from src.models.billing import CustomerBillingProfile
    profile = CustomerBillingProfile.query.filter_by(account_id=account_id).first()
    plan_name = profile.plan_choice.capitalize() if profile and profile.plan_choice else None

  # Get BYOL LLM config for ai_provider tab
  llm_config = None
  if tab == "ai_provider" and account_id:
    llm_config = AccountLLMConfig.query.filter_by(account_id=account_id).first()

  # Get draft reply feature status and approval policies for features tab
  draft_reply_enabled = True
  feature_flags = None
  if tab in ("features", "integrations") and account_id:
    from src.models.core import AccountFeatureFlags

    feature_flags = AccountFeatureFlags.query.filter_by(account_id=account_id).first()
    draft_reply_enabled = feature_flags.draft_reply_enabled if feature_flags else True

  # Get CRM connection for integrations tab
  crm_connection = None
  crm_prefill = {}
  linkedin_connection = None
  twitter_connection = None
  facebook_connection = None
  gcal_connection = None
  outlook_cal_connection = None
  inbox_connections = []
  if tab == "integrations" and account_id:
    crm_connection = InboxConnection.query.filter_by(account_id=account_id, provider="crm").first()
    linkedin_connection = InboxConnection.query.filter_by(account_id=account_id, provider="linkedin_social").first()
    twitter_connection = InboxConnection.query.filter_by(account_id=account_id, provider="twitter_social").first()
    facebook_connection = InboxConnection.query.filter_by(account_id=account_id, provider="facebook_social").first()
    gcal_connection = InboxConnection.query.filter_by(account_id=account_id, provider="gcal").first()
    outlook_cal_connection = InboxConnection.query.filter_by(account_id=account_id, provider="outlook_cal").first()
    inbox_connections = InboxConnection.query.filter(
      InboxConnection.account_id == account_id,
      InboxConnection.provider.in_(["gmail", "outlook"]),
    ).order_by(InboxConnection.created_at.asc()).all()
    if crm_connection and crm_connection.metadata_json:
      meta = crm_connection.metadata_json
      crm_prefill = {
        "platform": meta.get("platform", ""),
        "instance_url": meta.get("instance_url", ""),
        "client_id": meta.get("client_id", ""),
        "hub_id": meta.get("hub_id", ""),
        "domain": meta.get("domain", ""),
        "sync_contacts": meta.get("sync_contacts", False),
        "sync_accounts": meta.get("sync_accounts", False),
        "sync_deals": meta.get("sync_deals", False),
      }

  current_user = getattr(g, "current_user", None)
  if tab == "security":
    if current_user:
      passkeys = Passkey.query.filter_by(user_id=current_user.id).all()
      totp_devices = TOTPDevice.query.filter_by(user_id=current_user.id).all()

  # Developer tab — only accessible if account has developer_access
  developer_access_request = None
  registered_apps = []
  selected_app = None
  product_accesses = {}
  if tab == "developer" and account_id:
    # Always load the access request so the landing page knows if one is pending
    developer_access_request = DeveloperAccessRequest.query.filter_by(
      account_id=account_id
    ).order_by(DeveloperAccessRequest.created_at.desc()).first()
    if account and account.developer_access:
      registered_apps = RegisteredApp.query.filter_by(
        account_id=account_id
      ).order_by(RegisteredApp.created_at.desc()).all()
      # Select app from query param or fall back to first
      app_id_param = request.args.get("app_id", "").strip()
      if app_id_param:
        selected_app = next((a for a in registered_apps if a.id == app_id_param), None)
      if selected_app is None and registered_apps:
        selected_app = registered_apps[0]
      # Load product accesses for the selected app
      if selected_app:
        accesses = AppProductAccess.query.filter_by(app_id=selected_app.id).all()
        product_accesses = {a.product_slug: a for a in accesses}

  mcp_servers = []
  if tab == "developer":
    from src.models.ai import MCPServerCatalog
    mcp_servers = MCPServerCatalog.query.filter_by(enabled=True).order_by(MCPServerCatalog.label.asc()).all()

  csrf_token_value = request.cookies.get("csrf_access_token") or request.cookies.get("csrf_refresh_token") or ""
  show_social_integrations = _is_staff_account(current_user)

  return render_template(
    "settings/index.html",
    active_tab=tab,
    security_view=None,
    team_view=None,
    billing_view=None,
    integrations_view=None,
    passkeys=passkeys,
    totp_devices=totp_devices,
    seats_used=seats_used,
    seats_limit=seats_limit,
    account_id=account_id,
    account=account,
    plan_name=plan_name,
    draft_reply_enabled=draft_reply_enabled,
    crm_connection=crm_connection,
    crm_prefill=crm_prefill,
    linkedin_connection=linkedin_connection,
    twitter_connection=twitter_connection,
    facebook_connection=facebook_connection,
    gcal_connection=gcal_connection,
    outlook_cal_connection=outlook_cal_connection,
    inbox_connections=inbox_connections,
    developer_access_request=developer_access_request,
    registered_apps=registered_apps,
    selected_app=selected_app,
    product_accesses=product_accesses,
    product_catalog=PRODUCT_CATALOG,
    mcp_servers=mcp_servers,
    developer_error=None,
    new_app=None,
    llm_config=llm_config,
    allowed_llm_providers=ALLOWED_LLM_PROVIDERS,
    current_user=current_user,
    csrf_token_value=csrf_token_value,
    feature_flags=feature_flags,
    show_social_integrations=show_social_integrations,
  )


@bp.get("/settings/security/passkeys")
@login_required_settings
def settings_passkeys():
  """Passkeys/security keys settings page (placeholder UI)."""
  user = getattr(g, "current_user", None)
  passkeys = Passkey.query.filter_by(user_id=user.id).all() if user else []
  totp_devices = TOTPDevice.query.filter_by(user_id=user.id).all() if user else []
  account_id = getattr(g, "current_account_id", None)
  return render_template(
    "settings/index.html",
    active_tab="security",
    security_view="passkeys",
    passkeys=passkeys,
    totp_devices=totp_devices,
    team_view=None,
    billing_view=None,
    integrations_view=None,
    account_id=account_id,
  )


@bp.get("/settings/security/password")
@login_required_settings
def settings_password():
  """Password/login management placeholder view."""
  user = getattr(g, "current_user", None)
  passkeys = Passkey.query.filter_by(user_id=user.id).all() if user else []
  totp_devices = TOTPDevice.query.filter_by(user_id=user.id).all() if user else []
  account_id = getattr(g, "current_account_id", None)
  return render_template(
    "settings/index.html",
    active_tab="security",
    security_view="password",
    passkeys=passkeys,
    totp_devices=totp_devices,
    team_view=None,
    billing_view=None,
    integrations_view=None,
    account_id=account_id,
  )


@bp.get("/settings/security/audit")
@login_required_settings
def settings_audit():
  """Audit log placeholder view."""
  user = getattr(g, "current_user", None)
  passkeys = Passkey.query.filter_by(user_id=user.id).all() if user else []
  totp_devices = TOTPDevice.query.filter_by(user_id=user.id).all() if user else []
  account_id = getattr(g, "current_account_id", None)
  return render_template(
    "settings/index.html",
    active_tab="security",
    security_view="audit",
    passkeys=passkeys,
    totp_devices=totp_devices,
    team_view=None,
    billing_view=None,
    integrations_view=None,
    account_id=account_id,
  )


@bp.get("/settings/security/2fa")
@login_required_settings
def settings_2fa():
  """2FA placeholder view."""
  user = getattr(g, "current_user", None)
  passkeys = Passkey.query.filter_by(user_id=user.id).all() if user else []
  totp_devices = TOTPDevice.query.filter_by(user_id=user.id).all() if user else []
  account_id = getattr(g, "current_account_id", None)
  return render_template(
    "settings/index.html",
    active_tab="security",
    security_view="2fa",
    passkeys=passkeys,
    totp_devices=totp_devices,
    team_view=None,
    billing_view=None,
    integrations_view=None,
    account_id=account_id,
  )


@bp.get("/settings/team/invite")
@login_required_settings
def team_invite_page():
  account_id = getattr(g, "current_account_id", None)
  return render_template(
    "settings/index.html",
    active_tab="team",
    team_view="invite",
    security_view=None,
    billing_view=None,
    integrations_view=None,
    account_id=account_id,
  )


_VALID_ROLES = {"owner", "admin", "agent", "viewer", "billing"}


def _resolved_assignments(members):
  """Read role assignments from DB, defaulting first member to owner.

  If no member has an explicit owner role (e.g. after the role column
  migration that set server_default='agent' for all existing rows), the
  first member is promoted to owner and the assignment is persisted so
  all role checks work correctly on subsequent requests.
  """
  assignments = {}
  for idx, member in enumerate(members):
    role = getattr(member, "role", None)
    if role not in _VALID_ROLES:
      role = "owner" if idx == 0 else "agent"
    assignments[str(member.id)] = role
  if members and "owner" not in assignments.values():
    assignments[str(members[0].id)] = "owner"
    # Persist the resolved owner so the DB reflects reality going forward.
    _save_assignments(members[0].account_id, assignments)
  return assignments


def _save_assignments(account_id, assignments):
  """Write role assignments to DB."""
  for user_id_str, role in assignments.items():
    if role not in _VALID_ROLES:
      continue
    user = db.session.get(User, int(user_id_str))
    if user and user.account_id == account_id:
      user.role = role
  db.session.commit()
  return assignments


def _serialize_members(members, assignments):
  payload = []
  for member in members:
    role_key = assignments.get(str(member.id), "agent")
    payload.append(
      {
        "id": member.id,
        "email": member.email,
        "role": role_key,
        "created_at": member.created_at.isoformat() if getattr(member, "created_at", None) else None,
      }
    )
  return payload


@bp.route("/settings/billing/plan", methods=["GET", "POST"])
@login_required_settings
def billing_plan():
  """Billing plan view and update."""
  account_id = getattr(g, "current_account_id", None)
  account = Account.query.get(account_id) if account_id else None
  seats_used = User.query.filter_by(account_id=account_id).count() if account_id else 0
  seats_limit = account.seats_limit if account else None

  # Get current plan from billing profile
  from src.models.billing import CustomerBillingProfile
  profile = CustomerBillingProfile.query.filter_by(account_id=account_id).first() if account_id else None
  current_plan = profile.plan_choice if profile else None

  plan_change_message = None
  plan_change_status = None

  if request.method == "POST":
    new_plan = request.form.get("plan_choice")

    if new_plan not in ["pro", "business"]:
      plan_change_message = "Invalid plan selected"
      plan_change_status = "error"
    else:
      # Check if account is allowed to change plans without payment
      from src.api.v1.access_control import _parse_id_set
      import os
      exempt_ids = _parse_id_set(os.getenv("API_EXEMPT_ACCOUNT_IDS", ""))
      has_stripe_subscription = profile and profile.subscription_status in ("active", "trialing") if profile else False
      is_exempt = account_id in exempt_ids

      # Only allow plan changes for:
      # 1. Exempt/internal accounts (no payment required)
      # 2. Accounts with active Stripe subscriptions
      if not (is_exempt or has_stripe_subscription):
        plan_change_message = "Plan changes require an active subscription. Please contact sales or set up billing."
        plan_change_status = "error"
      elif not profile:
        # Create billing profile if it doesn't exist
        profile = CustomerBillingProfile(
          account_id=account_id,
          email=getattr(g, "current_user", None).email if hasattr(g, "current_user") else "",
          plan_choice=new_plan,
          trial_status="ended",
        )
        db.session.add(profile)
        db.session.commit()
        plan_change_message = f"Plan updated to {new_plan.capitalize()}. Changes take effect immediately."
        plan_change_status = "success"
        current_plan = new_plan
      else:
        # Update existing profile
        old_plan = profile.plan_choice
        profile.plan_choice = new_plan
        db.session.commit()

        if old_plan == new_plan:
          plan_change_message = f"You're already on the {new_plan.capitalize()} plan."
          plan_change_status = "info"
        else:
          plan_change_message = f"Plan changed from {old_plan.capitalize()} to {new_plan.capitalize()}. Changes take effect immediately."
          plan_change_status = "success"
        current_plan = new_plan

  # Get CSRF token from cookies for the form
  csrf_token_value = request.cookies.get("csrf_access_token") or request.cookies.get("csrf_refresh_token") or ""

  return render_template(
    "settings/index.html",
    active_tab="billing",
    billing_view="plan",
    team_view=None,
    security_view=None,
    integrations_view=None,
    seats_used=seats_used,
    seats_limit=seats_limit,
    account_id=account_id,
    current_plan=current_plan,
    plan_change_message=plan_change_message,
    plan_change_status=plan_change_status,
    csrf_token_value=csrf_token_value,
  )


@bp.get("/settings/billing/invoices")
@login_required_settings
def billing_invoices():
  """Billing invoices placeholder view."""
  account_id = getattr(g, "current_account_id", None)
  account = Account.query.get(account_id) if account_id else None
  seats_used = User.query.filter_by(account_id=account_id).count() if account_id else 0
  seats_limit = account.seats_limit if account else None
  return render_template(
    "settings/index.html",
    active_tab="billing",
    billing_view="invoices",
    team_view=None,
    security_view=None,
    integrations_view=None,
    seats_used=seats_used,
    seats_limit=seats_limit,
    account_id=account_id,
  )


@bp.get("/settings/team/roles")
@login_required_settings
def team_roles_page():
  account_id = getattr(g, "current_account_id", None)
  if not account_id:
    return redirect(url_for("dashboard_home"))
  members = User.query.filter_by(account_id=account_id).order_by(User.created_at.asc()).all()
  assignments = _resolved_assignments(members)
  member_payload = _serialize_members(members, assignments)
  return render_template(
    "settings/index.html",
    active_tab="team",
    team_view="roles",
    billing_view=None,
    security_view=None,
    integrations_view=None,
    roles=RBAC_DEFAULT_ROLES,
    members=member_payload,
  )


@bp.get("/api/roles")
@bp.get("/settings/api/roles")
@login_required_settings
def api_roles():
  account_id = getattr(g, "current_account_id", None)
  if not account_id:
    return jsonify({"error": "account not found"}), 404
  members = User.query.filter_by(account_id=account_id).order_by(User.created_at.asc()).all()
  assignments = _resolved_assignments(members)
  return jsonify(
    {
      "roles": RBAC_DEFAULT_ROLES,
      "members": _serialize_members(members, assignments),
    }
  )


@bp.post("/api/roles/assignments")
@bp.post("/settings/api/roles/assignments")
@login_required_settings
def api_update_role():
  account_id = getattr(g, "current_account_id", None)
  user = getattr(g, "current_user", None)
  if not account_id or not user:
    return jsonify({"error": "account not found"}), 404

  data = request.get_json(silent=True) or {}
  role_key = (data.get("role") or "").strip().lower()
  user_id = data.get("user_id")
  if role_key not in {r["key"] for r in RBAC_DEFAULT_ROLES}:
    return jsonify({"error": "invalid role"}), 400
  try:
    user_id_int = int(user_id)
  except (TypeError, ValueError):
    return jsonify({"error": "user_id must be an integer"}), 400

  members = User.query.filter_by(account_id=account_id).order_by(User.created_at.asc()).all()
  target = next((m for m in members if m.id == user_id_int), None)
  if not target:
    return jsonify({"error": "user not found for this account"}), 404

  assignments = _resolved_assignments(members)
  caller_role = assignments.get(str(user.id))
  if caller_role not in {"owner", "admin"}:
    return jsonify({"error": "insufficient permissions"}), 403

  old_role = assignments.get(str(target.id))
  assignments[str(target.id)] = role_key
  if "owner" not in assignments.values():
    return jsonify({"error": "at least one owner is required"}), 400

  _save_assignments(account_id, assignments)
  from src.security import log_audit
  log_audit("user.role_changed", resource_type="user", resource_id=str(target.id),
            metadata={"old_role": old_role, "new_role": role_key, "changed_by": user.id})
  return jsonify(
    {
      "user_id": target.id,
      "role": role_key,
      "assignments": assignments,
      "members": _serialize_members(members, assignments),
    }
  ), 200


# Legacy redirects to avoid breaking existing links.
@bp.get("/team/invite")
def _legacy_invite_redirect():
  return redirect(url_for("settings.team_invite_page"), code=302)


@bp.get("/team/roles")
def _legacy_roles_page_redirect():
  return redirect(url_for("settings.team_roles_page"), code=302)


@bp.get("/setting")
@bp.get("/setting/<tab>")
def _legacy_settings_redirect(tab="team"):
  return redirect(url_for("settings.settings_page", tab=tab or "team"))


@bp.get("/settings/activity")
@login_required_settings
def activity_log_page():
  account_id = getattr(g, "current_account_id", None)
  return render_template("settings/activity_log.html", account_id=account_id)


@bp.get("/settings/tickets")
@login_required_settings
def tickets_list():
  account_id = getattr(g, "current_account_id", None)
  if not account_id:
    return redirect(url_for("settings.settings_page", tab="team"))

  q = request.args.get("q", "").strip()
  status = request.args.get("status", "").strip()
  category = request.args.get("category", "").strip()
  priority = request.args.get("priority", "").strip()
  from_date = request.args.get("from", "").strip()
  to_date = request.args.get("to", "").strip()

  try:
    page = max(1, int(request.args.get("page", 1) or 1))
  except (ValueError, TypeError):
    page = 1

  ticket_q = _build_ticket_query(account_id, q, status, category, priority, from_date, to_date)
  total = ticket_q.count()
  tickets = ticket_q.offset((page - 1) * _TICKETS_PAGE_SIZE).limit(_TICKETS_PAGE_SIZE).all()
  total_pages = max(1, (total + _TICKETS_PAGE_SIZE - 1) // _TICKETS_PAGE_SIZE)

  return render_template(
    "settings/tickets_list.html",
    tickets=tickets,
    page=page,
    total=total,
    total_pages=total_pages,
    page_size=_TICKETS_PAGE_SIZE,
    q=q,
    filter_status=status,
    filter_category=category,
    filter_priority=priority,
    filter_from=from_date,
    filter_to=to_date,
    statuses=_TICKET_STATUSES,
    categories=_TICKET_CATEGORIES,
    priorities=_TICKET_PRIORITIES,
    active_tab="tickets",
  )


@bp.get("/settings/tickets/<ticket_id>")
@login_required_settings
def tickets_detail(ticket_id):
  account_id = getattr(g, "current_account_id", None)
  current_user = getattr(g, "current_user", None)
  if not account_id:
    return redirect(url_for("settings.settings_page", tab="team"))

  ticket = Ticket.query.filter_by(id=ticket_id, account_id=account_id).first()
  if not ticket:
    abort(404)

  _raw_back = request.args.get("back", "")
  if _raw_back.startswith("/") and not _raw_back.startswith("//"):
      back_url = _raw_back
  else:
      back_url = url_for("settings.tickets_list")
  is_staff = _is_staff_account(current_user)

  return render_template(
    "settings/tickets_detail.html",
    ticket=ticket,
    back_url=back_url,
    is_staff=is_staff,
    active_tab="tickets",
  )


@bp.post("/settings/tickets/<ticket_id>/resolve")
@login_required_settings
def tickets_resolve(ticket_id):
  account_id = getattr(g, "current_account_id", None)
  ticket = Ticket.query.filter_by(id=ticket_id, account_id=account_id).first()
  if not ticket:
    abort(404)

  if ticket.status in ("resolved", "closed"):
    flash(f"Ticket is already {ticket.status}.", "info")
    return redirect(url_for("settings.tickets_detail", ticket_id=ticket_id))

  ticket.status = "resolved"
  try:
    db.session.commit()
    flash("Ticket marked as resolved.", "success")
  except Exception:
    db.session.rollback()
    flash("Failed to update ticket. Please try again.", "error")

  return redirect(url_for("settings.tickets_detail", ticket_id=ticket_id))


@bp.post("/settings/tickets/<ticket_id>/close")
@login_required_settings
def tickets_close(ticket_id):
  account_id = getattr(g, "current_account_id", None)
  ticket = Ticket.query.filter_by(id=ticket_id, account_id=account_id).first()
  if not ticket:
    abort(404)

  if ticket.status in ("resolved", "closed"):
    flash(f"Ticket is already {ticket.status}.", "info")
    return redirect(url_for("settings.tickets_detail", ticket_id=ticket_id))

  ticket.status = "closed"
  try:
    db.session.commit()
    flash("Ticket closed.", "success")
  except Exception:
    db.session.rollback()
    flash("Failed to update ticket. Please try again.", "error")

  return redirect(url_for("settings.tickets_detail", ticket_id=ticket_id))


@bp.post("/settings/account/delete")
@login_required_settings
@limiter.limit("3 per hour")
def account_delete():
  """
  Soft-delete the account. Owner-only. Writes an AuditLog row before marking
  deleted_at, so the record survives even if something goes wrong afterward.
  The account is not hard-deleted here — a scheduled job purges after 30 days.
  """
  from datetime import timezone
  from src.models.auth import AuditLog

  account_id = getattr(g, "current_account_id", None)
  user = getattr(g, "current_user", None)
  if not account_id or not user:
    return jsonify({"error": "Unauthorized"}), 401

  if user.role != "owner":
    return jsonify({"error": "Only the account owner can delete this account."}), 403

  account = db.session.get(Account, account_id)
  if not account or account.is_deleted:
    return jsonify({"error": "Account not found."}), 404

  confirmation = (request.json or {}).get("confirm_name", "").strip()
  if confirmation != account.name:
    return jsonify({"error": "Account name does not match. Type the account name exactly to confirm."}), 422

  # Write audit log before mutating — immutable record survives the deletion
  log = AuditLog(
    account_id=account_id,
    user_id=user.id,
    action="account.deleted",
    resource_type="account",
    resource_id=str(account_id),
    ip_address=request.remote_addr,
    user_agent=(request.user_agent.string or "")[:300],
    metadata_json={
      "account_name": account.name,
      "initiated_by_email": user.email,
      "reason": (request.json or {}).get("reason", ""),
    },
  )
  db.session.add(log)

  account.deleted_at = datetime.now(timezone.utc)
  db.session.commit()

  current_app.logger.warning({
    "event": "account.deleted",
    "account_id": account_id,
    "account_name": account.name,
    "user_id": user.id,
    "ip": request.remote_addr,
  })

  return jsonify({"ok": True, "message": "Account scheduled for deletion. Data will be permanently removed in 30 days."}), 200


@bp.post("/integrations/booking-duration")
@login_required_settings
def save_booking_duration():
    from src.models.core import AccountFeatureFlags
    account_id = getattr(g, "current_account_id", None)
    if not account_id:
        return redirect(url_for("settings.settings_page", tab="integrations"))

    raw = request.form.get("booking_duration_minutes", "30")
    try:
        duration = int(raw)
        if duration not in (15, 30, 45, 60):
            duration = 30
    except (ValueError, TypeError):
        duration = 30

    try:
        flags = AccountFeatureFlags.query.filter_by(account_id=account_id).first()
        if not flags:
            flags = AccountFeatureFlags(account_id=account_id)
            db.session.add(flags)
        flags.booking_duration_minutes = duration
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.error("Failed to save booking_duration_minutes account=%s", account_id)

    return redirect(url_for("settings.settings_page", tab="integrations"))


@bp.post("/integrations/generate-booking-link")
@login_required_settings
def generate_booking_link():
    """Generate a permanent InboxIQ booking page URL for this account."""
    import re
    from src.models.core import AccountFeatureFlags, InboxConnection
    account_id = getattr(g, "current_account_id", None)
    if not account_id:
        return redirect(url_for("settings.settings_page", tab="integrations"))

    has_calendar = InboxConnection.query.filter(
        InboxConnection.account_id == account_id,
        InboxConnection.provider.in_(("gcal", "outlook_cal")),
        InboxConnection.status == "connected",
    ).first()
    if not has_calendar:
        flash(
            "Connect your Google Calendar or Outlook Calendar first — "
            "InboxIQ needs a calendar to show your availability.",
            "error",
        )
        return redirect(url_for("settings.settings_page", tab="integrations"))

    handle = request.form.get("handle", "").strip().lower()
    if not handle or not re.match(r'^[a-z0-9][a-z0-9\-]{1,38}[a-z0-9]$', handle):
        flash("Handle must be 3–40 characters, letters, numbers and hyphens only, and cannot start or end with a hyphen.", "error")
        return redirect(url_for("settings.settings_page", tab="integrations"))

    existing = AccountFeatureFlags.query.filter_by(booking_handle=handle).first()
    if existing and existing.account_id != account_id:
        flash("That handle is already taken. Please choose another.", "error")
        return redirect(url_for("settings.settings_page", tab="integrations"))

    base_url = current_app.config.get("APP_BASE_URL", "https://kalevent.com")
    try:
        flags = AccountFeatureFlags.query.filter_by(account_id=account_id).first()
        if not flags:
            flags = AccountFeatureFlags(account_id=account_id)
            db.session.add(flags)
        flags.booking_handle = handle
        flags.static_booking_url = f"{base_url}/book/me/{handle}"
        db.session.commit()
        flash("Your booking link has been generated.", "success")
    except Exception:
        db.session.rollback()
        current_app.logger.error("Failed to generate booking link account=%s", account_id)
        flash("Failed to generate booking link. Please try again.", "error")

    return redirect(url_for("settings.settings_page", tab="integrations"))


@bp.post("/integrations/static-booking-url")
@login_required_settings
def save_static_booking_url():
    """Manual override — power users can supply a custom InboxIQ-compatible booking URL."""
    from src.models.core import AccountFeatureFlags
    account_id = getattr(g, "current_account_id", None)
    if not account_id:
        return redirect(url_for("settings.settings_page", tab="integrations"))

    raw = (request.form.get("static_booking_url") or "").strip()

    if raw and not raw.startswith(("http://", "https://")):
        flash("Please enter a valid URL starting with https://", "error")
        return redirect(url_for("settings.settings_page", tab="integrations"))

    try:
        flags = AccountFeatureFlags.query.filter_by(account_id=account_id).first()
        if not flags:
            flags = AccountFeatureFlags(account_id=account_id)
            db.session.add(flags)
        flags.static_booking_url = raw or None
        db.session.commit()
        if raw:
            flash("Booking URL updated.", "success")
    except Exception:
        db.session.rollback()
        current_app.logger.error("Failed to save static_booking_url account=%s", account_id)
        flash("Failed to update booking URL. Please try again.", "error")

    return redirect(url_for("settings.settings_page", tab="integrations"))


@bp.route("/integrations/social/disconnect", methods=["POST"])
@login_required_settings
def integrations_social_disconnect():
    """Disconnect a LinkedIn or Twitter social CRM connection."""
    from src.models import InboxConnection
    account_id = getattr(g, "current_account_id", None)
    provider = request.form.get("provider", "").strip()
    if provider not in ("linkedin_social", "twitter_social", "facebook_social", "gcal", "outlook_cal") or not account_id:
        return redirect(url_for("settings.settings_page", tab="integrations"))

    conn = InboxConnection.query.filter_by(account_id=account_id, provider=provider).first()
    if conn:
        from src.extensions import db
        conn_id = str(conn.id)
        conn_provider = conn.provider
        db.session.delete(conn)
        db.session.commit()
        from src.security import log_audit
        log_audit("inbox.disconnected", resource_type="inbox_connection", resource_id=conn_id,
                  metadata={"provider": conn_provider})

    return redirect(url_for("settings.settings_page", tab="integrations"))


@bp.route("/integrations/inbox/toggle-gmail-filters", methods=["POST"])
@login_required_settings
def inbox_toggle_gmail_filters():
    """Toggle 'Sync learned filters to Gmail' for a Gmail inbox connection."""
    from src.models import InboxConnection
    from src.extensions import db
    account_id = getattr(g, "current_account_id", None)
    user = getattr(g, "current_user", None)
    if not user or getattr(user, "role", None) not in ("owner", "admin"):
        return redirect(url_for("settings.settings_page", tab="integrations"))
    connection_id = request.form.get("connection_id", "").strip()
    if not account_id or not connection_id:
        return redirect(url_for("settings.settings_page", tab="integrations"))

    conn = InboxConnection.query.filter_by(
        id=connection_id, account_id=account_id, provider="gmail"
    ).first()
    if conn:
        meta = dict(conn.metadata_json or {})
        enabled = not meta.get("sync_gmail_filters", False)
        meta["sync_gmail_filters"] = enabled
        conn.metadata_json = meta
        db.session.commit()
        if enabled:
            try:
                from src.inbox.tasks import sync_gmail_filters_task
                sync_gmail_filters_task.delay(connection_id)
            except Exception:
                pass

    return redirect(url_for("settings.settings_page", tab="integrations"))


@bp.route("/integrations/inbox/toggle-outlook-rules", methods=["POST"])
@login_required_settings
def inbox_toggle_outlook_rules():
    """Toggle 'Sync learned rules to Outlook' for an Outlook inbox connection."""
    from src.models import InboxConnection
    from src.extensions import db
    account_id = getattr(g, "current_account_id", None)
    user = getattr(g, "current_user", None)
    if not user or getattr(user, "role", None) not in ("owner", "admin"):
        return redirect(url_for("settings.settings_page", tab="integrations"))
    connection_id = request.form.get("connection_id", "").strip()
    if not account_id or not connection_id:
        return redirect(url_for("settings.settings_page", tab="integrations"))

    conn = InboxConnection.query.filter_by(
        id=connection_id, account_id=account_id, provider="outlook"
    ).first()
    if conn:
        meta = dict(conn.metadata_json or {})
        enabled = not meta.get("sync_outlook_rules", False)
        meta["sync_outlook_rules"] = enabled
        conn.metadata_json = meta
        db.session.commit()
        if enabled:
            try:
                from src.inbox.tasks import sync_outlook_rules_task
                sync_outlook_rules_task.delay(connection_id)
            except Exception:
                pass

    return redirect(url_for("settings.settings_page", tab="integrations"))


@bp.route("/integrations/inbox/disconnect", methods=["POST"])
@login_required_settings
def inbox_disconnect():
    """Disconnect a Gmail or Outlook inbox connection. Owner/admin only."""
    from src.models import InboxConnection
    account_id = getattr(g, "current_account_id", None)
    user = getattr(g, "current_user", None)
    if not user or getattr(user, "role", None) not in ("owner", "admin"):
        return redirect(url_for("settings.settings_page", tab="integrations"))
    connection_id = request.form.get("connection_id", "").strip()
    if not account_id or not connection_id:
        return redirect(url_for("settings.settings_page", tab="integrations"))

    conn = InboxConnection.query.filter_by(id=connection_id, account_id=account_id).first()
    if conn and conn.provider in ("gmail", "outlook"):
        from src.extensions import db
        conn_id = str(conn.id)
        conn_provider = conn.provider
        db.session.delete(conn)
        db.session.commit()
        from src.security import log_audit
        log_audit("inbox.disconnected", resource_type="inbox_connection", resource_id=conn_id,
                  metadata={"provider": conn_provider})

    return redirect(url_for("settings.settings_page", tab="integrations"))


@bp.route("/integrations/webhooks", methods=["GET", "POST"])
@login_required_settings
@limiter.limit("20 per minute", methods=["POST"])  # Rate limit: 20 provider configurations per minute
def integrations_webhooks():
  user = getattr(g, "current_user", None)
  account_id = getattr(g, "current_account_id", None)
  api_allowed = account_allows_api(account_id) if account_id else False
  show_social_integrations = _is_staff_account(user)
  crm_connection = None
  crm_prefill = {}
  linkedin_connection = None
  twitter_connection = None
  facebook_connection = None
  gcal_connection = None
  outlook_cal_connection = None
  if account_id:
    # Load CRM connection data
    crm_connection = InboxConnection.query.filter_by(account_id=account_id, provider="crm").first()
    if crm_connection and crm_connection.metadata_json:
      meta = crm_connection.metadata_json
      crm_prefill = {
        "platform": meta.get("platform", ""),
        "instance_url": meta.get("instance_url", ""),
        "client_id": meta.get("client_id", ""),
        "hub_id": meta.get("hub_id", ""),
        "domain": meta.get("domain", ""),
        "sync_contacts": meta.get("sync_contacts", False),
        "sync_accounts": meta.get("sync_accounts", False),
        "sync_deals": meta.get("sync_deals", False),
      }
    linkedin_connection = InboxConnection.query.filter_by(account_id=account_id, provider="linkedin_social").first()
    twitter_connection = InboxConnection.query.filter_by(account_id=account_id, provider="twitter_social").first()
    facebook_connection = InboxConnection.query.filter_by(account_id=account_id, provider="facebook_social").first()
    gcal_connection = InboxConnection.query.filter_by(account_id=account_id, provider="gcal").first()
    outlook_cal_connection = InboxConnection.query.filter_by(account_id=account_id, provider="outlook_cal").first()
  if request.method == "POST":
    action = (request.form.get("action") or "").strip()
    label = (request.form.get("label") or "").strip() or None
    allowed_ips_raw = (request.form.get("allowed_ips") or "").strip()
    allowed_ips = [ip.strip() for ip in allowed_ips_raw.split(",") if ip.strip()] if allowed_ips_raw else []
    expires_raw = (request.form.get("expires_at") or "").strip()
    expires_at = None
    if expires_raw:
      try:
        expires_at = datetime.fromisoformat(expires_raw)
      except Exception:
        expires_at = None

    if action == "save_crm" and account_id:
      platform = (request.form.get("crm_platform") or "").strip().lower()

      # Platform-specific fields
      instance_url = (request.form.get("crm_instance_url") or "").strip()
      client_id = (request.form.get("crm_client_id") or "").strip()
      client_secret = (request.form.get("crm_client_secret") or "").strip()
      access_token = (request.form.get("crm_access_token") or "").strip()
      api_key = (request.form.get("crm_api_key") or "").strip()
      hub_id = (request.form.get("crm_hub_id") or "").strip()
      domain = (request.form.get("crm_domain") or "").strip()

      # Sync settings
      sync_contacts = request.form.get("crm_sync_contacts") == "on"
      sync_accounts = request.form.get("crm_sync_accounts") == "on"
      sync_deals = request.form.get("crm_sync_deals") == "on"

      if not platform:
        return render_template(
          "settings/index.html",
          active_tab="integrations",
          integrations_view="webhooks",
          team_view=None,
          billing_view=None,
          security_view=None,
          api_allowed=api_allowed,
          account_id=account_id,
          crm_connection=crm_connection,
          crm_prefill=crm_prefill,
          show_social_integrations=show_social_integrations,
        )

      status = "connected" if (api_key or access_token or client_secret) else "pending"

      # Check if CRM connection already exists
      crm_connection = InboxConnection.query.filter_by(account_id=account_id, provider="crm").first()

      metadata = (crm_connection.metadata_json or {}) if crm_connection else {}
      metadata.update(
        {
          "channel": "crm",
          "platform": platform,
          "sync_contacts": sync_contacts,
          "sync_accounts": sync_accounts,
          "sync_deals": sync_deals,
        }
      )

      # Encrypt credentials based on platform
      if platform == "salesforce":
        if instance_url:
          metadata["instance_url"] = instance_url
        if client_id:
          metadata["client_id"] = client_id
        if client_secret:
          metadata["client_secret_enc"] = encrypt_value(client_secret)
          metadata.pop("client_secret", None)
        if access_token:
          metadata["access_token_enc"] = encrypt_value(access_token)
          metadata.pop("access_token", None)
      elif platform == "hubspot":
        if api_key:
          metadata["api_key_enc"] = encrypt_value(api_key)
          metadata.pop("api_key", None)
        if hub_id:
          metadata["hub_id"] = hub_id
      elif platform == "pipedrive":
        if api_key:
          metadata["api_key_enc"] = encrypt_value(api_key)
          metadata.pop("api_key", None)
        if domain:
          metadata["domain"] = domain

      if crm_connection:
        crm_connection.metadata_json = metadata
        crm_connection.status = status
      else:
        crm_connection = InboxConnection(
          user_id=user.id if user else None,
          account_id=account_id,
          provider="crm",
          status=status,
          metadata_json=metadata,
        )
        db.session.add(crm_connection)
      db.session.commit()

      return render_template(
        "settings/index.html",
        active_tab="integrations",
        integrations_view=None,
        team_view=None,
        billing_view=None,
        security_view=None,
        api_allowed=api_allowed,
        account_id=account_id,
        crm_connection=crm_connection,
        crm_saved=True,
        linkedin_connection=linkedin_connection,
        twitter_connection=twitter_connection,
        facebook_connection=facebook_connection,
        gcal_connection=gcal_connection,
        outlook_cal_connection=outlook_cal_connection,
        show_social_integrations=show_social_integrations,
      )
    if action == "add_provider" and account_id:
      import re
      import json
      from urllib.parse import urlparse
      from src.sanitize import sanitize_html

      provider = (request.form.get("provider") or "").strip()

      # Validate provider against whitelist (prevent injection)
      allowed_providers = ['sage', 'quickbooks', 'slack', 'teams', 'custom', 'stripe', 'square', 'paypal']
      if not provider or provider not in allowed_providers:
        return render_template(
          "settings/index.html",
          active_tab="integrations",
          integrations_view="webhooks",
          team_view=None,
          billing_view=None,
          security_view=None,
          api_allowed=api_allowed,
          account_id=account_id,
          crm_connection=crm_connection,
          crm_prefill=crm_prefill,
          webhook_providers=WebhookProvider.query.filter_by(account_id=account_id).order_by(WebhookProvider.created_at.desc()).all(),
        )

      # Collect form fields into credentials dict with validation
      credentials = {}
      configuration_name = None
      environment = 'production'

      for key in request.form:
        if key not in ['action', 'provider']:
          value = request.form.get(key, '').strip()

          # Input validation and sanitization
          if key == 'label':
            # Sanitize label (remove HTML, limit length)
            value = sanitize_html(value)
            value = re.sub(r'<[^>]*>', '', value)  # Strip all HTML tags
            value = value[:100]  # Max 100 chars
            configuration_name = value or f"{provider.title()} Integration"
            continue  # Don't store in credentials

          elif key == 'environment':
            environment = value if value in ['production', 'sandbox'] else 'production'
            continue  # Don't store in credentials

          elif key in ['endpoint_url', 'webhook_url']:
            # Validate URLs (prevent javascript:, data:, vbscript: protocols)
            if value:
              try:
                parsed = urlparse(value)
                # Only allow http and https protocols
                if parsed.scheme not in ['http', 'https', '']:
                  current_app.logger.warning(f"Blocked unsafe URL protocol: {parsed.scheme}")
                  continue  # Skip this field
                # Limit URL length
                value = value[:2000]
              except Exception as e:
                current_app.logger.warning(f"Invalid URL provided: {value}")
                continue  # Skip invalid URLs

          elif key == 'channel':
            # Validate Slack channel format (#channel-name)
            if value and not re.match(r'^#?[a-z0-9_-]{1,80}$', value, re.I):
              current_app.logger.warning(f"Invalid channel format: {value}")
              value = re.sub(r'[^a-z0-9_-]', '', value.lower())[:80]

          elif key in ['company_id', 'client_id', 'environment']:
            # Alphanumeric + basic chars only, max 255 chars
            value = re.sub(r'[^\w\s.-]', '', value)[:255]

          # Store all fields in credentials (will be encrypted as a whole)
          if value:
            credentials[key] = value

      if not configuration_name:
        configuration_name = f"{provider.title()} Integration"

      # Encrypt the entire credentials object
      credentials_json = json.dumps(credentials)
      credentials_encrypted = encrypt_value(credentials_json)

      # Check if provider already exists for this account
      existing_provider = WebhookProvider.query.filter_by(
        account_id=account_id,
        provider_type=provider
      ).first()

      if existing_provider:
        # Update existing provider
        existing_provider.configuration_name = configuration_name
        existing_provider.environment = environment
        existing_provider.credentials_encrypted = credentials_encrypted
        existing_provider.enabled = True

        # Update webhook signing secrets for source providers
        if 'webhook_secret' in credentials:
          existing_provider.webhook_signing_secret_encrypted = encrypt_value(credentials['webhook_secret'])
        if 'webhook_signature_key' in credentials:
          existing_provider.webhook_signing_secret_encrypted = encrypt_value(credentials['webhook_signature_key'])

        # Update API keys
        if 'api_key' in credentials:
          existing_provider.api_key_encrypted = encrypt_value(credentials['api_key'])
        if 'access_token' in credentials:
          existing_provider.api_key_encrypted = encrypt_value(credentials['access_token'])
      else:
        # Create new provider
        new_provider = WebhookProvider(
          id=str(uuid4()),
          account_id=account_id,
          provider_type=provider,
          configuration_name=configuration_name,
          environment=environment,
          credentials_encrypted=credentials_encrypted,
          enabled=True,
        )

        # Handle webhook signing secrets for source providers
        if 'webhook_secret' in credentials:
          new_provider.webhook_signing_secret_encrypted = encrypt_value(credentials['webhook_secret'])
        if 'webhook_signature_key' in credentials:
          new_provider.webhook_signing_secret_encrypted = encrypt_value(credentials['webhook_signature_key'])

        # Handle API keys
        if 'api_key' in credentials:
          new_provider.api_key_encrypted = encrypt_value(credentials['api_key'])
        if 'access_token' in credentials:
          new_provider.api_key_encrypted = encrypt_value(credentials['access_token'])

        db.session.add(new_provider)

      db.session.commit()

      return render_template(
        "settings/index.html",
        active_tab="integrations",
        integrations_view="webhooks",
        team_view=None,
        billing_view=None,
        security_view=None,
        api_allowed=api_allowed,
        account_id=account_id,
        crm_connection=crm_connection,
        crm_prefill=crm_prefill,
        webhook_providers=WebhookProvider.query.filter_by(account_id=account_id).order_by(WebhookProvider.created_at.desc()).all(),
        provider_saved=True,
      )

    if action == "delete_provider" and account_id:
      provider_id = request.form.get("provider_id", "").strip()
      if provider_id:
        provider = WebhookProvider.query.filter_by(
          id=provider_id,
          account_id=account_id
        ).first()

        if provider:
          db.session.delete(provider)
          db.session.commit()

      return render_template(
        "settings/index.html",
        active_tab="integrations",
        integrations_view="webhooks",
        team_view=None,
        billing_view=None,
        security_view=None,
        api_allowed=api_allowed,
        account_id=account_id,
        crm_connection=crm_connection,
        crm_prefill=crm_prefill,
        webhook_providers=WebhookProvider.query.filter_by(account_id=account_id).order_by(WebhookProvider.created_at.desc()).all(),
      )

  webhook_providers = WebhookProvider.query.filter_by(account_id=account_id).order_by(WebhookProvider.created_at.desc()).all() if account_id else []
  return render_template(
    "settings/index.html",
    active_tab="integrations",
    integrations_view="webhooks",
    team_view=None,
    billing_view=None,
    security_view=None,
    api_allowed=api_allowed,
    account_id=account_id,
    crm_connection=crm_connection,
    crm_prefill=crm_prefill,
    webhook_providers=webhook_providers,
    show_social_integrations=show_social_integrations,
  )


@bp.route("/integrations/finance", methods=["GET"])
@login_required_settings
def integrations_finance():
  """Finance Add-on setup wizard — visible to all, gated by add-on status."""
  account_id = getattr(g, "current_account_id", None)
  account = Account.query.get(account_id) if account_id else None

  finance_addon = AccountAddOn.query.filter_by(
    account_id=account_id, addon_type="finance"
  ).first() if account_id else None

  stripe_providers = WebhookProvider.query.filter_by(
    account_id=account_id, provider_type="stripe", enabled=True
  ).all() if account_id else []

  qb_providers = WebhookProvider.query.filter_by(
    account_id=account_id, provider_type="quickbooks", enabled=True
  ).all() if account_id else []

  finance_addon_active = bool(finance_addon and finance_addon.status == "active")
  account_email = account.email if account else ""

  return render_template(
    "settings/index.html",
    active_tab="integrations",
    integrations_view="finance",
    team_view=None,
    billing_view=None,
    security_view=None,
    api_allowed=account_allows_api(account_id) if account_id else False,
    account_id=account_id,
    account=account,
    finance_addon=finance_addon,
    finance_addon_active=finance_addon_active,
    stripe_providers=stripe_providers,
    qb_providers=qb_providers,
    account_email=account_email,
    crm_connection=None,
    crm_prefill={},
    webhook_providers=[],
    show_social_integrations=False,
    linkedin_connection=None,
    twitter_connection=None,
    facebook_connection=None,
    gcal_connection=None,
    outlook_cal_connection=None,
    inbox_connections=[],
  )


_AUTOMATION_VIEW_ROLES = {"owner", "admin", "agent"}
_AUTOMATION_MANAGE_ROLES = {"owner", "admin"}
_AUTOMATION_DELETE_ROLES = {"owner", "admin"}


@bp.route("/integrations/automation", methods=["GET", "POST"])
@login_required_settings
def integrations_automation():
  """Automation Studio - Manage automation rules and workflows."""
  from src.models import AutomationRule

  account_id = getattr(g, "current_account_id", None)
  current_user = getattr(g, "current_user", None)
  api_allowed = account_allows_api(account_id) if account_id else False

  if not account_id:
    return redirect(url_for("settings.index"))

  user_role = getattr(current_user, "role", "agent") if current_user else "agent"

  # Viewer and billing roles cannot access Automation Studio at all
  if user_role not in _AUTOMATION_VIEW_ROLES:
    from flask import abort
    abort(403)

  if request.method == "POST":
    action = (request.form.get("action") or "").strip()

    if action == "toggle_rule" and account_id:
      if user_role not in _AUTOMATION_MANAGE_ROLES:
        from flask import abort
        abort(403)
      rule_id = request.form.get("rule_id", "").strip()
      if rule_id:
        rule = AutomationRule.query.filter_by(id=rule_id, account_id=account_id).first()
        if rule:
          try:
            rule.enabled = not rule.enabled
            db.session.commit()
          except Exception:
            db.session.rollback()

    elif action == "delete_rule" and account_id:
      if user_role not in _AUTOMATION_DELETE_ROLES:
        from flask import abort
        abort(403)
      rule_id = request.form.get("rule_id", "").strip()
      if rule_id:
        rule = AutomationRule.query.filter_by(id=rule_id, account_id=account_id).first()
        if rule:
          try:
            db.session.delete(rule)
            db.session.commit()
          except Exception:
            db.session.rollback()

    elif action == "create_rule" and account_id:
      if user_role not in _AUTOMATION_MANAGE_ROLES:
        from flask import abort
        abort(403)
      name = request.form.get("name", "").strip()
      description = request.form.get("description", "").strip()

      if not name:
        return render_template(
          "settings/index.html",
          active_tab="integrations",
          integrations_view="automation",
          api_allowed=api_allowed,
          account_id=account_id,
          rules=AutomationRule.query.filter_by(account_id=account_id).order_by(AutomationRule.created_at.desc()).all(),
          webhook_providers=WebhookProvider.query.filter_by(account_id=account_id).order_by(WebhookProvider.created_at.desc()).all(),
          error="Rule name is required",
        )

      # Parse trigger, conditions, and actions from form
      trigger_event = request.form.get("trigger_event", "").strip()
      trigger_object = request.form.get("trigger_object", "").strip()

      if not trigger_event or not trigger_object:
        return render_template(
          "settings/index.html",
          active_tab="integrations",
          integrations_view="automation",
          api_allowed=api_allowed,
          account_id=account_id,
          rules=AutomationRule.query.filter_by(account_id=account_id).order_by(AutomationRule.created_at.desc()).all(),
          webhook_providers=WebhookProvider.query.filter_by(account_id=account_id).order_by(WebhookProvider.created_at.desc()).all(),
          error="Trigger event and object are required",
        )

      trigger = {
        "event": trigger_event,
        "object": trigger_object,
      }

      # For now, create a simple rule with empty conditions and actions
      # The full form builder will be added in the next iteration
      rule = AutomationRule(
        id=str(uuid4()),
        account_id=account_id,
        name=name,
        description=description,
        trigger=trigger,
        conditions=[],
        condition_logic="AND",
        actions=[],
        enabled=True,
        source="user_created",
      )

      db.session.add(rule)
      db.session.commit()

  # Get all automation rules for this account
  rules = AutomationRule.query.filter_by(account_id=account_id).order_by(
    AutomationRule.created_at.desc()
  ).all()

  # Get webhook providers for rule creation
  webhook_providers = WebhookProvider.query.filter_by(account_id=account_id).order_by(
    WebhookProvider.created_at.desc()
  ).all()

  # Calculate automation metrics
  from src.models import AutomationRuleExecution
  from datetime import datetime, timedelta, timezone

  try:
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    automation_executions_30d = AutomationRuleExecution.query.filter(
      AutomationRuleExecution.account_id == account_id,
      AutomationRuleExecution.created_at >= thirty_days_ago
    ).count()

    automation_time_saved_minutes = automation_executions_30d * 2
    automation_time_saved_hours = automation_time_saved_minutes // 60
    automation_time_saved_display = f"{automation_time_saved_hours}h" if automation_time_saved_hours > 0 else "0h"
  except Exception:
    automation_executions_30d = 0
    automation_time_saved_display = "0h"

  return render_template(
    "settings/index.html",
    active_tab="integrations",
    integrations_view="automation",
    api_allowed=api_allowed,
    account_id=account_id,
    rules=rules,
    webhook_providers=webhook_providers,
    automation_executions_30d=automation_executions_30d,
    automation_time_saved_display=automation_time_saved_display,
    phoenix_url=os.environ.get('PHOENIX_URL'),
    flask_env=os.environ.get('FLASK_ENV', 'production'),
  )


@bp.route("/integrations/automation/rule/<rule_id>", methods=["GET", "POST"])
@login_required_settings
def edit_automation_rule(rule_id):
  """Edit an automation rule - add/edit conditions and actions."""
  from src.models import AutomationRule, WebhookProvider
  import json

  account_id = getattr(g, "current_account_id", None)
  if not account_id:
    return redirect(url_for("settings.index"))

  rule = AutomationRule.query.filter_by(id=rule_id, account_id=account_id).first()
  if not rule:
    flash("Rule not found", "error")
    return redirect(url_for("settings.integrations_automation"))

  if request.method == "POST":
    action = request.form.get("action", "").strip()

    if action == "update_rule":
      # Update basic info
      rule.name = request.form.get("name", "").strip() or rule.name
      rule.description = request.form.get("description", "").strip()

      # Update conditions (JSON from form)
      conditions_json = request.form.get("conditions_json", "[]")
      try:
        rule.conditions = json.loads(conditions_json)
      except:
        flash("Invalid conditions format", "error")
        return redirect(url_for("settings.edit_automation_rule", rule_id=rule_id))

      # Update actions (JSON from form)
      actions_json = request.form.get("actions_json", "[]")
      try:
        rule.actions = json.loads(actions_json)
      except:
        flash("Invalid actions format", "error")
        return redirect(url_for("settings.edit_automation_rule", rule_id=rule_id))

      # Update condition logic
      rule.condition_logic = request.form.get("condition_logic", "AND")

      db.session.commit()
      flash("Rule updated successfully", "success")
      return redirect(url_for("settings.integrations_automation"))

  # Get webhook providers for action options
  webhook_providers = WebhookProvider.query.filter_by(account_id=account_id, enabled=True).all()

  # Check what integrations are available
  # Check both WebhookProvider and InboxConnection for Slack
  from src.models import InboxConnection
  slack_webhooks = any(p.provider_type == 'slack' for p in webhook_providers)
  slack_inbox = InboxConnection.query.filter_by(account_id=account_id, provider='slack', status='connected').first() is not None
  has_slack = slack_webhooks or slack_inbox

  # Check for Microsoft Teams
  teams_webhooks = any(p.provider_type == 'teams' for p in webhook_providers)
  has_teams = teams_webhooks

  has_email = True  # Email is always available via SMTP

  # Build available actions list
  available_actions = {
    'always': [
      {'value': 'tag', 'label': 'Add Tag', 'description': 'Add a tag to the ticket/lead'},
      {'value': 'assign', 'label': 'Assign To', 'description': 'Assign to a team or user'},
    ],
    'integrations': []
  }

  if has_email:
    available_actions['integrations'].append({
      'value': 'send_email',
      'label': 'Send Email',
      'description': 'Send an email notification'
    })

  if has_slack:
    available_actions['integrations'].append({
      'value': 'slack_notify',
      'label': 'Send to Slack',
      'description': 'Post a message to Slack'
    })

  if has_teams:
    available_actions['integrations'].append({
      'value': 'teams_notify',
      'label': 'Send to Microsoft Teams',
      'description': 'Post a message to Teams'
    })

  # Add webhook providers
  for provider in webhook_providers:
    if provider.provider_type not in ['slack', 'teams']:  # Slack and Teams handled separately
      available_actions['integrations'].append({
        'value': f'webhook_{provider.id}',
        'label': f'Webhook: {provider.configuration_name}',
        'description': f'Call webhook ({provider.provider_type})',
        'provider_id': provider.id
      })

  return render_template(
    "settings/automation_rule_edit.html",
    rule=rule,
    webhook_providers=webhook_providers,
    available_actions=available_actions,
    account_id=account_id,
  )


@bp.route("/automation/analytics", methods=["GET"])
@login_required_settings
def automation_analytics():
  """Automation Studio ROI Analytics Dashboard."""
  from src.models import AutomationRule, AutomationRuleExecution
  from src.automation.roi_calculator import calculate_account_roi
  from datetime import datetime, timedelta
  import json

  account_id = getattr(g, "current_account_id", None)

  if not account_id:
    return redirect(url_for("settings.index"))

  # Get time period from query params (default: month)
  time_period = request.args.get('period', 'month')

  # Calculate account-level ROI
  try:
    roi_data = calculate_account_roi(account_id, time_period)
  except Exception as e:
    current_app.logger.error(f"Failed to calculate ROI: {e}")
    roi_data = {
      "total_time_saved": {"hours": 0, "display": "0 hours"},
      "total_cost_saved": {"amount": 0, "display": "$0"},
      "overall_accuracy": {"rate": 0, "display": "0%"},
      "rules_breakdown": []
    }

  # Get all rules for the account
  rules = AutomationRule.query.filter_by(account_id=account_id).all()

  # Get execution history for chart (last 30 days)
  thirty_days_ago = datetime.utcnow() - timedelta(days=30)
  executions = AutomationRuleExecution.query.filter(
    AutomationRuleExecution.account_id == account_id,
    AutomationRuleExecution.created_at >= thirty_days_ago
  ).order_by(AutomationRuleExecution.created_at).all()

  # Group executions by date for chart
  execution_dates = {}
  for execution in executions:
    date_key = execution.created_at.strftime('%Y-%m-%d')
    if date_key not in execution_dates:
      execution_dates[date_key] = {"total": 0, "successful": 0, "failed": 0}
    execution_dates[date_key]["total"] += 1
    if execution.success:
      execution_dates[date_key]["successful"] += 1
    else:
      execution_dates[date_key]["failed"] += 1

  # Convert to chart data
  chart_data = {
    "labels": list(execution_dates.keys()),
    "total": [execution_dates[k]["total"] for k in execution_dates.keys()],
    "successful": [execution_dates[k]["successful"] for k in execution_dates.keys()],
    "failed": [execution_dates[k]["failed"] for k in execution_dates.keys()]
  }

  return render_template(
    "settings/index.html",
    active_tab="integrations",
    integrations_view="automation_analytics",
    account_id=account_id,
    roi_data=roi_data,
    rules=rules,
    chart_data=json.dumps(chart_data),
    time_period=time_period,
  )


@bp.route("/automation/rules/<rule_id>/analytics", methods=["GET"])
@login_required_settings
def rule_analytics(rule_id):
  """Individual automation rule analytics page."""
  from src.models import AutomationRule
  from src.automation.roi_calculator import calculate_rule_roi
  import json

  account_id = getattr(g, "current_account_id", None)

  if not account_id:
    return redirect(url_for("settings.index"))

  # Get the rule
  rule = AutomationRule.query.filter_by(id=rule_id, account_id=account_id).first()
  if not rule:
    flash("Rule not found", "error")
    return redirect(url_for("settings.integrations_automation"))

  # Get time period from query params (default: month)
  time_period = request.args.get('period', 'month')

  # Calculate rule ROI
  try:
    roi_data = calculate_rule_roi(rule_id, time_period)
  except Exception as e:
    current_app.logger.error(f"Failed to calculate rule ROI: {e}")
    roi_data = {
      "rule_id": rule_id,
      "rule_name": rule.name,
      "time_saved": {"hours": 0, "display": "0 hours"},
      "cost_saved": {"amount": 0, "display": "$0"},
      "accuracy": {"rate": 0, "display": "0%"},
      "executions": {"total": 0, "successful": 0, "failed": 0}
    }

  return render_template(
    "settings/rule_analytics.html",
    active_tab="integrations",
    account_id=account_id,
    rule=rule,
    roi_data=roi_data,
    time_period=time_period,
  )


@bp.route("/integrations/knowledge-base", methods=["GET", "POST"])
@login_required_settings
@limiter.limit("10 per minute", methods=["POST"])
def knowledge_base_integration():
    """Knowledge base integration settings."""
    from flask import flash
    from src.models import KBIntegration, KBArticle

    account_id = getattr(g, "current_account_id", None)
    if not account_id:
        return redirect(url_for("settings.index"))

    if request.method == "POST":
        action = request.form.get("action")

        if action == "upload_files":
            # Handle file upload
            files = request.files.getlist("kb_files")
            if not files or not any(f.filename for f in files):
                flash("No files selected", "error")
                return redirect(url_for("settings.knowledge_base_integration"))

            from src.integrations.kb import process_uploaded_files
            result = process_uploaded_files(files, account_id)

            if result["success"] > 0:
                flash(f"Successfully uploaded {result['success']} articles", "success")
            if result["failed"] > 0:
                for error in result["errors"][:5]:  # Show first 5 errors
                    flash(error, "error")

            return redirect(url_for("settings.knowledge_base_integration"))

        elif action == "add_url":
            url = request.form.get("url", "").strip()
            title = request.form.get("title", "").strip()
            if not url:
                flash("URL is required", "error")
                return redirect(url_for("settings.knowledge_base_integration"))
            from src.integrations.kb import process_url_source
            result = process_url_source(account_id, url, title)
            if result["success"]:
                flash("URL added to your knowledge base", "success")
            else:
                flash(result["error"] or "Failed to add URL", "error")
            return redirect(url_for("settings.knowledge_base_integration"))

        elif action == "crawl_url":
            url = request.form.get("url", "").strip()
            if not url:
                flash("URL is required", "error")
                return redirect(url_for("settings.knowledge_base_integration"))
            from src.integrations.kb import is_crawl_enabled
            if not is_crawl_enabled(account_id):
                flash("Crawl mode is available on Business and Scale plans.", "error")
                return redirect(url_for("settings.knowledge_base_integration"))
            from src.celery_inboxiq import crawl_kb_source_task
            crawl_kb_source_task.delay(account_id, url)
            flash("Crawl started — articles will appear in your knowledge base within a few minutes.", "success")
            return redirect(url_for("settings.knowledge_base_integration"))

        elif action == "delete_article":
            article_id = request.form.get("article_id")
            from src.integrations.kb import delete_kb_article
            if delete_kb_article(article_id, account_id):
                flash("Article deleted", "success")
            else:
                flash("Article not found", "error")
            return redirect(url_for("settings.knowledge_base_integration"))

    # GET: Display current KB status — include all integration types
    integrations = KBIntegration.query.filter_by(account_id=account_id).all()
    integration_ids = [i.id for i in integrations]
    total_articles = sum(i.article_count or 0 for i in integrations)
    articles = []
    if integration_ids:
        articles = (
            KBArticle.query
            .filter(KBArticle.integration_id.in_(integration_ids))
            .order_by(KBArticle.created_at.desc())
            .limit(50)
            .all()
        )

    # Primary integration for status display (file_upload, falling back to any)
    integration = next((i for i in integrations if i.integration_type == "file_upload"), None) or (integrations[0] if integrations else None)

    from src.integrations.kb import get_kb_article_limit, is_crawl_enabled
    kb_article_limit = get_kb_article_limit(account_id)
    crawl_enabled = is_crawl_enabled(account_id)

    return render_template(
        "settings/knowledge_base.html",
        integration=integration,
        total_articles=total_articles,
        kb_article_limit=kb_article_limit,
        crawl_enabled=crawl_enabled,
        articles=articles,
        account_id=account_id,
    )


@bp.route("/settings/integrations/triage-config", methods=["GET", "POST"])
@login_required_settings
def triage_config_settings():
    """Triage configuration settings (SLA mappings, fallback messages, defaults)."""
    account_id = getattr(g, "current_account_id", None)
    if not account_id:
        flash("Account not found", "error")
        return redirect(url_for("settings.settings_page"))

    from src.dspy.triage_config import get_triage_config, save_triage_config, invalidate_triage_config
    from src.dspy.triage_config import (
        DEFAULT_SLA_MAPPINGS, DEFAULT_SLA_HOURS, DEFAULT_FALLBACK_MESSAGES,
        DEFAULT_OWNER, DEFAULT_CATEGORY, DEFAULT_PRIORITY,
        DEFAULT_CONFIDENCE_THRESHOLD, DEFAULT_P2_NEUTRAL_AUTO_HANDLE,
        DEFAULT_BODY_PREVIEW_LIMIT, DEFAULT_TRAIN_MIN_SAMPLES,
    )

    if request.method == "POST":
        action = request.form.get("action")

        if action == "save_config":
            try:
                # Parse SLA mappings
                sla_mappings = {}
                for p in ["P0", "P1", "P2", "P3", "P4"]:
                    val = request.form.get(f"sla_display_{p}", "").strip()
                    if val:
                        sla_mappings[p] = val

                sla_hours = {}
                for p in ["P0", "P1", "P2", "P3", "P4"]:
                    val = request.form.get(f"sla_hours_{p}", "").strip()
                    if val:
                        try:
                            sla_hours[p] = int(val)
                        except ValueError:
                            pass

                # Parse fallback messages
                fallback_messages = {}
                for key in ["action_required", "optional", "auto_handled", "needs_review"]:
                    val = request.form.get(f"fallback_{key}", "").strip()
                    if val:
                        fallback_messages[key] = val

                # Parse other settings
                default_owner = request.form.get("default_owner", "").strip() or None
                default_team = request.form.get("default_team", "").strip() or None
                default_category = request.form.get("default_category", "").strip() or None
                default_priority = request.form.get("default_priority", "").strip() or None
                p2_neutral_auto_handle = request.form.get("p2_neutral_auto_handle") == "on"

                confidence_threshold = None
                val = request.form.get("confidence_threshold", "").strip()
                if val:
                    try:
                        confidence_threshold = float(val)
                    except ValueError:
                        pass

                body_preview_limit = None
                val = request.form.get("body_preview_limit", "").strip()
                if val:
                    try:
                        body_preview_limit = int(val)
                    except ValueError:
                        pass

                train_min_samples = None
                val = request.form.get("train_min_samples", "").strip()
                if val:
                    try:
                        train_min_samples = int(val)
                    except ValueError:
                        pass

                save_triage_config(
                    account_id=account_id,
                    sla_mappings=sla_mappings if sla_mappings else None,
                    sla_hours=sla_hours if sla_hours else None,
                    fallback_messages=fallback_messages if fallback_messages else None,
                    default_owner=default_owner,
                    default_team=default_team,
                    default_category=default_category,
                    default_priority=default_priority,
                    p2_neutral_auto_handle=p2_neutral_auto_handle,
                    confidence_threshold=confidence_threshold,
                    body_preview_limit=body_preview_limit,
                    train_min_samples=train_min_samples,
                )
                flash("Triage configuration saved", "success")
            except Exception as exc:
                flash(f"Failed to save configuration: {exc}", "error")

            return redirect(url_for("settings.triage_config_settings"))

        elif action == "reset_defaults":
            from src.models import TriageConfig
            config = TriageConfig.query.filter_by(account_id=account_id).first()
            if config:
                db.session.delete(config)
                db.session.commit()
                invalidate_triage_config(account_id)
                flash("Configuration reset to system defaults", "success")
            return redirect(url_for("settings.triage_config_settings"))

    # GET: Load current config
    current_config = get_triage_config(account_id)

    return render_template(
        "settings/triage_config.html",
        config=current_config,
        defaults={
            "sla_mappings": DEFAULT_SLA_MAPPINGS,
            "sla_hours": DEFAULT_SLA_HOURS,
            "fallback_messages": DEFAULT_FALLBACK_MESSAGES,
            "default_owner": DEFAULT_OWNER,
            "default_category": DEFAULT_CATEGORY,
            "default_priority": DEFAULT_PRIORITY,
            "confidence_threshold": DEFAULT_CONFIDENCE_THRESHOLD,
            "p2_neutral_auto_handle": DEFAULT_P2_NEUTRAL_AUTO_HANDLE,
            "body_preview_limit": DEFAULT_BODY_PREVIEW_LIMIT,
            "train_min_samples": DEFAULT_TRAIN_MIN_SAMPLES,
        },
        account_id=account_id,
    )


# ── Developer tab POST handlers ───────────────────────────────────────────────

ALLOWED_SCOPES = {"intake:write", "tickets:read", "decisions:read"}


@bp.route("/settings/developer", methods=["POST"])
@login_required_settings
def developer_post():
  """Handle Developer tab form submissions: access request, app registration, revoke."""
  import hashlib

  account_id = getattr(g, "current_account_id", None)
  account = Account.query.get(account_id) if account_id else None

  if not account_id or not account:
    return redirect(url_for("settings.settings_page", tab="team"))

  action = (request.form.get("action") or "").strip()

  # ── Request developer access (allowed before developer_access is granted) ──
  if action == "request_access":
    if not account.developer_access:
      full_name = (request.form.get("full_name") or "").strip()[:255]
      company = (request.form.get("company") or "").strip()[:255]
      use_case = (request.form.get("use_case") or "").strip()[:4000]
      agreed_tos = request.form.get("agreed_tos") == "on"
      if full_name and company and use_case and agreed_tos:
        existing = DeveloperAccessRequest.query.filter_by(account_id=account_id).first()
        if not existing:
          access_req = DeveloperAccessRequest(
            account_id=account_id,
            full_name=full_name,
            company=company,
            use_case=use_case,
            scopes=[],
            agreed_tos=True,
            status="pending",
          )
          try:
            db.session.add(access_req)
            db.session.commit()
          except Exception:
            db.session.rollback()
            raise
          current_app.logger.info(f"DeveloperAccessRequest created account={account_id}")
    return redirect(url_for("settings.settings_page", tab="developer"))

  # All other actions require developer_access to be enabled
  if not account.developer_access:
    return redirect(url_for("settings.settings_page", tab="developer"))

  # ── Register new app ───────────────────────────────────────────────────────
  if action == "register_app":
    app_name = (request.form.get("app_name") or "").strip()[:255]
    if not app_name:
      registered_apps = RegisteredApp.query.filter_by(account_id=account_id).order_by(RegisteredApp.created_at.desc()).all()
      return _developer_page(
        account_id=account_id,
        account=account,
        developer_access_request=None,
        registered_apps=registered_apps,
        selected_app=registered_apps[0] if registered_apps else None,
        product_accesses={},
        error="App name is required.",
        new_app=None,
      )

    client_id = "iq_" + secrets.token_hex(16)
    client_secret_plain = secrets.token_hex(32)

    new_registered_app = RegisteredApp(
      account_id=account_id,
      name=app_name,
      client_id=client_id,
      client_secret_enc=encrypt_value(client_secret_plain),
      scopes=[],
    )
    try:
      db.session.add(new_registered_app)
      db.session.commit()
    except Exception:
      db.session.rollback()
      raise
    current_app.logger.info(
      f"RegisteredApp created account={account_id} client_id={client_id}"
    )

    registered_apps = RegisteredApp.query.filter_by(account_id=account_id).order_by(RegisteredApp.created_at.desc()).all()
    return _developer_page(
      account_id=account_id,
      account=account,
      developer_access_request=None,
      registered_apps=registered_apps,
      selected_app=new_registered_app,
      product_accesses={},
      error=None,
      new_app={"name": app_name, "client_id": client_id, "client_secret": client_secret_plain},
    )

  # ── Revoke app ─────────────────────────────────────────────────────────────
  if action == "revoke_app":
    app_id = (request.form.get("app_id") or "").strip()
    if app_id:
      app = RegisteredApp.query.filter_by(id=app_id, account_id=account_id).first()
      if app:
        app.status = "suspended"
        try:
          db.session.commit()
        except Exception:
          db.session.rollback()
          raise
        current_app.logger.info(
          f"RegisteredApp revoked account={account_id} client_id={app.client_id}"
        )

  if action == "delete_app":
    app_id = (request.form.get("app_id") or "").strip()
    if app_id:
      app = RegisteredApp.query.filter_by(id=app_id, account_id=account_id).first()
      if app:
        client_id = app.client_id
        try:
          db.session.delete(app)
          db.session.commit()
        except Exception:
          db.session.rollback()
          raise
        current_app.logger.info(
          f"RegisteredApp deleted account={account_id} client_id={client_id}"
        )
    return redirect(url_for("settings.settings_page", tab="developer"))

  # ── Request product access ─────────────────────────────────────────────────
  if action == "request_product":
    app_id = (request.form.get("app_id") or "").strip()
    product_slug = (request.form.get("product_slug") or "").strip()
    use_case = (request.form.get("use_case") or "").strip()[:4000]

    app = RegisteredApp.query.filter_by(id=app_id, account_id=account_id).first()
    if not app or not product_slug:
      return redirect(url_for("settings.settings_page", tab="developer"))

    # Block duplicate requests
    existing = AppProductAccess.query.filter_by(app_id=app_id, product_slug=product_slug).first()
    if existing:
      return redirect(url_for("settings.settings_page", tab="developer", app_id=app_id))

    from src.developer.products import get_product_by_slug
    product = get_product_by_slug(product_slug)
    if not product:
      return redirect(url_for("settings.settings_page", tab="developer", app_id=app_id))
    status = "approved" if product.get("approval") == "auto" else "pending"

    access = AppProductAccess(
      app_id=app_id,
      account_id=account_id,
      product_slug=product_slug,
      status=status,
      use_case=use_case or None,
    )
    try:
      db.session.add(access)
      db.session.commit()
    except Exception:
      db.session.rollback()
      raise
    current_app.logger.info(
      f"AppProductAccess created account={account_id} app={app_id} product={product_slug} status={status}"
    )
    return redirect(url_for("settings.settings_page", tab="developer", app_id=app_id))

  # ── Update product webhook ─────────────────────────────────────────────────
  if action == "update_webhook":
    app_id = (request.form.get("app_id") or "").strip()
    product_slug = (request.form.get("product_slug") or "").strip()
    webhook_url = (request.form.get("webhook_url") or "").strip() or None

    app = RegisteredApp.query.filter_by(id=app_id, account_id=account_id).first()
    if not app:
      return redirect(url_for("settings.settings_page", tab="developer"))

    access = AppProductAccess.query.filter_by(app_id=app_id, product_slug=product_slug).first()
    if not access or access.status != "approved":
      return redirect(url_for("settings.settings_page", tab="developer", app_id=app_id))

    # Basic URL validation
    if webhook_url and not webhook_url.startswith(("https://", "http://")):
      return redirect(url_for("settings.settings_page", tab="developer", app_id=app_id))

    access.webhook_url = webhook_url
    try:
      db.session.commit()
    except Exception:
      db.session.rollback()
      raise
    current_app.logger.info(
      f"AppProductAccess webhook updated account={account_id} app={app_id} product={product_slug}"
    )
    return redirect(url_for("settings.settings_page", tab="developer", app_id=app_id))

  if action == "update_origins":
    app_id = (request.form.get("app_id") or "").strip()
    raw_origins = (request.form.get("origins") or "")

    app = RegisteredApp.query.filter_by(id=app_id, account_id=account_id).first()
    if app:
      origins = []
      for line in raw_origins.splitlines():
        origin = line.strip().rstrip("/")[:255]
        if origin.startswith("https://") and len(origin) > 8:
          origins.append(origin)
      app.allowed_origins = origins[:20]
      try:
        db.session.commit()
      except Exception:
        db.session.rollback()
        raise
      current_app.logger.info(
        f"RegisteredApp allowed_origins updated account={account_id} app={app_id} count={len(app.allowed_origins)}"
      )
    return redirect(url_for("settings.settings_page", tab="developer", app_id=app_id))

  return redirect(url_for("settings.settings_page", tab="developer"))


def _developer_page(*, account_id, account, developer_access_request, registered_apps,
                    selected_app=None, product_accesses=None, error, new_app):
  """Render the developer settings tab directly (used after form submission)."""
  from src.models.ai import MCPServerCatalog
  mcp_servers = MCPServerCatalog.query.filter_by(enabled=True).order_by(MCPServerCatalog.label.asc()).all()
  return render_template(
    "settings/index.html",
    active_tab="developer",
    account_id=account_id,
    account=account,
    developer_access_request=developer_access_request,
    registered_apps=registered_apps,
    selected_app=selected_app,
    product_accesses=product_accesses or {},
    product_catalog=PRODUCT_CATALOG,
    mcp_servers=mcp_servers,
    developer_error=error,
    new_app=new_app,
    # required by base template
    security_view=None,
    team_view=None,
    billing_view=None,
    integrations_view=None,
    passkeys=[],
    totp_devices=[],
    seats_used=0,
    seats_limit=account.seats_limit if account else None,
    plan_name=None,
    draft_reply_enabled=True,
    crm_connection=None,
    crm_prefill={},
    linkedin_connection=None,
    twitter_connection=None,
    facebook_connection=None,
    gcal_connection=None,
    outlook_cal_connection=None,
  )


_WEBHOOK_TEST_PAYLOADS = {
  "chat": {
    "event": "chat.message",
    "data": {
      "message": "Hello, this is a test message from a visitor.",
      "session_id": "test_session_001",
    },
  },
  "forms": {
    "event": "form.submitted",
    "data": {
      "form_id": "contact_form",
      "fields": {
        "name": "Test User",
        "email": "test@example.com",
        "message": "This is a test form submission.",
      },
    },
  },
  "intake_api": {
    "event": "intake.ticket",
    "data": {
      "ticket_id": "test_ticket_001",
      "subject": "Test webhook delivery",
      "body": "This is a test event from InboxIQ. Your webhook is working correctly.",
      "priority": "normal",
    },
  },
}


@bp.route("/settings/developer/test-webhook", methods=["POST"])
@login_required_settings
def developer_test_webhook():
  """Return JSON result of firing a synthetic event at the product webhook URL."""
  import time
  from datetime import timezone

  account_id = getattr(g, "current_account_id", None)
  if not account_id:
    return jsonify({"ok": False, "error": "unauthorized"}), 401

  body = request.get_json(silent=True) or {}
  app_id = (body.get("app_id") or "").strip()
  product_slug = (body.get("product_slug") or "").strip()

  if not app_id or not product_slug:
    return jsonify({"ok": False, "error": "app_id and product_slug required"}), 400

  app = RegisteredApp.query.filter_by(id=app_id, account_id=account_id).first()
  if not app:
    return jsonify({"ok": False, "error": "app not found"}), 404

  access = AppProductAccess.query.filter_by(
    app_id=app_id, product_slug=product_slug, status="approved"
  ).first()
  if not access:
    return jsonify({"ok": False, "error": "product not approved"}), 400

  if not access.webhook_url:
    return jsonify({"ok": False, "error": "no webhook URL configured"}), 400

  template = _WEBHOOK_TEST_PAYLOADS.get(product_slug, {
    "event": f"{product_slug}.test",
    "data": {},
  })
  payload = {
    **template,
    "app_id": app.client_id,
    "account_id": account_id,
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "test": True,
  }

  start = time.monotonic()
  try:
    resp = requests_lib.post(
      access.webhook_url,
      json=payload,
      timeout=5,
      allow_redirects=False,
      headers={"User-Agent": "InboxIQ-Webhook/1.0"},
    )
    latency_ms = int((time.monotonic() - start) * 1000)
    return jsonify({
      "ok": True,
      "status_code": resp.status_code,
      "body": resp.text[:500],
      "latency_ms": latency_ms,
    })
  except requests_lib.exceptions.Timeout:
    return jsonify({"ok": False, "error": "timeout", "latency_ms": 5000})
  except requests_lib.exceptions.ConnectionError as e:
    return jsonify({"ok": False, "error": f"connection_error: {str(e)[:120]}"})
  except Exception as e:
    current_app.logger.error(f"test_webhook error account={account_id} app={app_id}: {e}")
    return jsonify({"ok": False, "error": "internal_error"}), 500


@bp.route("/settings/developer/webhook-deliveries", methods=["GET"])
@login_required_settings
def developer_webhook_deliveries():
  """Return the last 10 webhook delivery attempts for an app + product."""
  account_id = getattr(g, "current_account_id", None)
  if not account_id:
    return jsonify({"ok": False, "error": "unauthorized"}), 401

  app_id = (request.args.get("app_id") or "").strip()
  product_slug = (request.args.get("product_slug") or "").strip()
  if not app_id or not product_slug:
    return jsonify({"ok": False, "error": "app_id and product_slug required"}), 400

  app = RegisteredApp.query.filter_by(id=app_id, account_id=account_id).first()
  if not app:
    return jsonify({"ok": False, "error": "app not found"}), 404

  deliveries = (
    AppWebhookDelivery.query
    .filter_by(app_id=app_id, product_slug=product_slug)
    .order_by(AppWebhookDelivery.created_at.desc())
    .limit(10)
    .all()
  )

  return jsonify({
    "ok": True,
    "deliveries": [
      {
        "event":       d.event,
        "success":     d.success,
        "status_code": d.status_code,
        "error":       d.error,
        "latency_ms":  d.latency_ms,
        "created_at":  d.created_at.isoformat() if d.created_at else None,
      }
      for d in deliveries
    ],
  })
