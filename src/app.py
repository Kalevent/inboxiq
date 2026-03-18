import os
from functools import wraps
from uuid import uuid4

from flask import Flask, jsonify, render_template, current_app, request, redirect, url_for, g, abort
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity, get_jwt
from src.config import Config, DevelopmentConfig, ProductionConfig, TestConfig
from src.extensions import db, migrate, jwt, cache, limiter
from src.monitoring.crash_report import configure_crash_email
from flask_cors import CORS
from src.models.content import BlogPost  # noqa: F401  # ensure models are registered
from src.models.core import Account, User, InboxConnection  # noqa: F401  # ensure models are registered
from src.models.misc import Feedback  # noqa: F401  # ensure models are registered
from src.models.tickets import Ticket  # noqa: F401  # ensure models are registered
from src.admin import bp as admin_bp
from src.auth import bp as auth_bp
from src.users import bp as users_bp
from src.accounts import bp as accounts_bp
from src.api import bp as api_bp
from src.docs import bp as docs_bp
from src.kb import bp as kb_bp
from src.blog import bp as blog_bp
from src.settings import bp as settings_bp
from src.publishing import bp as publishing_bp
from src.funnel.routes import funnel_bp
from src.automation.studio import bp as automation_studio_bp
from src.social_auth import bp as social_auth_bp
from src.landing_pages.routes import bp as landing_pages_bp
from src.marketing_ops.routes import marketing_bp
from src.api.v1.audit import audit_bp
from src.api.v1.access_control import account_allows_api

from src.notifications.emails import send_test_email as send_test_email_util, send_onboarding_reminder
from src.monitoring.crash_report import configure_crash_email
from datetime import datetime, timezone, timedelta


def create_app() -> Flask:
  """Create and configure the Flask application."""
  from werkzeug.middleware.proxy_fix import ProxyFix
  app = Flask(__name__)
  # Trust X-Forwarded-Proto/Host from the AWS ALB (one hop) so url_for(_external=True)
  # produces https:// URLs instead of http://.
  app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
  env = (os.getenv("APP_ENV") or "").lower()
  if env in ("prod", "production"):
    app.config.from_object(ProductionConfig)
  elif env in ("test", "testing"):
    app.config.from_object(TestConfig)
  else:
    app.config.from_object(DevelopmentConfig)

  def _env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
      return default
    return val.lower() in ("1", "true", "yes", "on")

  def _validate_required_env() -> None:
    """Fail fast on missing required env in production to avoid silent breakage."""
    if env not in ("prod", "production"):
      return

    if not _env_bool("DSPY_ENABLED", False):
      return

    provider = (os.getenv("DSPY_PROVIDER") or "").strip().lower()
    if not provider:
      if _env_bool("DSPY_USE_OPENAI", False):
        provider = "openai"
      elif _env_bool("DSPY_USE_ANTHROPIC", False):
        provider = "anthropic"
      elif _env_bool("DSPY_USE_GEMINI", False):
        provider = "gemini"

    if not provider:
      raise RuntimeError("DSPy provider missing. Set DSPY_PROVIDER or DSPY_USE_OPENAI/ANTHROPIC/GEMINI.")

    if provider == "openai" and not os.getenv("OPENAI_API_KEY"):
      raise RuntimeError("OPENAI_API_KEY missing for DSPy OpenAI provider.")
    if provider == "anthropic" and not os.getenv("ANTHROPIC_API_KEY"):
      raise RuntimeError("ANTHROPIC_API_KEY missing for DSPy Anthropic provider.")
    if provider in {"gemini", "google"} and not os.getenv("GEMINI_API_KEY"):
      raise RuntimeError("GEMINI_API_KEY missing for DSPy Gemini provider.")

  _validate_required_env()

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

  # Initialize OpenTelemetry (must be after Flask app + extensions init)
  from src.monitoring.observability import init_otel
  init_otel(app, service_name="inboxiq-flask")

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
        "img-src 'self' data: https://www.gravatar.com https://files.kalevent.com",
        "font-src 'self' data:",
        "connect-src 'self' https://127.0.0.1:8000 https://api.kalevent.com https://files.kalevent.com",
        "form-action 'self'",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "object-src 'none'",
        "frame-src 'self' https://js.stripe.com",
        "upgrade-insecure-requests",
        "block-all-mixed-content",
      ]
    )
    response.headers.setdefault("Content-Security-Policy", csp)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("X-XSS-Protection", "1; mode=block")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
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
    csrf_token_val = request.cookies.get("csrf_access_token") or request.cookies.get("csrf_refresh_token") or ""
    from datetime import datetime, timezone
    return {
        "current_user": user,
        "avatar_url": avatar_url or url_for("static", filename="svgs/card.svg"),
        "has_admin_access": has_admin_access,
        "csrf_token_value": csrf_token_val,
        "csrf_token": lambda: csrf_token_val,  # Function for templates to call csrf_token()
        "current_year": datetime.now(timezone.utc).year,
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
    # Block access for soft-deleted accounts
    resolved_account_id = account_id or user.account_id
    if resolved_account_id:
      from src.models.core import Account as _Account
      acct = db.session.get(_Account, resolved_account_id)
      if acct and acct.is_deleted:
        current_app.logger.warning({
            "event": "auth.load_user_failed",
            "reason": "account_deleted",
            "user_id": user_id,
            "account_id": resolved_account_id,
        })
        return None, None
    return user, resolved_account_id

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
      from src.models.billing import CustomerBillingProfile
      return CustomerBillingProfile.query.filter_by(account_id=account_id).first()
    except Exception:
      return None

  app.register_blueprint(admin_bp)
  app.register_blueprint(auth_bp)
  app.register_blueprint(users_bp)
  app.register_blueprint(accounts_bp)
  app.register_blueprint(api_bp)
  app.register_blueprint(docs_bp)
  app.register_blueprint(kb_bp)
  app.register_blueprint(blog_bp)
  app.register_blueprint(settings_bp)
  app.register_blueprint(publishing_bp)
  app.register_blueprint(funnel_bp)
  app.register_blueprint(automation_studio_bp)
  app.register_blueprint(social_auth_bp)
  app.register_blueprint(landing_pages_bp, url_prefix="/lp")
  app.register_blueprint(marketing_bp)
  app.register_blueprint(audit_bp)

  # Register SEO cleanup handlers for old URLs
  from src.marketing.seo_cleanup import register_seo_cleanup
  register_seo_cleanup(app)

  @app.route("/", methods=["GET"])
  def root():
    return render_template("index.html")

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

  @app.route("/security")
  def security():
    return render_template("security.html")


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

  # Use case pages
  @app.get("/use-cases/support")
  def use_case_support():
    return render_template("marketing/use_case_support.html")

  @app.get("/use-cases/healthcare-triage")
  def use_case_healthcare_triage():
    return render_template("marketing/use_case_healthcare_triage.html")

  @app.get("/use-cases/claims")
  def use_case_claims():
    return render_template("marketing/use_case_claims.html")

  @app.get("/use-cases/hr")
  def use_case_hr():
    return render_template("marketing/use_case_hr.html")

  @app.get("/use-cases/finance")
  def use_case_finance():
    return render_template("marketing/use_case_finance.html")

  # Solutions (decision-centric + unified intake)
  @app.get("/solutions/unified-intake")
  def solutions_unified_intake():
    return render_template("marketing/solutions_unified_intake.html")

  @app.get("/solutions/decisions")
  def solutions_decisions():
    return render_template("marketing/solutions_decisions.html")

  @app.get("/solutions/voice")
  def solutions_voice():
    return render_template("marketing/solutions_channel_voice.html")

  @app.get("/solutions/social")
  def solutions_social():
    return render_template("marketing/solutions_channel_social.html")

  @app.get("/solutions/forms")
  def solutions_forms():
    return render_template("marketing/solutions_channel_forms.html")

  @app.get("/solutions/chat")
  def solutions_chat():
    return render_template("marketing/solutions_channel_chat.html")

  @app.get("/solutions/crm")
  def solutions_crm():
    return render_template("marketing/solutions_channel_crm.html")

  @app.get("/solutions/api")
  def solutions_api():
    return render_template("marketing/solutions_channel_api.html")

  @app.get("/solutions/email/ai-triage")
  def solutions_email_ai_triage():
    return render_template("marketing/ai_email_triage.html")

  @app.get("/solutions/email/triage-automation")
  def solutions_email_triage_automation():
    return render_template("marketing/email_triage.html")

  @app.get("/solutions/email/draft-replies")
  def solutions_email_draft_replies():
    return render_template("marketing/email_draft_replies.html")

  @app.get("/solutions/email/shared-inbox")
  def solutions_email_shared_inbox():
    return render_template("marketing/shared_inbox.html")

  @app.get("/solutions/email/support-automation")
  def solutions_email_support_automation():
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

  @app.get("/features")
  def features_page():
    return render_template("marketing/features.html")

  @app.get("/pricing")
  def pricing_page():
    return render_template("marketing/pricing.html")

  @app.route("/robots.txt")
  def robots_txt():
    # Serve SEO-friendly robots.txt at the root.
    return current_app.send_static_file("robots.txt")

  @app.route("/sitemap.xml")
  def sitemap():
    """
    Dynamic sitemap that includes all published blog posts.
    Auto-updates when new content is generated.
    """
    from src.models import BlogPost
    from flask import Response

    # Static pages (from sitemap.xml)
    static_pages = [
      {"loc": "https://kalevent.com/", "priority": "1.0"},
      {"loc": "https://kalevent.com/login", "priority": "0.7"},
      {"loc": "https://kalevent.com/contact", "priority": "0.7"},
      {"loc": "https://kalevent.com/security", "priority": "0.6"},
      {"loc": "https://kalevent.com/email-triage", "priority": "0.6"},
      {"loc": "https://kalevent.com/ai-email-triage", "priority": "0.6"},
      {"loc": "https://kalevent.com/shared-inbox", "priority": "0.6"},
      {"loc": "https://kalevent.com/support-automation", "priority": "0.6"},
      {"loc": "https://kalevent.com/solutions/unified-intake", "priority": "0.6"},
      {"loc": "https://kalevent.com/solutions/decisions", "priority": "0.6"},
      {"loc": "https://kalevent.com/solutions/voice", "priority": "0.6"},
      {"loc": "https://kalevent.com/solutions/social", "priority": "0.6"},
      {"loc": "https://kalevent.com/solutions/forms", "priority": "0.6"},
      {"loc": "https://kalevent.com/solutions/chat", "priority": "0.6"},
      {"loc": "https://kalevent.com/solutions/crm", "priority": "0.6"},
      {"loc": "https://kalevent.com/solutions/api", "priority": "0.6"},
      {"loc": "https://kalevent.com/solutions/email/ai-triage", "priority": "0.6"},
      {"loc": "https://kalevent.com/solutions/email/triage-automation", "priority": "0.6"},
      {"loc": "https://kalevent.com/solutions/email/shared-inbox", "priority": "0.6"},
      {"loc": "https://kalevent.com/solutions/email/support-automation", "priority": "0.6"},
      {"loc": "https://kalevent.com/use-cases/support", "priority": "0.6"},
      {"loc": "https://kalevent.com/use-cases/healthcare-triage", "priority": "0.6"},
      {"loc": "https://kalevent.com/use-cases/claims", "priority": "0.6"},
      {"loc": "https://kalevent.com/use-cases/hr", "priority": "0.6"},
      {"loc": "https://kalevent.com/use-cases/finance", "priority": "0.6"},
      {"loc": "https://kalevent.com/playbook/unified-support-triage", "priority": "0.6"},
      {"loc": "https://kalevent.com/playbook/unified-sales-intake", "priority": "0.6"},
      {"loc": "https://kalevent.com/playbook/unified-ops-intake", "priority": "0.6"},
      {"loc": "https://kalevent.com/playbook/unified-intake-system", "priority": "0.6"},
      {"loc": "https://kalevent.com/docs", "priority": "0.6"},
      {"loc": "https://kalevent.com/privacy", "priority": "0.5"},
      {"loc": "https://kalevent.com/terms", "priority": "0.5"},
    ]

    # Get all published blog posts
    blog_posts = BlogPost.query.filter_by(status='published').order_by(BlogPost.created_at.desc()).all()

    # Build XML
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'

    # Add static pages
    for page in static_pages:
      xml += '  <url>\n'
      xml += f'    <loc>{page["loc"]}</loc>\n'
      xml += f'    <priority>{page["priority"]}</priority>\n'
      xml += '  </url>\n'

    # Add blog posts (higher priority for fresh content)
    for post in blog_posts:
      xml += '  <url>\n'
      xml += f'    <loc>https://kalevent.com/blog/{post.slug}</loc>\n'
      xml += f'    <lastmod>{post.created_at.strftime("%Y-%m-%d")}</lastmod>\n'
      xml += '    <changefreq>monthly</changefreq>\n'
      xml += '    <priority>0.7</priority>\n'
      xml += '  </url>\n'

    xml += '</urlset>'

    return Response(xml, mimetype='application/xml')

  @app.route("/upgrade")
  @login_required_page
  def upgrade():
    return render_template("billing_upgrade.html", stripe_pk=current_app.config.get("STRIPE_PUBLISHABLE_KEY"))

  @app.route("/onboarding", methods=["GET"])
  @login_required_page
  def onboarding_page():
    return render_template("onboarding.html")

  def _cluster_top_topics(account_id, tickets, top_n=5):
    """
    Return top N topic labels with counts, derived from email subjects.

    Strategy:
    1. Clean each subject (strip Re:/Fwd: prefixes, brackets, truncate).
    2. Try to load TicketEmbedding vectors for these tickets and do greedy
       cosine clustering so semantically similar emails share one topic.
    3. Fall back to exact-subject grouping when embeddings are unavailable.
    4. Use the shortest subject in each cluster as the display label —
       avoids generic DSPy intent values like "General" or "Support".
    """
    import math
    import re

    _GENERIC = {"support", "general", "other", "unknown", "how to", "how_to", "feedback"}

    def _clean_subject(s):
      s = (s or "").strip()
      # Strip common prefixes: Re:, Fwd:, [Company], etc.
      s = re.sub(r"^(re|fwd?|fw)\s*:\s*", "", s, flags=re.IGNORECASE)
      s = re.sub(r"^\[[^\]]{1,40}\]\s*", "", s)
      return s.strip()[:80] or None

    def _cosine(a, b):
      dot = sum(x * y for x, y in zip(a, b))
      na = math.sqrt(sum(x * x for x in a)) or 1.0
      nb = math.sqrt(sum(y * y for y in b)) or 1.0
      return dot / (na * nb)

    # Build list of (ticket_id, clean_subject) — skip tickets with no subject
    ticket_subjects = []
    for t in tickets:
      subj = _clean_subject(t.get("subject"))
      if not subj:
        # Fall back to intent only when subject is missing
        intent = (t.get("intent") or t.get("category") or "").replace("_", " ").lower()
        if intent and intent not in _GENERIC:
          subj = intent.title()
      if subj:
        ticket_subjects.append((t["id"], subj))

    if not ticket_subjects:
      return []

    # Attempt embedding-based clustering — scoped by account_id via join
    try:
      from src.models.tickets import TicketEmbedding, Ticket as _Ticket
      ids = [tid for tid, _ in ticket_subjects]
      rows = (
        TicketEmbedding.query
        .join(_Ticket, _Ticket.id == TicketEmbedding.ticket_id)
        .filter(_Ticket.account_id == account_id, TicketEmbedding.ticket_id.in_(ids))
        .all()
      )
      emb_map = {r.ticket_id: list(r.embedding) for r in rows if r.embedding}
    except Exception:
      emb_map = {}

    SIMILARITY_THRESHOLD = 0.78
    clusters = []  # list of {"label": str, "count": int, "vec": list|None}

    for tid, subj in ticket_subjects:
      vec = emb_map.get(tid)
      matched = False
      for cluster in clusters:
        if vec and cluster["vec"]:
          sim = _cosine(vec, cluster["vec"])
        else:
          # Fall back to exact subject match when embeddings unavailable
          sim = 1.0 if subj.lower() == cluster["label"].lower() else 0.0
        if sim >= SIMILARITY_THRESHOLD:
          cluster["count"] += 1
          # Keep the shorter subject as the label (more concise)
          if len(subj) < len(cluster["label"]):
            cluster["label"] = subj
          matched = True
          break
      if not matched:
        clusters.append({"label": subj, "count": 1, "vec": vec})

    clusters.sort(key=lambda c: c["count"], reverse=True)
    return [(c["label"], c["count"]) for c in clusters[:top_n]]

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
      def _is_email(conn):
        return (conn.provider or "").lower() in {"gmail", "outlook", "imap"}
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
      email_connections = [c for c in connections if _is_email(c)]
      candidate_pool = email_connections or connections
      return max(
        candidate_pool,
        key=lambda c: (_poll_ts(c) or datetime.min.replace(tzinfo=timezone.utc), c.updated_at or datetime.min.replace(tzinfo=timezone.utc)),
      )

    account_connections = InboxConnection.query.filter_by(account_id=account_id, status="connected").all()
    email_inbox_connections = [c for c in account_connections if (c.provider or "").lower() in {"gmail", "outlook", "imap"}]
    last_connection = _pick_connection(account_connections)
    if not last_connection:
      user_connections = InboxConnection.query.filter_by(user_id=user.id, status="connected").all()
      last_connection = _pick_connection(user_connections)
      email_inbox_connections = email_inbox_connections or [c for c in user_connections if (c.provider or "").lower() in {"gmail", "outlook", "imap"}]
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

    # Query connection status for each integration type for dashboard cards
    def _has_connection(provider_list):
      """Check if any connected provider exists for the given list"""
      return InboxConnection.query.filter(
        InboxConnection.account_id == account_id,
        InboxConnection.status == "connected",
        InboxConnection.provider.in_(provider_list)
      ).first() is not None

    integration_status = {
      "voice": _has_connection(["voice", "ivr", "twilio", "vonage"]),
      "social": _has_connection(["social", "facebook", "twitter", "instagram", "linkedin", "whatsapp"]),
      "forms": _has_connection(["forms", "typeform", "jotform", "googleforms"]),
      "chat": _has_connection(["chat", "inboxiq", "intercom", "drift", "livechat", "zendesk_chat"]),
      "crm": _has_connection(["crm", "salesforce", "hubspot", "pipedrive"]),
      "api": _has_connection(["api", "webhook", "webhooks"]),
    }

    from src.models.content import KBIntegration
    has_kb = KBIntegration.query.filter(
        KBIntegration.account_id == account_id,
        KBIntegration.article_count > 0,
    ).first() is not None

    banner_first_batch = total_tickets >= 5
    allowed = set(
      e.strip().lower()
      for e in (current_app.config.get("ADMIN_EMAILS", "") or "").split(",")
      if e.strip()
    )
    has_admin_access = bool(user and user.email and ((not allowed) or (user.email.lower() in allowed)))

    # Build work queue groupings to match the UI sections (action required, optional, auto-handled).
    from src.dspy.triage_config import get_triage_config
    triage_cfg = get_triage_config(account_id)

    def _sla_display(priority: str | None) -> str:
      return triage_cfg.get_sla_display(priority)

    def _ai_reason(decision: dict, fallback: str) -> str:
      # Check top-level first, then merged dict (where auto-handled reasons are stored)
      return (
          decision.get("ai_reason")
          or decision.get("reason")
          or decision.get("merged", {}).get("ai_reason")
          or fallback
      )

    def _action_reason_text(flag) -> str:
      return triage_cfg.get_action_reason_text(flag)

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
        "category": t.category or decision.get("category") or triage_cfg.default_category,
        "intent": decision.get("intent") or triage_cfg.default_category,
        "sentiment": sentiment or "neutral",
        "provider": t.provider or decision.get("provider"),
        "ai_reason": _ai_reason(decision, _action_reason_text(action_required)),
        "owner": t.owner or decision.get("owner") or triage_cfg.default_owner,
        "due_at": t.due_at,
        "sla": _sla_display(priority),
        "url": url_for("ticket_detail", ticket_id=t.id),
        "provider_url": t.provider_thread_url or decision.get("url"),
        "draft_reply": bool(decision.get("reply_text") or decision.get("draft_reply")),
      }

      if action_required is True:
        action_required_tickets.append(ticket_view)
      elif action_required == "optional" or needs_review:
        ticket_view["ai_reason"] = _ai_reason(decision, _action_reason_text("optional"))
        optional_tickets.append(ticket_view)
      elif action_required is False or auto_handled_flag or triage_cfg.should_auto_handle_p2_neutral(priority, sentiment, risk_flag):
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

    # Hours saved: 3 min per email processed, all-time
    hours_saved_raw = total_tickets * 3 / 60
    if hours_saved_raw >= 10:
      hours_saved_display = f"{round(hours_saved_raw)}h"
    elif hours_saved_raw >= 1:
      hours_saved_display = f"{hours_saved_raw:.1f}h"
    else:
      hours_saved_display = f"{round(hours_saved_raw * 60)}m"

    # Top topics: cluster tickets by subject similarity and label each cluster
    # with the most representative subject line — avoids generic labels like
    # "General" or "Support" that come from DSPy's coarse intent field.
    _SUPPORT_CATEGORIES = {"support", "billing"}
    _support_tickets = [
      t for t in (action_required_tickets + optional_tickets + auto_handled_items)
      if (t.get("category") or "").lower() in _SUPPORT_CATEGORIES
    ]
    top_raw_topics = _cluster_top_topics(
      account_id,
      _support_tickets,
      top_n=5,
    )

    # Check which topics already have an automation rule (match on conditions field)
    try:
      from src.models.automation import AutomationRule
      existing_rules = AutomationRule.query.filter_by(account_id=account_id, enabled=True).all()

      def _rule_for_topic(topic_label):
        tl = topic_label.lower()
        for rule in existing_rules:
          for cond in (rule.conditions or []):
            val = str(cond.get("value") or "").lower()
            if val and val in tl:
              return rule
        return None

      top_topics = []
      for label, count in top_raw_topics:
        rule = _rule_for_topic(label)
        top_topics.append({
          "label": label,
          "count": count,
          "rule_id": str(rule.id) if rule else None,
          "rule_name": rule.name if rule else None,
        })
    except Exception as e:
      current_app.logger.error(f"Failed to build top topics: {e}")
      top_topics = [{"label": lbl, "count": cnt, "rule_id": None, "rule_name": None} for lbl, cnt in top_raw_topics]

    # Draft acceptance rate
    try:
      from src.models.tickets import DraftReplyFeedback
      feedback_rows = DraftReplyFeedback.query.filter_by(account_id=account_id).all()
      total_feedback = len(feedback_rows)
      accepted_feedback = sum(1 for f in feedback_rows if f.feedback_type in ("accepted", "edited"))
      draft_acceptance_pct = round(accepted_feedback / total_feedback * 100) if total_feedback else None
    except Exception as e:
      current_app.logger.error(f"Failed to fetch draft feedback: {e}")
      draft_acceptance_pct = None

    # Get automation metrics
    try:
      from src.models import AutomationRule, AutomationRuleExecution
      active_rules_count = AutomationRule.query.filter_by(
        account_id=account_id,
        enabled=True
      ).count()

      thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
      automation_executions_30d = AutomationRuleExecution.query.filter(
        AutomationRuleExecution.account_id == account_id,
        AutomationRuleExecution.created_at >= thirty_days_ago
      ).count()

      # Calculate time saved (rough estimate: 2 minutes per execution)
      automation_time_saved_minutes = automation_executions_30d * 2
      automation_time_saved_hours = automation_time_saved_minutes // 60
      automation_time_saved_display = f"{automation_time_saved_hours}h" if automation_time_saved_hours > 0 else "0h"
    except Exception as e:
      current_app.logger.error(f"Failed to fetch automation metrics: {e}")
      active_rules_count = 0
      automation_executions_30d = 0
      automation_time_saved_display = "0h"

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
      email_inbox_connections=email_inbox_connections,
      has_admin_access=has_admin_access,
      scope=scope,
      integration_status=integration_status,
      account_id=account_id,
      active_rules_count=active_rules_count,
      automation_executions_30d=automation_executions_30d,
      automation_time_saved_display=automation_time_saved_display,
      has_kb=has_kb,
      hours_saved_display=hours_saved_display,
      top_topics=top_topics,
      draft_acceptance_pct=draft_acceptance_pct,
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
  @login_required_page
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
  @login_required_page
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

  @app.route("/signup", methods=["GET"])
  def signup_page():
    return redirect("/?open_trial=1")

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

  # Initialize Celery instance for background tasks
  # This ensures shared_task decorators use the correct broker (Redis)
  try:
    from src.celery_inboxiq import celery  # noqa: F401
  except ImportError:
    pass  # Celery optional for basic Flask operations

  return app
