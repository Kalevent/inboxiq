from flask import request, jsonify, current_app, g
from flask_jwt_extended import jwt_required, get_jwt_identity
from src.api.v1 import v1
from src.extensions import db
from src.billing.service import BillingService, guard_missing_tables
from src.billing import models
from src.billing.idempotency import ensure_idempotency
from src.billing.providers.barclay import BarclayHostedProvider


def _get_account_id(user_id: int | None) -> int | None:
    from src.models import User, Account  # local to avoid cycles
    if not user_id:
        return None
    user = User.query.get(user_id)
    acct = user.account if user else None
    return getattr(acct, "id", None)


def _lookup_account_id_by_email(email: str | None) -> int | None:
    """Best-effort account lookup by user email for upgrade flows when JWT is missing."""
    if not email:
        return None
    from src.models import User  # local import to avoid cycles
    user = User.query.filter_by(email=email).first()
    return getattr(user, "account_id", None) if user else None


def _get_service() -> BillingService:
    cfg = current_app.config
    return BillingService(
        stripe_key=cfg.get("STRIPE_SECRET_KEY"),
        secondary_key=cfg.get("SECONDARY_PSP_KEY"),
    )


def _stripe_price_for_plan(plan_choice: str) -> str | None:
    """
    Map plan choice to Stripe price id via config. Configure env:
    STRIPE_PRICE_PRO, STRIPE_PRICE_BUSINESS, STRIPE_PRICE_SCALE.
    """
    plan = (plan_choice or "").lower()
    cfg = current_app.config
    if plan == "pro":
        return cfg.get("STRIPE_PRICE_PRO")
    if plan == "business":
        return cfg.get("STRIPE_PRICE_BUSINESS")
    if plan == "scale":
        return cfg.get("STRIPE_PRICE_SCALE")
    return None


def _get_or_create_profile(account_id: int, email: str, plan_choice: str | None = None) -> models.CustomerBillingProfile:
    profile = models.CustomerBillingProfile.query.filter_by(account_id=account_id).first()
    if not profile:
        profile = models.CustomerBillingProfile(
            account_id=account_id,
            email=email,
            plan_choice=plan_choice,
        )
        db.session.add(profile)
        db.session.commit()
    return profile


@v1.route("/billing/payment-methods", methods=["POST"])
@jwt_required(optional=True)
def add_payment_method():
    user_id = get_jwt_identity()
    data = request.get_json() or {}
    account_id = (
        _get_account_id(user_id)
        or getattr(g, "current_account_id", None)
        or data.get("account_id")
        or _lookup_account_id_by_email(data.get("email"))
    )
    if not account_id:
        return jsonify({"error": "Account not found"}), 404

    if not current_app.config.get("STRIPE_SECRET_KEY"):
        return jsonify({"error": "stripe api key missing"}), 500

    token = data.get("token")
    provider = data.get("provider") or "stripe"
    email = data.get("email")
    plan_choice = data.get("plan_choice")
    if not token:
        return jsonify({"error": "token is required"}), 400
    if not email:
        return jsonify({"error": "email is required"}), 400

    billing = _get_service()
    profile = _get_or_create_profile(account_id, email, plan_choice)
    try:
        ensure_idempotency(request.headers.get("Idempotency-Key"), "payment_method_api")
        result = billing.add_payment_method(profile, token, provider)
    except Exception as exc:
        status, payload = guard_missing_tables(exc)
        return jsonify(payload), status
    return jsonify(result), 201


@v1.route("/billing/activate", methods=["POST"])
@jwt_required(optional=True)
def activate_subscription():
    user_id = get_jwt_identity()
    data = request.get_json() or {}
    account_id = (
        _get_account_id(user_id)
        or getattr(g, "current_account_id", None)
        or data.get("account_id")
        or _lookup_account_id_by_email(data.get("email"))
    )
    if not account_id:
        return jsonify({"error": "Account not found"}), 404

    if not current_app.config.get("STRIPE_SECRET_KEY"):
        return jsonify({"error": "stripe api key missing"}), 500

    plan_choice = data.get("plan_choice") or "pro"
    provider = data.get("provider") or "stripe"
    email = data.get("email")
    if not email:
        return jsonify({"error": "email is required"}), 400
    # For Stripe, translate plan choice to price id.
    if provider == "stripe":
        price_id = _stripe_price_for_plan(plan_choice)
        if not price_id:
            return jsonify({"error": "stripe_price_missing", "plan": plan_choice}), 400
        plan_code = price_id
    else:
        plan_code = plan_choice

    billing = _get_service()
    profile = _get_or_create_profile(account_id, email, plan_choice)

    # Ensure we have a payment method and a Stripe customer before creating subscription.
    pm = None
    if profile.default_payment_method_id:
        pm = models.PaymentMethod.query.filter_by(id=profile.default_payment_method_id).first()
    if not pm:
        return jsonify({"error": "payment_method_missing"}), 400
    if pm.provider != provider:
        return jsonify({"error": "payment_method_provider_mismatch"}), 400

    try:
        ensure_idempotency(request.headers.get("Idempotency-Key"), "activate_api")
        # For Stripe, create/attach customer using the stored payment method before subscribing.
        if provider == "stripe":
            stripe_provider = billing._provider("stripe")
            customer = stripe_provider.create_customer(email=email, payment_method_id=pm.provider_payment_method_id)
            stripe_provider.attach_payment_method_to_customer(pm.provider_payment_method_id, customer["id"])
            customer_ref = customer["id"]
        else:
            customer_ref = profile.id

        result = billing._provider(provider).create_subscription(customer_ref=customer_ref, plan_code=plan_code)

        # Persist subscription/invoice in our DB.
        db_sub = models.Subscription(
            profile_id=profile.id,
            plan_id=None,
            provider=provider,
            provider_subscription_id=result.get("id"),
            status=result.get("status") or "active",
            current_period_end=None,
        )
        db.session.add(db_sub)

        inv = models.Invoice(
            profile_id=profile.id,
            subscription_id=db_sub.id,
            amount_cents=0,
            currency="GBP",
            status="paid" if db_sub.status == "active" else "open",
            provider=provider,
            provider_invoice_id=result.get("latest_invoice") if isinstance(result, dict) else None,
        )
        db.session.add(inv)
        profile.subscription_status = "active" if db_sub.status == "active" else db_sub.status
        profile.plan_choice = plan_choice
        profile.trial_status = "ended"
        db.session.commit()
        return jsonify(
            {
                "subscription": {"id": db_sub.id, "status": db_sub.status},
                "invoice": {"id": inv.id, "status": inv.status},
                "client_secret": result.get("client_secret") if isinstance(result, dict) else None,
            }
        ), 200
    except Exception as exc:
        status, payload = guard_missing_tables(exc)
        return jsonify(payload), status


@v1.route("/billing/invoices", methods=["GET"])
@jwt_required()
def list_invoices():
    user_id = get_jwt_identity()
    account_id = _get_account_id(user_id)
    if not account_id:
        return jsonify({"error": "Account not found"}), 404
    try:
        billing = _get_service()
        profile = models.CustomerBillingProfile.query.filter_by(account_id=account_id).first()
        if not profile:
            return jsonify({"invoices": []})
        invoices = billing.list_invoices(profile)
    except Exception as exc:
        status, payload = guard_missing_tables(exc)
        return jsonify(payload), status
    return jsonify({"invoices": invoices})


@v1.route("/billing/invoices/<invoice_id>", methods=["GET"])
@jwt_required()
def get_invoice(invoice_id: str):
    try:
        inv = models.Invoice.query.get(invoice_id)
    except Exception as exc:
        status, payload = guard_missing_tables(exc)
        return jsonify(payload), status
    if not inv:
        return jsonify({"error": "Invoice not found"}), 404
    return jsonify(
        {
            "id": inv.id,
            "status": inv.status,
            "amount_cents": inv.amount_cents,
            "currency": inv.currency,
            "provider": inv.provider,
            "pdf_url": inv.pdf_url,
            "due_at": inv.due_at.isoformat() if inv.due_at else None,
        }
    )


@v1.route("/billing/retry/<invoice_id>", methods=["POST"])
@jwt_required()
def retry_invoice(invoice_id: str):
    try:
        inv = models.Invoice.query.get(invoice_id)
    except Exception as exc:
        status, payload = guard_missing_tables(exc)
        return jsonify(payload), status
    if not inv:
        return jsonify({"error": "Invoice not found"}), 404
    billing = _get_service()
    data = request.get_json() or {}
    try:
        result = billing.retry_invoice(inv, use_provider=data.get("provider"))
    except Exception as exc:
        status, payload = guard_missing_tables(exc)
        return jsonify(payload), status
    return jsonify(result)


@v1.route("/billing/webhooks/stripe", methods=["POST"])
def webhook_stripe():
    billing = _get_service()
    payload = request.get_json() or {}
    result = billing.handle_webhook("stripe", payload, dict(request.headers))
    return jsonify(result)


@v1.route("/billing/webhooks/secondary", methods=["POST"])
def webhook_secondary():
    billing = _get_service()
    payload = request.get_json() or {}
    result = billing.handle_webhook("secondary", payload, dict(request.headers))
    return jsonify(result)


@v1.route("/billing/barclay/initiate", methods=["POST"])
@jwt_required()
def barclay_initiate():
    """Build a hosted payment payload; does not call Barclays network (stub until credentials/soap client)."""
    data = request.get_json() or {}
    amount_cents = data.get("amount_cents")
    currency = data.get("currency", "GBP")
    description = data.get("description", "InboxIQ Subscription")
    trans_ref = data.get("transaction_reference") or data.get("trans_no") or "temp-ref"
    billing_addr = data.get("billing_address") or {}
    try:
        provider = BarclayHostedProvider()
        result = provider.begin_web_payment(
            {
                "amount_cents": amount_cents or 0,
                "currency": currency,
                "description": description,
                "transaction_reference": trans_ref,
                "billingAddress": billing_addr,
            }
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(result)


@v1.route("/billing/barclay/callback", methods=["POST"])
def barclay_callback():
    """Handle hosted payment return; this is a stub that echoes the payload."""
    data = request.get_json() or {}
    transaction_reference = data.get("transaction_reference") or data.get("transNo") or "unknown"
    status = data.get("status") or data.get("paymentStatus") or "pending"
    provider = BarclayHostedProvider()
    result = provider.handle_callback(transaction_reference, status, data)
    return jsonify(result)
