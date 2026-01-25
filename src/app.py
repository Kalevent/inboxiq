import os
from functools import wraps
from uuid import uuid4

from flask import Flask, jsonify, render_template, current_app, request, redirect, url_for, g, abort
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity, get_jwt
from src.config import Config, DevelopmentConfig, ProductionConfig, TestConfig
from src.extensions import db, migrate, jwt, cache, limiter
from src.crash_report import configure_crash_email
from flask_cors import CORS
from src.models import Account, User, Ticket, InboxConnection, BlogPost, Feedback, IntakeToken  # noqa: F401  # ensure models are registered
from src.auth import bp as auth_bp
from src.users import bp as users_bp
from src.accounts import bp as accounts_bp
from src.api import bp as api_bp
from src.docs import bp as docs_bp
from src.blog import bp as blog_bp
from src.settings import bp as settings_bp
from src.publishing import bp as publishing_bp
from src.api.v1.access_control import account_allows_api

from src.email_utils import send_test_email as send_test_email_util, send_onboarding_reminder
from src.crash_report import configure_crash_email
from datetime import datetime, timezone, timedelta


def create_app() -> Flask:
  """Create and configure the Flask application."""
  app = Flask(__name__)
  env = (os.getenv("APP_ENV") or "").lower()
  if env in ("prod", "production"):
    app.config.from_object(ProductionConfig)
  elif env in ("test", "testing"):
    app.config.from_object(TestConfig)
  else:
    app.config.from_object(DevelopmentConfig)

  db.init_app(app)
  migrate.init_app(app, db, directory=app.config.get("MIGRATION_DIR"))
  jwt.init_app(app)
  cache.init_app(app)
  ratelimit_uri = (
    app.config.get("RATELIMIT_STORAGE_URI")
    or app.config.get("LIMITER_STORAGE_URL")
    or "memory://"
  )
  ratelimit_defaults_raw = app.config.get("RATELIMIT_DEFAULTS")
  ratelimit_defaults = []
  if ratelimit_defaults_raw:
    ratelimit_defaults = [limit.strip() for limit in ratelimit_defaults_raw.split(",") if limit.strip()]
  app.config["RATELIMIT_STORAGE_URI"] = ratelimit_uri
  app.config["RATELIMIT_DEFAULTS"] = ratelimit_defaults
  app.config["RATELIMIT_HEADERS_ENABLED"] = app.config.get("RATELIMIT_HEADERS_ENABLED", True)
  limiter.init_app(app)
  configure_crash_email(app)

  cors_origins_raw = app.config.get("CORS_ORIGINS", "")
  cors_origins = [o.strip() for o in cors_origins_raw.split(",") if o.strip()]
  if cors_origins:
    # Allow CORS for auth and API endpoints from trusted origins.
    CORS(
      app,
      resources={
        r"/auth/*": {"origins": cors_origins},
        r"/api/*": {"origins": cors_origins},
      },
      supports_credentials=True,
    )

  @app.after_request
  def set_security_headers(response):
    csp = "; ".join(
      [
        "default-src 'self'",
        "script-src 'self' 'unsafe-inline' https://js.stripe.com",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: https://www.gravatar.com",
        "font-src 'self'",
        "connect-src 'self' https://127.0.0.1:8000 https://api.kalevent.com https://files.kalevent.com",
        "form-action 'self'",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "object-src 'none'",
        "frame-src 'self' https://js.stripe.com",
      ]
    )
    response.headers.setdefault("Content-Security-Policy", csp)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response

  @app.context_processor
  def inject_user_meta():
    user = getattr(g, "current_user", None)
    email = getattr(user, "email", None)
    default_admin = "support@kalevent.com"
    allowed = set(
        e.strip().lower()
        for e in (app.config.get("ADMIN_EMAILS", "") or default_admin).split(",")
        if e.strip()
    )
    has_admin_access = bool(user and email and ((not allowed) or (email.lower() in allowed)))
    avatar_url = None
    if email:
      import hashlib
      digest = hashlib.md5(email.lower().encode("utf-8")).hexdigest()
      avatar_url = f"https://www.gravatar.com/avatar/{digest}?s=96&d=identicon&f=y"
    return {
        "current_user": user,
        "avatar_url": avatar_url or url_for("static", filename="svgs/card.svg"),
        "has_admin_access": has_admin_access,
        "csrf_token_value": request.cookies.get("csrf_access_token") or request.cookies.get("csrf_refresh_token") or "",
    }

  def _redirect_to_login():
    login_url = url_for("login_page")
    next_param = request.path if request.path and request.path != "/login" else None
    if next_param:
      return redirect(f"{login_url}?next={next_param}")
    return redirect(login_url)

  def _load_current_user():
    """Validate JWT cookies/headers and return the user and account id."""
    try:
      # Validate JWT from cookies/headers; CSRF enforcement is disabled in dev via config.
      verify_jwt_in_request()
    except Exception as exc:
      cookie_keys = list((request.cookies or {}).keys())
      current_app.logger.warning({"event": "auth.load_user_failed", "reason": str(exc), "cookies": cookie_keys})
      return None, None
    claims = get_jwt() or {}
    raw_user_id = get_jwt_identity()
    raw_account_id = claims.get("account_id")
    try:
      user_id = int(raw_user_id) if raw_user_id is not None else None
    except (TypeError, ValueError):
      user_id = None
    try:
      account_id = int(raw_account_id) if raw_account_id is not None else None
    except (TypeError, ValueError):
      account_id = None
    if not user_id:
      current_app.logger.warning(
          {
              "event": "auth.load_user_failed",
              "reason": "no user_id",
              "cookies": list((request.cookies or {}).keys()),
          }
      )
      return None, None
    user = db.session.get(User, user_id)
    if not user:
      current_app.logger.warning(
          {
              "event": "auth.load_user_failed",
              "reason": "user not found",
              "user_id": user_id,
              "account_id": account_id,
              "cookies": list((request.cookies or {}).keys()),
          }
      )
      return None, None
    return user, account_id or user.account_id

  def login_required_page(view_func):
    """Require a valid JWT for HTML pages and redirect to login when missing/invalid."""
    @wraps(view_func)
    def wrapper(*args, **kwargs):
      user, account_id = _load_current_user()
      if not user:
        try:
          from flask import current_app as app_ctx
          app_ctx.logger.warning(
              {
                  "event": "auth.page_redirect",
                  "reason": "no user",
                  "path": request.path,
                  "cookies": list((request.cookies or {}).keys()),
              }
          )
        except Exception:
          pass
        return _redirect_to_login()
      g.current_user = user
      g.current_account_id = account_id

      # If trial expired and account is not allowed for API/Business, redirect to upgrade (except on upgrade itself).
      if account_id and request.path not in {"/upgrade"}:
        if not account_allows_api(account_id):
          return redirect(url_for("upgrade", trial="ended"))

      return view_func(*args, **kwargs)
    return wrapper

  def _billing_profile(account_id: int | None):
    if not account_id:
      return None
    try:
      from src.billing.models import CustomerBillingProfile
      return CustomerBillingProfile.query.filter_by(account_id=account_id).first()
    except Exception:
      return None

  app.register_blueprint(auth_bp)
  app.register_blueprint(users_bp)
  app.register_blueprint(accounts_bp)
  app.register_blueprint(api_bp)
  app.register_blueprint(docs_bp)
  app.register_blueprint(blog_bp)
  app.register_blueprint(settings_bp)
  app.register_blueprint(publishing_bp)


  @app.route("/", methods=["GET"])
  def root():
    return render_template("index.html")

  @app.route("/home", methods=["GET"])
  def redirect_home():
    # Permanent redirect to canonical root.
    return redirect(url_for("root"), code=301)

  @app.route("/favicon.ico")
  def favicon():
    return current_app.send_static_file("favicon.svg")

  @app.route("/privacy")
  def privacy():
    return render_template("privacy_policy.html")

  @app.route("/terms")
  def terms():
    return render_template("terms_of_service.html")

  @app.route("/contact")
  def contact():
    return render_template("contact.html")
  
  # Marketing endpoints
  @app.get("/email-triage")
  def email_triage():
    return render_template("marketing/email_triage.html")

  @app.get("/ai-email-triage")
  def ai_email_triage():
    return render_template("marketing/ai_email_triage.html")

  @app.get("/shared-inbox")
  def shared_inbox():
    return render_template("marketing/shared_inbox.html")

  @app.get("/support-automation")
  def support_automation():
    return render_template("marketing/support_automation.html")
  
  @app.get("/playbook/unified-support-triage")
  def playbook():
    return render_template("marketing/unified-support-triage.html")
  
  @app.get("/playbook/unified-sales-intake")
  def playbook_sales():
    return render_template("marketing/unified-sales-intake.html")

  @app.get("/playbook/unified-ops-intake")
  def playbook_ops():
    return render_template("marketing/unified-ops-intake.html")

  @app.get("/playbook/unified-intake-system")
  def playbook_intake_system():
    return render_template("marketing/unified-intake-system.html")

  @app.route("/robots.txt")
  def robots_txt():
    # Serve SEO-friendly robots.txt at the root.
    return current_app.send_static_file("robots.txt")

  @app.route("/sitemap.xml")
  def sitemap():
    # Serve sitemap at the canonical root URL for search engines.
    return current_app.send_static_file("sitemap.xml")

  @app.route("/upgrade")
  @login_required_page
  def upgrade():
    return render_template("billing_upgrade.html", stripe_pk=current_app.config.get("STRIPE_PUBLISHABLE_KEY"))

  @app.route("/onboarding", methods=["GET"])
  @login_required_page
  def onboarding_page():
    return render_template("onboarding.html")

  @app.route("/dashboard", methods=["GET"])
  @login_required_page
  def dashboard_home():
    account_id = getattr(g, "current_account_id", None)
    user = getattr(g, "current_user", None)
    if not account_id or not user:
      return _redirect_to_login()

    billing_profile = _billing_profile(account_id)
    if billing_profile:
      trial_ended = billing_profile.trial_status == "ended" and billing_profile.subscription_status in ("none", "trialing", "canceled")
      if trial_ended and request.path != url_for("upgrade"):
        return redirect(url_for("upgrade", trial="ended"))
    today = datetime.now(timezone.utc).date()
    recent = (
      Ticket.query.filter_by(account_id=account_id)
      .order_by(Ticket.created_at.desc())
      .limit(5)
      .all()
    )
    tickets_today = sum(1 for t in recent if t.created_at and t.created_at.date() == today)
    total_tickets = Ticket.query.filter_by(account_id=account_id).count()
    triaged_count = total_tickets
    missed = 0  # placeholder metric; adjust when inbox polling is wired
    def _pick_connection(connections):
      if not connections:
        return None
      def _poll_ts(conn):
        meta = conn.metadata_json or {}
        ts = meta.get("last_poll_at")
        if not ts:
          return None
        try:
          ts_raw = str(ts)
          if ts_raw.endswith("Z"):
            ts_raw = ts_raw[:-1] + "+00:00"
          parsed = datetime.fromisoformat(ts_raw)
          if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
          return parsed
        except Exception:
          return None
      # Prefer latest poll timestamp; fall back to updated_at.
      return max(
        connections,
        key=lambda c: (_poll_ts(c) or datetime.min.replace(tzinfo=timezone.utc), c.updated_at or datetime.min.replace(tzinfo=timezone.utc)),
      )

    account_connections = InboxConnection.query.filter_by(account_id=account_id, status="connected").all()
    last_connection = _pick_connection(account_connections)
    if not last_connection:
      user_connections = InboxConnection.query.filter_by(user_id=user.id, status="connected").all()
      last_connection = _pick_connection(user_connections)
    last_poll = (last_connection.metadata_json or {}).get("last_poll_at") if last_connection else None
    last_poll_status = (last_connection.metadata_json or {}).get("last_poll_status") if last_connection else None
    last_poll_error = (last_connection.metadata_json or {}).get("last_poll_error") if last_connection else None
    last_poll_counts = (last_connection.metadata_json or {}).get("last_poll_counts") if last_connection else None
    # Fallback: if counts or status exist but timestamp is missing, use updated_at as best-effort display.
    if (
      not last_poll
      and last_connection
      and last_connection.updated_at
      and (last_poll_counts or (last_poll_status and last_poll_status != "never"))
    ):
      last_poll = last_connection.updated_at.isoformat()
    connection_provider = getattr(last_connection, "provider", None)
    connection_email = getattr(last_connection, "email_address", None)
    connection_status = getattr(last_connection, "status", None)
    connection_id = getattr(last_connection, "id", None)
    banner_first_batch = total_tickets >= 5
    allowed = set(
      e.strip().lower()
      for e in (current_app.config.get("ADMIN_EMAILS", "") or "").split(",")
      if e.strip()
    )
    has_admin_access = bool(user and user.email and ((not allowed) or (user.email.lower() in allowed)))

    # Build work queue groupings to match the UI sections (action required, optional, auto-handled).
    def _sla_display(priority: str | None) -> str:
      mapping = {"P0": "2h", "P1": "4h", "P2": "24h"}
      return mapping.get((priority or "").upper(), "24h")

    def _ai_reason(decision: dict, fallback: str) -> str:
      return decision.get("ai_reason") or decision.get("reason") or fallback

    def _action_reason_text(flag) -> str:
      if flag is True:
        return "Action required — customer needs help."
      if flag == "optional":
        return "Optional follow-up when capacity allows."
      if flag is False:
        return "Informational / auto-handled."
      return "Queued for review."

    def _parse_scope(scope: str | None):
      scope = (scope or "today").lower()
      now = datetime.now(timezone.utc)
      if scope == "last_24_hours":
        return scope, now - timedelta(hours=24)
      if scope == "last_7_days":
        return scope, now - timedelta(days=7)
      if scope == "all_time":
        return scope, None
      return "today", now.replace(hour=0, minute=0, second=0, microsecond=0)

    scope, created_after = _parse_scope(request.args.get("scope"))
    query = Ticket.query.filter_by(account_id=account_id)
    if created_after:
      query = query.filter(Ticket.created_at >= created_after)
    all_tickets = query.order_by(Ticket.created_at.desc()).limit(200).all()

    action_required_tickets = []
    optional_tickets = []
    auto_handled_items = []

    for t in all_tickets:
      decision = t.decision or {}
      needs_review = bool(decision.get("needs_review") or (t.status == "needs_review"))
      priority = (t.priority or decision.get("priority") or "P2").upper()
      sentiment = (t.sentiment or decision.get("sentiment") or "neutral").lower()
      risk_flag = bool(decision.get("risk_flag"))
      auto_handled_flag = bool(decision.get("auto_handled") or (t.status == "auto_handled"))
      action_required = t.action_required
      if action_required is None and auto_handled_flag:
        action_required = False  # backwards compatibility when decision lacked explicit field
      # Honor explicit status overrides from the ticket view.
      if t.status == "auto_handled":
        action_required = False
      if t.status == "optional":
        action_required = "optional"

      ticket_view = {
        "id": t.id,
        "priority": priority,
        "subject": t.subject,
        "category": t.category or decision.get("category") or "general",
        "intent": decision.get("intent") or "general",
        "sentiment": sentiment or "neutral",
        "provider": t.provider or decision.get("provider"),
        "ai_reason": _ai_reason(decision, _action_reason_text(action_required)),
        "owner": t.owner or decision.get("owner") or "Support",
        "due_at": t.due_at,
        "sla": _sla_display(priority),
        "url": url_for("ticket_detail", ticket_id=t.id),
        "provider_url": t.provider_thread_url or decision.get("url"),
      }

      if action_required is True:
        action_required_tickets.append(ticket_view)
      elif action_required == "optional" or needs_review:
        ticket_view["ai_reason"] = _ai_reason(decision, _action_reason_text("optional"))
        optional_tickets.append(ticket_view)
      elif action_required is False or auto_handled_flag or (priority == "P2" and sentiment == "neutral" and not risk_flag):
        ticket_view["ai_reason"] = _ai_reason(decision, _action_reason_text(False))
        auto_handled_items.append(ticket_view)
      else:
        action_required_tickets.append(ticket_view)

    action_required_count = len(action_required_tickets)
    optional_count = len(optional_tickets)
    auto_handled_count = len(auto_handled_items)
    email_providers = {
      "gmail",
      "outlook",
      "imap",
      "email",
      "google",
      "gsuite",
      "google_oauth",
      "ms_graph",
      "microsoft",
      "office365",
      "exchange",
      "ews",
      "smtp",
    }
    auto_handled_email_count = sum(
      1 for t in auto_handled_items
      if (t.get("provider") or "").lower() in email_providers
    )
    auto_handled_other_count = auto_handled_count - auto_handled_email_count
    total_for_metrics = action_required_count + optional_count + auto_handled_count
    triage_eliminated_pct = round((auto_handled_count / total_for_metrics) * 100, 1) if total_for_metrics else 0.0
    actionable_today = action_required_count
    auto_handled_today = auto_handled_count

    return render_template(
      "dashboard_welcome.html",
      recent_tickets=recent,
      tickets_today=tickets_today,
      total_tickets=total_tickets,
      triaged_count=triaged_count,
      missed_emails=missed,
      action_required_tickets=action_required_tickets,
      optional_tickets=optional_tickets,
      auto_handled_items=auto_handled_items,
      action_required_count=action_required_count,
      optional_count=optional_count,
      auto_handled_email_count=auto_handled_email_count,
      auto_handled_other_count=auto_handled_other_count,
      actionable_today=actionable_today,
      auto_handled_today=auto_handled_today,
      triage_eliminated_pct=triage_eliminated_pct,
      banner_first_batch=banner_first_batch,
      last_poll_at=last_poll,
      last_poll_status=last_poll_status,
      last_poll_error=last_poll_error,
      last_poll_counts=last_poll_counts,
      connection_id=connection_id,
      connection_provider=connection_provider,
      connection_email=connection_email,
      connection_status=connection_status,
      has_admin_access=has_admin_access,
      scope=scope,
    )

  @app.route("/home", methods=["GET"])
  def legacy_home_redirect():
    return redirect(url_for("dashboard_home"))

  @app.route("/admin", methods=["GET"])
  @login_required_page
  def admin_page():
    user = getattr(g, "current_user", None)
    email = getattr(user, "email", "").lower() if user else ""
    default_admin = "support@kalevent.com"
    allowed = set(
      e.strip().lower()
      for e in (current_app.config.get("ADMIN_EMAILS", "") or default_admin).split(",")
      if e.strip()
    )
    if not user or (allowed and email not in allowed):
      return redirect(url_for("dashboard_home"))
    return render_template("admin.html")

  @app.route("/api/test-email", methods=["POST"])
  def send_test_email():
    data = request.get_json(silent=True) or {}
    to_email = (data.get("to_email") or "").strip()
    if not to_email:
        return jsonify({"error": "to_email is required"}), 400
    ok = send_test_email_util(to_email)
    if not ok:
        return jsonify({"error": "Unable to send test email. Check SMTP configuration."}), 502
    triage_samples = [
        {
            "subject": "Overcharged on invoice",
            "category": "Billing",
            "priority": "High",
            "sentiment": "Frustrated",
            "ticket": "#8831",
            "created_at": datetime.now(timezone.utc).isoformat() + "Z",
        },
        {
            "subject": "Feature request: bulk export",
            "category": "Feature Request",
            "priority": "Normal",
            "sentiment": "Neutral",
            "ticket": "#8832",
            "created_at": datetime.now(timezone.utc).isoformat() + "Z",
        },
    ]
    return jsonify({"message": f"Test email sent to {to_email}", "triage": triage_samples}), 200

  @app.route("/api/reminder-email", methods=["POST"])
  def send_reminder_email():
    data = request.get_json(silent=True) or {}
    to_email = (data.get("to_email") or "").strip()
    stage_raw = data.get("stage")
    if not to_email:
        return jsonify({"error": "to_email is required"}), 400
    try:
        stage = int(stage_raw)
    except (TypeError, ValueError):
        return jsonify({"error": "stage must be an integer (1, 2, or 3)"}), 400
    ok = send_onboarding_reminder(to_email, stage)
    if not ok:
        return jsonify({"error": "Unable to send reminder email. Check SMTP configuration or stage value."}), 502
    return jsonify({"message": f"Reminder email (stage {stage}) sent to {to_email}"}), 200

  @app.route("/login", methods=["GET"])
  def login_page():
    return render_template("login.html")

  @app.route("/tickets/<ticket_id>", methods=["GET", "POST"])
  @login_required_page
  def ticket_detail(ticket_id: str):
    user = getattr(g, "current_user", None)
    account_id = getattr(g, "current_account_id", None)
    ticket = Ticket.query.filter_by(id=ticket_id, account_id=account_id).first()
    if not ticket:
      abort(404)

    if request.method == "POST":
      form = request.form or {}
      status_vals = form.getlist("status")
      status = (status_vals[-1] if status_vals else "").strip() or ticket.status
      category = (form.get("category") or "").strip() or ticket.category
      priority = (form.get("priority") or "").strip() or ticket.priority
      sentiment = (form.get("sentiment") or "").strip() or ticket.sentiment
      intent = (form.get("intent") or "").strip() or (ticket.decision or {}).get("intent")
      owner = (form.get("owner") or "").strip() or ticket.owner
      team = (form.get("team") or "").strip() or ticket.team
      assigned_to = (form.get("assigned_to") or "").strip() or ticket.assigned_to
      note = (form.get("note") or "").strip()
      raw_action_required = (form.get("action_required") or "").strip().lower()
      if raw_action_required == "true":
        action_required_value = True
      elif raw_action_required == "false":
        action_required_value = False
      elif raw_action_required == "optional":
        action_required_value = "optional"
      else:
        action_required_value = (ticket.decision or {}).get("action_required")

      # Status should drive action_required to stay consistent, even if the dropdown wasn't touched.
      if status == "auto_handled":
        action_required_value = False
      elif status == "optional" and action_required_value is None:
        action_required_value = "optional"

      ticket.status = status
      ticket.category = category
      ticket.priority = priority
      ticket.sentiment = sentiment
      ticket.owner = owner
      ticket.team = team
      ticket.assigned_to = assigned_to
      ticket.manual_override = True
      ticket.action_required = action_required_value

      # Keep status/action_required in sync for downstream dashboards/metrics,
      # but do not override explicit closure.
      if ticket.status != "closed":
        if action_required_value is False:
          ticket.status = "auto_handled"
        elif action_required_value == "optional" and ticket.status != "needs_review":
          ticket.status = "optional"
        elif action_required_value is True and ticket.status == "auto_handled":
          ticket.status = "new"

      decision = ticket.decision or {}
      decision["intent"] = intent or decision.get("intent")
      decision["action_required"] = action_required_value
      decision["human_override"] = {
        "status": status,
        "category": category,
        "priority": priority,
        "sentiment": sentiment,
        "intent": decision.get("intent"),
        "owner": owner,
        "team": team,
        "assigned_to": assigned_to,
        "action_required": action_required_value,
      }
      ticket.decision = decision

      overrides = ticket.override_metadata or {}
      human_updates = overrides.get("human_updates") or []
      human_updates.append(
        {
          "note": note or "Updated ticket",
          "updated_by": user.email if user else "unknown",
          "updated_at": datetime.now(timezone.utc).isoformat(),
          "status": status,
          "category": category,
          "priority": priority,
          "sentiment": sentiment,
          "intent": decision.get("intent"),
          "owner": owner,
          "team": team,
          "assigned_to": assigned_to,
          "action_required": action_required_value,
        }
      )
      overrides["human_updates"] = human_updates
      ticket.override_metadata = overrides

      db.session.add(ticket)
      db.session.commit()
      return redirect(url_for("ticket_detail", ticket_id=ticket.id))

    # expose latest human updates for display
    history = (ticket.override_metadata or {}).get("human_updates") or []
    return render_template("ticket.html", ticket=ticket, history=history)

  @app.route("/feedback/<feedback_id>", methods=["GET"])
  @login_required_page
  def feedback_detail(feedback_id: str):
    account_id = getattr(g, "current_account_id", None)
    feedback = Feedback.query.filter_by(id=feedback_id, account_id=account_id).first()
    if not feedback:
      abort(404)

    decision = feedback.ai_decision_json or {}
    metadata = feedback.metadata_json or {}
    linked_ticket = Ticket.query.filter_by(id=feedback.ticket_id, account_id=account_id).first() if feedback.ticket_id else None

    return render_template(
      "feedback.html",
      feedback=feedback,
      decision=decision,
      metadata=metadata,
      linked_ticket=linked_ticket,
    )

  @app.route("/activate", methods=["GET"])
  def activate_page():
    return render_template("activate.html")

  @app.route("/reset", methods=["GET"])
  def reset_page():
    return render_template("reset.html")

  @app.route('/health', methods=['GET'])
  def health():
    return jsonify({'status': 'ok'}), 200
  
  @app.route('/cached-status', methods=['GET'])
  @cache.cached(timeout=60)
  def cached_status():
    return jsonify({'status': 'ok', 'cached': True}), 200

  @app.errorhandler(429)
  def ratelimit_handler(e):
    return jsonify({"error": "too many requests", "details": str(e.description)}), 429

  return app
