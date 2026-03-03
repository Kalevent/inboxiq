import os
import secrets
from datetime import datetime
from uuid import uuid4

from flask import current_app, flash, g, jsonify, redirect, render_template, request, url_for

from src.extensions import db, limiter
from src.models.auth import Passkey, TOTPDevice
from src.models.automation import WebhookProvider
from src.models.core import User, Account, InboxConnection
from src.models.developer import RegisteredApp, DeveloperAccessRequest
from src.crypto import encrypt_value, decrypt_value
from src.api.v1.access_control import account_allows_api
from src.settings import bp, login_required_settings

RBAC_DEFAULT_ROLES = [
  {
    "key": "owner",
    "label": "Owner",
    "description": "Full control including billing, security, and role delegation.",
    "permissions": [
      "Manage billing & seats",
      "Invite/remove users",
      "Manage integrations and security",
      "View and respond to tickets",
    ],
  },
  {
    "key": "admin",
    "label": "Admin",
    "description": "Workspace configuration without billing authority.",
    "permissions": [
      "Manage users (except owners)",
      "Manage integrations and security",
      "View and respond to tickets",
    ],
  },
  {
    "key": "agent",
    "label": "Agent",
    "description": "Day-to-day support work with no access to billing or security.",
    "permissions": [
      "View/triage/respond to tickets",
      "Create and edit macros",
      "View integrations status",
    ],
  },
  {
    "key": "viewer",
    "label": "Viewer",
    "description": "Read-only access for audits or leadership.",
    "permissions": [
      "Read tickets and metrics",
      "View integrations status",
      "No configuration access",
    ],
  },
  {
    "key": "billing",
    "label": "Billing-only",
    "description": "Finance-only access to invoices and seats, nothing else.",
    "permissions": [
      "Manage billing & invoices",
      "View seat usage",
      "No ticket or integration access",
    ],
  },
]


@bp.get("/settings")
@bp.get("/settings/")
@login_required_settings
def settings_root():
  """Redirect bare /settings to the default tab."""
  return redirect(url_for("settings.settings_page", tab="team"))


@bp.get("/settings/<tab>")
@login_required_settings
def settings_page(tab):
  allowed = {"team", "profile", "billing", "security", "integrations", "features", "developer"}
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

  # Get draft reply feature status for features tab
  draft_reply_enabled = False
  draft_reply_has_access = False
  if tab == "features" and account_id:
    from src.models import AccountFeatureFlags
    from src.features import check_draft_reply_access

    feature_flags = AccountFeatureFlags.query.filter_by(account_id=account_id).first()
    draft_reply_enabled = feature_flags.draft_reply_enabled if feature_flags else False
    draft_reply_has_access = check_draft_reply_access(account_id)

  # Get CRM connection for integrations tab
  crm_connection = None
  crm_prefill = {}
  linkedin_connection = None
  twitter_connection = None
  if tab == "integrations" and account_id:
    crm_connection = InboxConnection.query.filter_by(account_id=account_id, provider="crm").first()
    linkedin_connection = InboxConnection.query.filter_by(account_id=account_id, provider="linkedin_social").first()
    twitter_connection = InboxConnection.query.filter_by(account_id=account_id, provider="twitter_social").first()
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

  if tab == "security":
    user = getattr(g, "current_user", None)
    if user:
      passkeys = Passkey.query.filter_by(user_id=user.id).all()
      totp_devices = TOTPDevice.query.filter_by(user_id=user.id).all()

  # Developer tab — only accessible if account has developer_access
  developer_access_request = None
  registered_apps = []
  if tab == "developer" and account_id:
    if not (account and account.developer_access):
      tab = "team"  # silently redirect if not enabled
    else:
      developer_access_request = DeveloperAccessRequest.query.filter_by(
        account_id=account_id
      ).order_by(DeveloperAccessRequest.created_at.desc()).first()
      if developer_access_request and developer_access_request.status == "approved":
        registered_apps = RegisteredApp.query.filter_by(
          account_id=account_id
        ).order_by(RegisteredApp.created_at.desc()).all()

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
    draft_reply_has_access=draft_reply_has_access,
    crm_connection=crm_connection,
    crm_prefill=crm_prefill,
    linkedin_connection=linkedin_connection,
    twitter_connection=twitter_connection,
    developer_access_request=developer_access_request,
    registered_apps=registered_apps,
    developer_error=None,
    new_app=None,
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


def _role_store():
  return current_app.config.setdefault("ROLE_ASSIGNMENTS_STORE", {})


def _resolved_assignments(account_id, members):
  """
  Merge stored assignments with sensible defaults (first member is owner,
  rest default to agent) while guaranteeing at least one owner.
  """
  store = _role_store()
  stored = store.get(str(account_id)) or {}
  assignments = {}
  for idx, member in enumerate(members):
    default_role = "owner" if idx == 0 else "agent"
    assignments[str(member.id)] = stored.get(str(member.id)) or default_role
  if members and "owner" not in assignments.values():
    assignments[str(members[0].id)] = "owner"
  return assignments


def _save_assignments(account_id, assignments):
  store = _role_store()
  store[str(account_id)] = assignments
  current_app.config["ROLE_ASSIGNMENTS_STORE"] = store
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
  assignments = _resolved_assignments(account_id, members)
  member_payload = _serialize_members(members, assignments)
  csrf_token_value = request.cookies.get("csrf_access_token") or request.cookies.get("csrf_refresh_token") or ""
  return render_template(
    "settings/index.html",
    active_tab="team",
    team_view="roles",
    billing_view=None,
    security_view=None,
    integrations_view=None,
    roles=RBAC_DEFAULT_ROLES,
    members=member_payload,
    csrf_token=csrf_token_value,
  )


@bp.get("/api/roles")
@bp.get("/settings/api/roles")
@login_required_settings
def api_roles():
  account_id = getattr(g, "current_account_id", None)
  if not account_id:
    return jsonify({"error": "account not found"}), 404
  members = User.query.filter_by(account_id=account_id).order_by(User.created_at.asc()).all()
  assignments = _resolved_assignments(account_id, members)
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

  assignments = _resolved_assignments(account_id, members)
  caller_role = assignments.get(str(user.id))
  if caller_role not in {"owner", "admin"}:
    return jsonify({"error": "insufficient permissions"}), 403

  assignments[str(target.id)] = role_key
  if "owner" not in assignments.values():
    return jsonify({"error": "at least one owner is required"}), 400

  _save_assignments(account_id, assignments)
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


@bp.route("/integrations/social/disconnect", methods=["POST"])
@login_required_settings
def integrations_social_disconnect():
    """Disconnect a LinkedIn or Twitter social CRM connection."""
    from src.models import InboxConnection
    account_id = getattr(g, "current_account_id", None)
    provider = request.form.get("provider", "").strip()
    if provider not in ("linkedin_social", "twitter_social") or not account_id:
        return redirect(url_for("settings.settings_page", tab="integrations"))

    conn = InboxConnection.query.filter_by(account_id=account_id, provider=provider).first()
    if conn:
        from src.extensions import db
        db.session.delete(conn)
        db.session.commit()

    return redirect(url_for("settings.settings_page", tab="integrations"))


@bp.route("/integrations/webhooks", methods=["GET", "POST"])
@login_required_settings
@limiter.limit("20 per minute", methods=["POST"])  # Rate limit: 20 provider configurations per minute
def integrations_webhooks():
  user = getattr(g, "current_user", None)
  account_id = getattr(g, "current_account_id", None)
  api_allowed = account_allows_api(account_id) if account_id else False
  crm_connection = None
  crm_prefill = {}
  linkedin_connection = None
  twitter_connection = None
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
  )


@bp.route("/integrations/automation", methods=["GET", "POST"])
@login_required_settings
def integrations_automation():
  """Automation Studio - Manage automation rules and workflows."""
  from src.models import AutomationRule

  account_id = getattr(g, "current_account_id", None)
  api_allowed = account_allows_api(account_id) if account_id else False

  if not account_id:
    return redirect(url_for("settings.index"))

  if request.method == "POST":
    action = (request.form.get("action") or "").strip()

    if action == "toggle_rule" and account_id:
      rule_id = request.form.get("rule_id", "").strip()
      if rule_id:
        rule = AutomationRule.query.filter_by(id=rule_id, account_id=account_id).first()
        if rule:
          rule.enabled = not rule.enabled
          db.session.commit()

    elif action == "delete_rule" and account_id:
      rule_id = request.form.get("rule_id", "").strip()
      if rule_id:
        rule = AutomationRule.query.filter_by(id=rule_id, account_id=account_id).first()
        if rule:
          db.session.delete(rule)
          db.session.commit()

    elif action == "create_rule" and account_id:
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

        elif action == "delete_article":
            article_id = request.form.get("article_id")
            from src.integrations.kb import delete_kb_article
            if delete_kb_article(article_id, account_id):
                flash("Article deleted", "success")
            else:
                flash("Article not found", "error")
            return redirect(url_for("settings.knowledge_base_integration"))

    # GET: Display current KB status
    integration = KBIntegration.query.filter_by(
        account_id=account_id,
        integration_type="file_upload"
    ).first()

    articles = []
    if integration:
        articles = KBArticle.query.filter_by(
            integration_id=integration.id
        ).order_by(KBArticle.created_at.desc()).limit(50).all()

    return render_template(
        "settings/knowledge_base.html",
        integration=integration,
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

  if not account.developer_access:
    return redirect(url_for("settings.settings_page", tab="team"))

  action = (request.form.get("action") or "").strip()

  # ── Submit access request ──────────────────────────────────────────────────
  if action == "request_access":
    full_name = (request.form.get("full_name") or "").strip()
    company = (request.form.get("company") or "").strip()
    use_case = (request.form.get("use_case") or "").strip()
    callback_url = (request.form.get("callback_url") or "").strip()
    agreed_tos = request.form.get("agreed_tos") == "1"
    raw_scopes = request.form.getlist("scopes")
    scopes = [s for s in raw_scopes if s in ALLOWED_SCOPES]

    if not full_name or not company or not use_case or not scopes or not agreed_tos:
      return _developer_page(
        account_id=account_id,
        account=account,
        developer_access_request=None,
        registered_apps=[],
        error="Please fill in all required fields and agree to the API Terms of Service.",
        new_app=None,
      )

    existing = DeveloperAccessRequest.query.filter_by(account_id=account_id).first()
    if existing:
      return redirect(url_for("settings.settings_page", tab="developer"))

    # Auto-approve when only low-risk scopes are requested
    low_risk = {"intake:write"}
    status = "approved" if set(scopes).issubset(low_risk) else "pending"

    req = DeveloperAccessRequest(
      account_id=account_id,
      full_name=full_name,
      company=company,
      use_case=use_case,
      scopes=scopes,
      callback_url=callback_url or None,
      agreed_tos=True,
      status=status,
    )
    db.session.add(req)
    db.session.commit()
    current_app.logger.info(
      f"DeveloperAccessRequest created account={account_id} status={status}"
    )
    return redirect(url_for("settings.settings_page", tab="developer"))

  # ── Register new app ───────────────────────────────────────────────────────
  if action == "register_app":
    access_req = DeveloperAccessRequest.query.filter_by(
      account_id=account_id, status="approved"
    ).first()
    if not access_req:
      return redirect(url_for("settings.settings_page", tab="developer"))

    app_name = (request.form.get("app_name") or "").strip()
    if not app_name:
      return _developer_page(
        account_id=account_id,
        account=account,
        developer_access_request=access_req,
        registered_apps=RegisteredApp.query.filter_by(account_id=account_id).order_by(RegisteredApp.created_at.desc()).all(),
        error="App name is required.",
        new_app=None,
      )

    client_id = "iq_" + secrets.token_hex(16)
    client_secret_plain = secrets.token_hex(32)

    app = RegisteredApp(
      account_id=account_id,
      name=app_name,
      client_id=client_id,
      client_secret_enc=encrypt_value(client_secret_plain),
      scopes=access_req.scopes,
    )
    db.session.add(app)
    db.session.commit()
    current_app.logger.info(
      f"RegisteredApp created account={account_id} client_id={client_id}"
    )

    registered_apps = RegisteredApp.query.filter_by(account_id=account_id).order_by(RegisteredApp.created_at.desc()).all()
    return _developer_page(
      account_id=account_id,
      account=account,
      developer_access_request=access_req,
      registered_apps=registered_apps,
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
        db.session.commit()
        current_app.logger.info(
          f"RegisteredApp revoked account={account_id} client_id={app.client_id}"
        )

  return redirect(url_for("settings.settings_page", tab="developer"))


def _developer_page(*, account_id, account, developer_access_request, registered_apps, error, new_app):
  """Render the developer settings tab directly (used after form submission)."""
  return render_template(
    "settings/index.html",
    active_tab="developer",
    account_id=account_id,
    account=account,
    developer_access_request=developer_access_request,
    registered_apps=registered_apps,
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
    draft_reply_enabled=False,
    draft_reply_has_access=False,
    crm_connection=None,
    crm_prefill={},
    linkedin_connection=None,
    twitter_connection=None,
  )
