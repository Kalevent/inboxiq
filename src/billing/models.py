from datetime import datetime
from uuid import uuid4
from sqlalchemy.sql import func
from src.extensions import db


class PaymentProviderAccount(db.Model):
    __tablename__ = "payment_provider_accounts"

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    provider = db.Column(db.String(32), nullable=False)  # e.g., stripe, secondary
    label = db.Column(db.String(64), nullable=True)
    status = db.Column(db.String(32), nullable=False, default="active")
    livemode = db.Column(db.Boolean, nullable=False, default=False)
    metadata_json = db.Column("metadata", db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class CustomerBillingProfile(db.Model):
    __tablename__ = "customer_billing_profiles"
    __table_args__ = (db.UniqueConstraint("account_id", name="uq_billing_profile_account"),)

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)
    email = db.Column(db.String(255), nullable=False)
    billing_name = db.Column(db.String(255), nullable=True)
    address = db.Column(db.JSON, nullable=False, default=dict)
    tax_id = db.Column(db.String(64), nullable=True)
    plan_choice = db.Column(db.String(32), nullable=True)  # pro|business
    trial_start = db.Column(db.DateTime(timezone=True), nullable=True)
    trial_end = db.Column(db.DateTime(timezone=True), nullable=True)
    trial_status = db.Column(db.String(32), nullable=False, default="active")  # active|ending_soon|ended
    subscription_status = db.Column(db.String(32), nullable=False, default="none")  # none|active|past_due|canceled
    default_payment_method_id = db.Column(db.String(64), db.ForeignKey("payment_methods.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class PaymentMethod(db.Model):
    __tablename__ = "payment_methods"

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    profile_id = db.Column(db.String(64), db.ForeignKey("customer_billing_profiles.id"), nullable=False, index=True)
    provider = db.Column(db.String(32), nullable=False)
    provider_payment_method_id = db.Column(db.String(128), nullable=False)
    brand = db.Column(db.String(64), nullable=True)
    last4 = db.Column(db.String(8), nullable=True)
    exp_month = db.Column(db.Integer, nullable=True)
    exp_year = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(32), nullable=False, default="active")  # active|failed|detached
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class Plan(db.Model):
    __tablename__ = "plans"

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    code = db.Column(db.String(32), nullable=False, unique=True)  # pro|business|scale
    price_cents = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(8), nullable=False, default="GBP")
    # Legacy field — superseded by ai_decisions_limit below; kept for backward compat
    ai_actions = db.Column(db.Integer, nullable=True)
    seats = db.Column(db.Integer, nullable=True)
    metadata_json = db.Column("metadata", db.JSON, nullable=False, default=dict)

    # Feature gates (False = disabled on this plan)
    chat_enabled             = db.Column(db.Boolean, nullable=False, default=False)
    automation_enabled       = db.Column(db.Boolean, nullable=False, default=False)
    content_gen_enabled      = db.Column(db.Boolean, nullable=False, default=False)
    lead_discovery_enabled   = db.Column(db.Boolean, nullable=False, default=False)
    nurture_enabled          = db.Column(db.Boolean, nullable=False, default=False)
    distribution_enabled     = db.Column(db.Boolean, nullable=False, default=False)
    api_access_enabled       = db.Column(db.Boolean, nullable=False, default=False)
    registered_apps_limit    = db.Column(db.Integer, nullable=False, default=0)

    # Monthly included quotas (None = unlimited)
    ai_decisions_limit       = db.Column(db.Integer, nullable=True)
    chat_limit               = db.Column(db.Integer, nullable=True)
    automation_runs_limit    = db.Column(db.Integer, nullable=True)
    content_posts_limit      = db.Column(db.Integer, nullable=True)
    leads_limit              = db.Column(db.Integer, nullable=True)
    nurture_emails_limit     = db.Column(db.Integer, nullable=True)

    # Stripe metered price IDs for overage reporting (set after Stripe setup)
    stripe_ai_overage_price_id         = db.Column(db.String(128), nullable=True)
    stripe_chat_overage_price_id       = db.Column(db.String(128), nullable=True)
    stripe_automation_overage_price_id = db.Column(db.String(128), nullable=True)
    stripe_leads_overage_price_id      = db.Column(db.String(128), nullable=True)
    stripe_nurture_overage_price_id    = db.Column(db.String(128), nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class Subscription(db.Model):
    __tablename__ = "subscriptions"

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    profile_id = db.Column(db.String(64), db.ForeignKey("customer_billing_profiles.id"), nullable=False, index=True)
    plan_id = db.Column(db.String(64), db.ForeignKey("plans.id"), nullable=True)
    provider = db.Column(db.String(32), nullable=False)
    provider_subscription_id = db.Column(db.String(128), nullable=True)
    status = db.Column(db.String(32), nullable=False, default="trialing")  # trialing|active|past_due|canceled
    current_period_end = db.Column(db.DateTime(timezone=True), nullable=True)
    cancel_at_period_end = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class Invoice(db.Model):
    __tablename__ = "invoices"

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    profile_id = db.Column(db.String(64), db.ForeignKey("customer_billing_profiles.id"), nullable=False, index=True)
    subscription_id = db.Column(db.String(64), db.ForeignKey("subscriptions.id"), nullable=True)
    amount_cents = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(8), nullable=False, default="GBP")
    status = db.Column(db.String(32), nullable=False, default="draft")  # draft|open|paid|void|uncollectible
    due_at = db.Column(db.DateTime(timezone=True), nullable=True)
    provider = db.Column(db.String(32), nullable=True)
    provider_invoice_id = db.Column(db.String(128), nullable=True)
    pdf_url = db.Column(db.String(512), nullable=True)
    last_attempt_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class ChargeAttempt(db.Model):
    __tablename__ = "charge_attempts"

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    invoice_id = db.Column(db.String(64), db.ForeignKey("invoices.id"), nullable=False, index=True)
    provider = db.Column(db.String(32), nullable=False)
    provider_payment_intent_id = db.Column(db.String(128), nullable=True)
    status = db.Column(db.String(32), nullable=False, default="processing")  # requires_action|processing|succeeded|failed
    failure_reason = db.Column(db.String(255), nullable=True)
    attempt_number = db.Column(db.Integer, nullable=False, default=1)
    used_fallback = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class AccountUsageCounter(db.Model):
    """Monthly usage counters per account. Composite PK on (account_id, billing_month).

    billing_month format: "YYYY-MM" (e.g. "2026-02").
    Counters are incremented by quota.check_and_increment(); never decremented.
    Overage units are reported to Stripe when a counter crosses its plan limit.
    """
    __tablename__ = "account_usage_counters"

    account_id         = db.Column(db.Integer, db.ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True)
    billing_month      = db.Column(db.String(7), primary_key=True)
    ai_decisions       = db.Column(db.Integer, nullable=False, default=0)
    chat_conversations = db.Column(db.Integer, nullable=False, default=0)
    automation_runs    = db.Column(db.Integer, nullable=False, default=0)
    content_posts      = db.Column(db.Integer, nullable=False, default=0)
    leads_discovered   = db.Column(db.Integer, nullable=False, default=0)
    nurture_emails     = db.Column(db.Integer, nullable=False, default=0)
    updated_at         = db.Column(db.DateTime(timezone=True), onupdate=func.now())


def table_exists(model) -> bool:
    """Helper to detect if the mapped table exists to avoid runtime crashes before migrations run."""
    try:
        return db.inspect(db.engine).has_table(model.__tablename__)
    except Exception:
        return False
