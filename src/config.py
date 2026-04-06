import os
from datetime import timedelta

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    load_dotenv = None


# Load environment variables from project .env early if python-dotenv is available.
if load_dotenv:
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    load_dotenv(os.path.join(BASE_DIR, ".env"))
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.lower() in ("1", "true", "yes", "on")

def _redis_dev_url() -> str | None:
    return os.getenv("REDIS_DEV_URL") or os.getenv("REDIS__DEV_URL") or os.getenv("REDIS_URL")


class Config:
    """Minimal config; extend as features land."""

    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
    # API base for links and cross-origin calls; accept either var
    INBOXIQ_API_BASE_URL = os.getenv("INBOXIQ_API_BASE_URL") or os.getenv("API_BASE_URL")
    # Prefer explicit dev vars when present; fall back to DATABASE_URL.
    SQLALCHEMY_DATABASE_URI = (
        os.getenv("DATABASE_DEV_URL")
        or os.getenv("DATABASE_URL")
        or "postgresql://postgres:postgres@localhost:5432/inboxiq"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Flask-Migrate directory (kept separate from legacy migrations)
    MIGRATION_DIR = os.getenv("MIGRATION_DIR", "src/migrations")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", SECRET_KEY)
    JWT_TOKEN_LOCATION = ["headers", "cookies"]
    JWT_HEADER_NAME = "Authorization"
    JWT_HEADER_TYPE = "Bearer"
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        minutes=int(os.getenv("JWT_ACCESS_TOKEN_MINUTES", "480"))
    )
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(
        days=int(os.getenv("JWT_REFRESH_TOKEN_DAYS", "7"))
    )
    JWT_COOKIE_SECURE = _env_bool("JWT_COOKIE_SECURE", True)
    JWT_COOKIE_SAMESITE = os.getenv("JWT_COOKIE_SAMESITE", "Lax")
    JWT_COOKIE_CSRF_PROTECT = _env_bool("JWT_COOKIE_CSRF_PROTECT", True)
    JWT_CSRF_CHECK_FORM = True  # Allow CSRF tokens from form data, not just headers
    # Caching (Redis)
    # Caching (default to SimpleCache to avoid redis dependency in dev)
    CACHE_TYPE = os.getenv("CACHE_TYPE", "SimpleCache")
    CACHE_REDIS_URL = _redis_dev_url()
    # Rate limiting (Flask-Limiter)
    RATELIMIT_STORAGE_URI = os.getenv(
        "RATELIMIT_STORAGE_URI",
        _redis_dev_url() or "memory://",
    )
    RATELIMIT_DEFAULTS = os.getenv("RATELIMIT_DEFAULTS")
    RATELIMIT_HEADERS_ENABLED = True
    # CORS (restrict to trusted origins; leave unset to disable)
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "")
    # Email (SMTP) for activation links
    SMTP_HOST = os.getenv("SMTP_HOST")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = os.getenv("SMTP_USER")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
    SMTP_USE_TLS = _env_bool("SMTP_USE_TLS", True)
    SMTP_USE_SSL = _env_bool("SMTP_USE_SSL", False)
    MAIL_FROM = os.getenv("MAIL_FROM", "noreply@kalevent.com")  # System emails (crash reports, etc.)

    # Campaign senders are stored in database (CampaignSender model) for security
    # Fallback defaults if no senders configured in DB
    CAMPAIGN_DEFAULT_EMAIL = os.getenv("CAMPAIGN_DEFAULT_EMAIL", "kofi@kalevent.com")
    CAMPAIGN_DEFAULT_NAME = os.getenv("CAMPAIGN_DEFAULT_NAME", "Kofi from Kalevent")

    # Celery
    CELERY_BROKER_URL = os.getenv("CELERY_BROKER_DEV_URL") or os.getenv("CELERY_BROKER_URL") or _redis_dev_url()
    CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_DEV_BACKEND") or os.getenv("CELERY_RESULT_BACKEND") or _redis_dev_url()
    # Payments
    STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY")
    STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
    STRIPE_PRICE_PRO = os.getenv("STRIPE_PRICE_PRO")
    STRIPE_PRICE_BUSINESS = os.getenv("STRIPE_PRICE_BUSINESS")
    STRIPE_PRICE_SCALE = os.getenv("STRIPE_PRICE_SCALE")
    # Metered overage price IDs (set after running scripts/stripe_setup.py)
    STRIPE_OVERAGE_PRO_AI = os.getenv("STRIPE_OVERAGE_PRO_AI_OVERAGE")
    STRIPE_OVERAGE_BUSINESS_AI = os.getenv("STRIPE_OVERAGE_BUSINESS_AI_OVERAGE")
    STRIPE_OVERAGE_BUSINESS_CHAT = os.getenv("STRIPE_OVERAGE_BUSINESS_CHAT_OVERAGE")
    STRIPE_OVERAGE_BUSINESS_AUTOMATION = os.getenv("STRIPE_OVERAGE_BUSINESS_AUTOMATION_OVERAGE")
    STRIPE_OVERAGE_BUSINESS_NURTURE = os.getenv("STRIPE_OVERAGE_BUSINESS_NURTURE_OVERAGE")
    STRIPE_OVERAGE_SCALE_AI = os.getenv("STRIPE_OVERAGE_SCALE_AI_OVERAGE")
    STRIPE_OVERAGE_SCALE_CHAT = os.getenv("STRIPE_OVERAGE_SCALE_CHAT_OVERAGE")
    STRIPE_OVERAGE_SCALE_AUTOMATION = os.getenv("STRIPE_OVERAGE_SCALE_AUTOMATION_OVERAGE")
    STRIPE_OVERAGE_SCALE_NURTURE = os.getenv("STRIPE_OVERAGE_SCALE_NURTURE_OVERAGE")
    STRIPE_OVERAGE_SCALE_LEADS = os.getenv("STRIPE_OVERAGE_SCALE_LEADS_OVERAGE")
    SECONDARY_PSP_KEY = os.getenv("SECONDARY_PSP_KEY")
    # Microsoft OAuth (Outlook)
    MICROSOFT_CLIENT_ID = os.getenv("MICROSOFT_CLIENT_ID")
    MICROSOFT_CLIENT_SECRET = os.getenv("MICROSOFT_CLIENT_SECRET")
    MICROSOFT_REDIRECT_URI = os.getenv("MICROSOFT_REDIRECT_URI")
    # Marketing / Google Analytics
    GOOGLE_ANALYTICS_ID = os.getenv("GOOGLE_ANALYTICS_ID")
    GOOGLE_ANALYTICS_ENABLED = _env_bool("GOOGLE_ANALYTICS_ENABLED", False)
    GOOGLE_ANALYTICS_API_SECRET = os.getenv("GOOGLE_ANALYTICS_API_SECRET")
    GA_MARKETING_PROPERTY_ID = os.getenv("GA_MARKETING_PROPERTY_ID")
    # Crash reporting email target (used by crash_report)
    CRASH_EMAIL_TO = os.getenv("CRASH_EMAIL_TO")
    # Admin access control (comma-separated emails)
    ADMIN_EMAILS = os.getenv("ADMIN_EMAILS", "kofi@kalevent.com")
    # OAuth
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
    GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")
    # Celery
    CELERY_BROKER_URL = os.getenv("CELERY_BROKER_DEV_URL") or os.getenv("CELERY_BROKER_URL") or _redis_dev_url()
    CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_DEV_BACKEND") or os.getenv("CELERY_RESULT_BACKEND") or _redis_dev_url()
    # Testimonials gating
    TESTIMONIAL_MIN_TICKETS = int(os.getenv("TESTIMONIAL_MIN_TICKETS", "3"))
    TESTIMONIAL_MIN_ACCOUNT_AGE_DAYS = int(os.getenv("TESTIMONIAL_MIN_ACCOUNT_AGE_DAYS", "7"))
    # InboxIQ post-processing
    INBOXIQ_AUTO_LABEL_PROCESSED = _env_bool("INBOXIQ_AUTO_LABEL_PROCESSED", False)
    INBOXIQ_AUTO_LABEL_NEEDS_REVIEW = _env_bool("INBOXIQ_AUTO_LABEL_NEEDS_REVIEW", True)
    INBOXIQ_AUTO_MARK_READ = _env_bool("INBOXIQ_AUTO_MARK_READ", False)
    # Uploads (S3 + CloudFront)
    UPLOADS_BUCKET = os.getenv("UPLOADS_BUCKET")
    UPLOADS_HOST = os.getenv("UPLOADS_HOST")
    # Publishing MCP/HTTP endpoints
    PUBLISHING_API_BASE = os.getenv("PUBLISHING_API_BASE")
    PUBLISHING_API_TOKEN = os.getenv("PUBLISHING_API_TOKEN")
    # NHS FHIR API — signed JWT authentication
    NHS_FHIR_CLIENT_ID = os.getenv("NHS_FHIR_CLIENT_ID")
    NHS_FHIR_BASE_URL = os.getenv("NHS_FHIR_BASE_URL")
    NHS_FHIR_CALLBACK_URL = os.getenv("NHS_FHIR_CALLBACK_URL")
    NHS_FHIR_PRIVATE_KEY = os.getenv("NHS_FHIR_PRIVATE_KEY")  # PEM — used to sign JWTs
    NHS_FHIR_JWKS = os.getenv("NHS_FHIR_JWKS")                # JSON string served at /.well-known/jwks.json


class DevelopmentConfig(Config):
    """Development overrides (use dev URLs when present)."""

    # Allow HTTP for local dev so login cookies are set when running on localhost.
    JWT_COOKIE_SECURE = _env_bool("JWT_COOKIE_SECURE", False)
    # Disable CSRF on JWT cookies for local HTML flows.
    JWT_COOKIE_CSRF_PROTECT = _env_bool("JWT_COOKIE_CSRF_PROTECT", False)

    SQLALCHEMY_DATABASE_URI = (
        os.getenv("DATABASE_DEV_URL")
        or os.getenv("DATABASE_URL")
        or "postgresql://postgres:postgres@localhost:5432/inboxiq"
    )
    CACHE_REDIS_URL = _redis_dev_url()
    CELERY_BROKER_URL = os.getenv("CELERY_BROKER_DEV_URL") or os.getenv("CELERY_BROKER_URL") or _redis_dev_url()
    CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_DEV_BACKEND") or os.getenv("CELERY_RESULT_BACKEND") or _redis_dev_url()
    # Prefer dev overrides for publishing
    PUBLISHING_API_BASE = (
        os.getenv("PUBLISHING_API_BASE_DEV")
        or os.getenv("PUBLISHING_API_BASE")
        or "http://localhost:8000/api/v1"
    )
    PUBLISHING_API_TOKEN = os.getenv("PUBLISHING_API_TOKEN_DEV") or os.getenv("PUBLISHING_API_TOKEN")


class ProductionConfig(Config):
    """Production overrides (explicitly use prod URLs)."""

    # Allow disabling CSRF on JWT cookies via env if HTML forms fail CSRF checks.
    JWT_COOKIE_CSRF_PROTECT = _env_bool("JWT_COOKIE_CSRF_PROTECT", True)
    JWT_CSRF_CHECK_FORM = True  # Allow CSRF tokens from form data, not just headers
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    CACHE_REDIS_URL = os.getenv("REDIS_URL")
    CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL")
    CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND")
    PUBLISHING_API_BASE = os.getenv("PUBLISHING_API_BASE")
    PUBLISHING_API_TOKEN = os.getenv("PUBLISHING_API_TOKEN")
    # Lax allows the session cookie to be sent on OAuth cross-site redirects
    # (e.g. LinkedIn/Twitter → kalevent.com callback).
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = True


class TestConfig(Config):
    """Testing configuration."""

    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    CACHE_TYPE = "SimpleCache"
    CELERY_BROKER_URL = "memory://"
    CELERY_RESULT_BACKEND = "cache+memory://"
