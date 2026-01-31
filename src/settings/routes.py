from datetime import datetime
from uuid import uuid4

from flask import current_app, g, jsonify, redirect, render_template, request, url_for

from src.extensions import db
from src.models import IntakeToken, User, Passkey, TOTPDevice, Account, InboxConnection
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
  allowed = {"team", "profile", "billing", "security", "integrations", "features"}
  if tab not in allowed:
    tab = "team"
  passkeys = []
  totp_devices = []
  account_id = getattr(g, "current_account_id", None)
  account = Account.query.get(account_id) if account_id else None
  seats_used = User.query.filter_by(account_id=account_id).count() if account_id else 0
  seats_limit = account.seats_limit if account else None

  # Get draft reply feature status for features tab
  draft_reply_enabled = False
  draft_reply_has_access = False
  if tab == "features" and account_id:
    from src.models import AccountFeatureFlags
    from src.features import check_draft_reply_access

    feature_flags = AccountFeatureFlags.query.filter_by(account_id=account_id).first()
    draft_reply_enabled = feature_flags.draft_reply_enabled if feature_flags else False
    draft_reply_has_access = check_draft_reply_access(account_id)

  if tab == "security":
    user = getattr(g, "current_user", None)
    if user:
      passkeys = Passkey.query.filter_by(user_id=user.id).all()
      totp_devices = TOTPDevice.query.filter_by(user_id=user.id).all()
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
    draft_reply_enabled=draft_reply_enabled,
    draft_reply_has_access=draft_reply_has_access,
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
  from src.billing.models import CustomerBillingProfile
  profile = CustomerBillingProfile.query.filter_by(account_id=account_id).first() if account_id else None
  current_plan = profile.plan_choice if profile else None

  plan_change_message = None
  plan_change_status = None

  if request.method == "POST":
    current_app.logger.info(f"[billing_plan] POST request from account {account_id}, form data: {dict(request.form)}, cookies: {list(request.cookies.keys())}")
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


@bp.route("/integrations/webhooks", methods=["GET", "POST"])
@login_required_settings
def integrations_webhooks():
  import hashlib
  from werkzeug.utils import secure_filename
  from src.uploads import upload_bytes

  user = getattr(g, "current_user", None)
  account_id = getattr(g, "current_account_id", None)
  api_allowed = account_allows_api(account_id) if account_id else False
  voice_connection = None
  voice_prefill = {"account_sid": "", "webhook_url": ""}
  if account_id:
    voice_connection = InboxConnection.query.filter_by(account_id=account_id, provider="voice").first()
    if voice_connection and voice_connection.metadata_json:
      meta = voice_connection.metadata_json
      if meta.get("account_sid_enc"):
        voice_prefill["account_sid"] = decrypt_value(meta.get("account_sid_enc")) or ""
      elif meta.get("account_sid"):
        voice_prefill["account_sid"] = meta.get("account_sid") or ""
      if meta.get("webhook_url_enc"):
        voice_prefill["webhook_url"] = decrypt_value(meta.get("webhook_url_enc")) or ""
      elif meta.get("webhook_url"):
        voice_prefill["webhook_url"] = meta.get("webhook_url") or ""
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

    if action == "save_voice" and account_id:
      provider = (request.form.get("voice_provider") or "twilio").strip().lower()
      account_sid = (request.form.get("twilio_account_sid") or "").strip()
      auth_token = (request.form.get("twilio_auth_token") or "").strip()
      webhook_url = (request.form.get("voice_webhook_url") or "").strip()
      status = "connected" if (account_sid or webhook_url or auth_token) else "pending"

      metadata = (voice_connection.metadata_json or {}) if voice_connection else {}
      metadata.update(
        {
          "channel": "voice",
          "provider": provider or "twilio",
        }
      )
      if account_sid:
        metadata["account_sid_enc"] = encrypt_value(account_sid)
        metadata.pop("account_sid", None)
      if webhook_url:
        metadata["webhook_url_enc"] = encrypt_value(webhook_url)
        metadata.pop("webhook_url", None)
      if auth_token:
        metadata["auth_token_enc"] = encrypt_value(auth_token)

      file = request.files.get("voice_csv")
      if file and file.filename:
        filename = secure_filename(file.filename or "")
        data = file.read()
        if data:
          uploads_bucket = current_app.config.get("UPLOADS_BUCKET")
          uploads_host = current_app.config.get("UPLOADS_HOST")
          if not uploads_bucket or not uploads_host:
            return jsonify({"error": "uploads_not_configured"}), 503
          if len(data) > 10 * 1024 * 1024:
            return jsonify({"error": "file_too_large", "max_bytes": 10 * 1024 * 1024}), 413
          key = f"public/{uuid4().hex}_{filename}"
          url = upload_bytes(
            key=key,
            data=data,
            content_type=file.mimetype or "text/csv",
            content_disposition=f'attachment; filename="{filename}"',
          )
          metadata["csv_upload"] = {"key": key, "url": url, "filename": filename}

      if voice_connection:
        voice_connection.metadata_json = metadata
        voice_connection.status = status
      else:
        voice_connection = InboxConnection(
          user_id=user.id if user else None,
          account_id=account_id,
          provider="voice",
          status=status,
          metadata_json=metadata,
        )
        db.session.add(voice_connection)
      db.session.commit()
      return render_template(
        "settings/index.html",
        active_tab="integrations",
        integrations_view="webhooks",
        intake_token_set=bool(IntakeToken.query.filter_by(account_id=account_id, revoked_at=None).all()),
        tokens=IntakeToken.query.filter_by(account_id=account_id, revoked_at=None).all(),
        new_token=None,
        team_view=None,
        billing_view=None,
        security_view=None,
        api_allowed=api_allowed,
        account_id=account_id,
        voice_connection=voice_connection,
        voice_prefill=voice_prefill,
        voice_saved=True,
      )
    if action == "generate" and account_id and api_allowed:
      token_value = str(uuid4())
      token_hash = hashlib.sha256(token_value.encode("utf-8")).hexdigest()
      token = IntakeToken(
        account_id=account_id,
        label=label,
        token_hash=token_hash,
        allowed_ips=allowed_ips,
        expires_at=expires_at,
      )
      db.session.add(token)
      db.session.commit()
      return render_template(
        "settings/index.html",
        active_tab="integrations",
        integrations_view="webhooks",
        intake_token_set=True,
        tokens=IntakeToken.query.filter_by(account_id=account_id, revoked_at=None).all(),
        new_token=token_value,
        team_view=None,
        billing_view=None,
        security_view=None,
        api_allowed=api_allowed,
        account_id=account_id,
        voice_connection=voice_connection,
        voice_prefill=voice_prefill,
      )
  active_tokens = IntakeToken.query.filter_by(account_id=account_id, revoked_at=None).all() if account_id else []
  intake_token_set = bool(active_tokens)
  return render_template(
    "settings/index.html",
    active_tab="integrations",
    integrations_view="webhooks",
    intake_token_set=intake_token_set,
    tokens=active_tokens,
    new_token=None,
    team_view=None,
    billing_view=None,
    security_view=None,
    api_allowed=api_allowed,
    account_id=account_id,
    voice_connection=voice_connection,
    voice_prefill=voice_prefill,
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

            from src.kb_integrations import process_uploaded_files
            result = process_uploaded_files(files, account_id)

            if result["success"] > 0:
                flash(f"Successfully uploaded {result['success']} articles", "success")
            if result["failed"] > 0:
                for error in result["errors"][:5]:  # Show first 5 errors
                    flash(error, "error")

            return redirect(url_for("settings.knowledge_base_integration"))

        elif action == "delete_article":
            article_id = request.form.get("article_id")
            from src.kb_integrations import delete_kb_article
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
