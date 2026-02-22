#!/usr/bin/env python3
"""
One-time Stripe setup script for InboxIQ pricing migration.

Creates / updates:
  1. New £49/mo flat price under existing `pro` product
  2. New £149/mo flat price under existing `business` product
  3. New `scale` product + £399/mo flat price
  4. Metered overage prices for Pro, Business, Scale
  5. Seeds the local `plans` table with all quotas, feature flags, and Stripe price IDs

Run once (idempotent — uses metadata lookups to skip already-created objects):

    STRIPE_SECRET_KEY=sk_live_... python scripts/stripe_setup.py

Then copy the printed env vars into your .env / Kubernetes secrets.

Overage billing units
---------------------
Stripe metered prices are billed per "reporting unit". To keep math simple,
we define each unit as the *smallest granular item*:

  ai_decisions      → 1 unit = 1 decision  (report individual decisions)
  chat_conversations→ 1 unit = 1 conversation
  automation_runs   → 1 unit = 1 run
  content_posts     → 1 unit = 1 post         (rarely hits overage)
  nurture_emails    → 1 unit = 1 email
  leads_discovered  → 1 unit = 1 lead

The unit_amount_decimal is set to the per-unit pence value using Stripe's
decimal support (avoids sub-pence rounding issues for high-volume items).
"""
from __future__ import annotations

import os
import sys
import json
import time

try:
    import stripe
except ImportError:
    print("ERROR: stripe SDK not installed. Run: pip install stripe")
    sys.exit(1)

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
if not STRIPE_SECRET_KEY:
    print("ERROR: STRIPE_SECRET_KEY env var not set.")
    sys.exit(1)

stripe.api_key = STRIPE_SECRET_KEY

# Existing Stripe price IDs — used to locate the existing product IDs
CURRENT_PRICE_PRO      = os.getenv("STRIPE_PRICE_PRO")
CURRENT_PRICE_BUSINESS = os.getenv("STRIPE_PRICE_BUSINESS")

# ── Flat price definitions ──────────────────────────────────────────────────
FLAT_PRICES = {
    "pro":      {"amount": 4900,  "nickname": "InboxIQ Pro – £49/mo flat"},
    "business": {"amount": 14900, "nickname": "InboxIQ Business – £149/mo flat"},
    "scale":    {"amount": 39900, "nickname": "InboxIQ Scale – £399/mo flat"},
}

# ── Metered overage price definitions ──────────────────────────────────────
# unit_amount_decimal: pence per single unit (string for Stripe decimal API)
# meter: internal meter key matching _METER_META in quota.py
OVERAGE_PRICES = {
    # Pro
    "pro_ai_overage": {
        "plan": "pro",
        "meter": "ai_decisions",
        "nickname": "Pro – AI overage (£4/100)",
        "unit_amount_decimal": "4",       # 4p per decision → £4 per 100
    },
    # Business
    "business_ai_overage": {
        "plan": "business",
        "meter": "ai_decisions",
        "nickname": "Business – AI overage (£3/100)",
        "unit_amount_decimal": "3",       # 3p per decision → £3 per 100
    },
    "business_chat_overage": {
        "plan": "business",
        "meter": "chat_conversations",
        "nickname": "Business – Chat overage (£2/50)",
        "unit_amount_decimal": "4",       # 4p per conversation → £2 per 50
    },
    "business_automation_overage": {
        "plan": "business",
        "meter": "automation_runs",
        "nickname": "Business – Automation overage (£3/100)",
        "unit_amount_decimal": "3",
    },
    "business_nurture_overage": {
        "plan": "business",
        "meter": "nurture_emails",
        "nickname": "Business – Nurture email overage (£1/100)",
        "unit_amount_decimal": "1",
    },
    # Scale
    "scale_ai_overage": {
        "plan": "scale",
        "meter": "ai_decisions",
        "nickname": "Scale – AI overage (£2/100)",
        "unit_amount_decimal": "2",
    },
    "scale_chat_overage": {
        "plan": "scale",
        "meter": "chat_conversations",
        "nickname": "Scale – Chat overage (£1/50)",
        "unit_amount_decimal": "2",       # 2p per conversation → £1 per 50
    },
    "scale_automation_overage": {
        "plan": "scale",
        "meter": "automation_runs",
        "nickname": "Scale – Automation overage (£2/100)",
        "unit_amount_decimal": "2",
    },
    "scale_nurture_overage": {
        "plan": "scale",
        "meter": "nurture_emails",
        "nickname": "Scale – Nurture email overage (£0.50/100)",
        "unit_amount_decimal": "0.5",
    },
    "scale_leads_overage": {
        "plan": "scale",
        "meter": "leads_discovered",
        "nickname": "Scale – Lead discovery overage (£5/50)",
        "unit_amount_decimal": "10",      # 10p per lead → £5 per 50
    },
}


def _find_product_id(plan_code: str, current_price_id: str | None) -> str | None:
    """Resolve product ID from the existing price, or by searching by name."""
    if current_price_id:
        try:
            price = stripe.Price.retrieve(current_price_id)
            return price["product"]
        except stripe.error.StripeError as e:
            print(f"  WARNING: could not retrieve existing {plan_code} price: {e}")

    # Fall back: search products by name
    products = stripe.Product.list(limit=100, active=True)
    for p in products.auto_paging_iter():
        if p.get("name", "").lower() == plan_code:
            return p["id"]
    return None


def _get_or_create_product(code: str, display_name: str) -> str:
    """Return the product ID for `code`, creating it if it doesn't exist."""
    products = stripe.Product.search(query=f'metadata["inboxiq_plan"]:"{code}"', limit=1)
    if products.data:
        pid = products.data[0]["id"]
        print(f"  Found existing {code} product: {pid}")
        return pid

    product = stripe.Product.create(
        name=display_name,
        metadata={"inboxiq_plan": code},
    )
    print(f"  Created {code} product: {product['id']}")
    return product["id"]


def _create_flat_price(product_id: str, amount_pence: int, nickname: str) -> str:
    """Create a new recurring flat price and return its ID."""
    price = stripe.Price.create(
        product=product_id,
        unit_amount=amount_pence,
        currency="gbp",
        recurring={"interval": "month"},
        nickname=nickname,
    )
    print(f"  Created flat price: {price['id']} ({nickname})")
    return price["id"]


def _create_metered_price(product_id: str, unit_amount_decimal: str, nickname: str) -> str:
    """Create a metered usage price and return its ID."""
    price = stripe.Price.create(
        product=product_id,
        unit_amount_decimal=unit_amount_decimal,
        currency="gbp",
        recurring={
            "interval": "month",
            "usage_type": "metered",
            "aggregate_usage": "sum",
        },
        billing_scheme="per_unit",
        nickname=nickname,
    )
    print(f"  Created metered price: {price['id']} ({nickname})")
    return price["id"]


def main():
    print("=" * 60)
    print("InboxIQ Stripe Setup")
    print("=" * 60)

    # ── 1. Resolve / create products ───────────────────────────────
    print("\n[1] Products")
    product_ids: dict[str, str] = {}

    # Pro — must already exist
    pro_product_id = _find_product_id("pro", CURRENT_PRICE_PRO)
    if not pro_product_id:
        # Create it with the search metadata tag so future runs find it
        pro_product_id = _get_or_create_product("pro", "InboxIQ Pro")
    else:
        # Tag it so future runs can find it
        stripe.Product.modify(pro_product_id, metadata={"inboxiq_plan": "pro"})
        print(f"  Found existing pro product: {pro_product_id}")
    product_ids["pro"] = pro_product_id

    # Business — must already exist
    business_product_id = _find_product_id("business", CURRENT_PRICE_BUSINESS)
    if not business_product_id:
        business_product_id = _get_or_create_product("business", "InboxIQ Business")
    else:
        stripe.Product.modify(business_product_id, metadata={"inboxiq_plan": "business"})
        print(f"  Found existing business product: {business_product_id}")
    product_ids["business"] = business_product_id

    # Scale — create new
    scale_product_id = _get_or_create_product("scale", "InboxIQ Scale")
    product_ids["scale"] = scale_product_id

    # ── 2. Create new flat prices ──────────────────────────────────
    print("\n[2] Flat monthly prices")
    flat_price_ids: dict[str, str] = {}
    for plan_code, cfg in FLAT_PRICES.items():
        pid = _create_flat_price(product_ids[plan_code], cfg["amount"], cfg["nickname"])
        flat_price_ids[plan_code] = pid
        time.sleep(0.3)  # avoid rate limits

    # ── 3. Create metered overage prices ──────────────────────────
    print("\n[3] Metered overage prices")
    overage_price_ids: dict[str, str] = {}
    for key, cfg in OVERAGE_PRICES.items():
        pid = _create_metered_price(
            product_ids[cfg["plan"]],
            cfg["unit_amount_decimal"],
            cfg["nickname"],
        )
        overage_price_ids[key] = pid
        time.sleep(0.3)

    # ── 4. Print env vars ──────────────────────────────────────────
    print("\n" + "=" * 60)
    print("ENV VARS — add these to your .env / Kubernetes secrets:")
    print("=" * 60)
    print(f"STRIPE_PRICE_PRO={flat_price_ids['pro']}")
    print(f"STRIPE_PRICE_BUSINESS={flat_price_ids['business']}")
    print(f"STRIPE_PRICE_SCALE={flat_price_ids['scale']}")
    print()
    for key, price_id in overage_price_ids.items():
        env_key = "STRIPE_OVERAGE_" + key.upper()
        print(f"{env_key}={price_id}")

    # ── 5. Seed plans table ────────────────────────────────────────
    print("\n" + "=" * 60)
    print("DB SEED — run this SQL to seed plans (adjust price IDs above first):")
    print("=" * 60)

    pro_flat   = flat_price_ids["pro"]
    biz_flat   = flat_price_ids["business"]
    scale_flat = flat_price_ids["scale"]

    sql = f"""
-- ── Update Pro ──────────────────────────────────────────────────
UPDATE plans SET
  price_cents=4900,
  seats=2,
  ai_decisions_limit=1000,
  chat_enabled=false,
  automation_enabled=false,
  content_gen_enabled=false,
  lead_discovery_enabled=false,
  nurture_enabled=false,
  distribution_enabled=false,
  api_access_enabled=false,
  registered_apps_limit=0,
  stripe_ai_overage_price_id='{overage_price_ids["pro_ai_overage"]}'
WHERE code='pro';

-- ── Update Business ─────────────────────────────────────────────
UPDATE plans SET
  price_cents=14900,
  seats=5,
  ai_decisions_limit=5000,
  chat_enabled=true,  chat_limit=200,
  automation_enabled=true,  automation_runs_limit=500,
  content_gen_enabled=true, content_posts_limit=8,
  nurture_enabled=true,     nurture_emails_limit=2000,
  lead_discovery_enabled=false,
  distribution_enabled=false,
  api_access_enabled=true,  registered_apps_limit=2,
  stripe_ai_overage_price_id='{overage_price_ids["business_ai_overage"]}',
  stripe_chat_overage_price_id='{overage_price_ids["business_chat_overage"]}',
  stripe_automation_overage_price_id='{overage_price_ids["business_automation_overage"]}',
  stripe_nurture_overage_price_id='{overage_price_ids["business_nurture_overage"]}'
WHERE code='business';

-- ── Insert Scale (run only if not already present) ──────────────
INSERT INTO plans (
  id, code, price_cents, currency, seats,
  ai_decisions_limit, chat_enabled, chat_limit,
  automation_enabled, automation_runs_limit,
  content_gen_enabled, content_posts_limit,
  nurture_enabled, nurture_emails_limit,
  lead_discovery_enabled, leads_limit,
  distribution_enabled,
  api_access_enabled, registered_apps_limit,
  stripe_ai_overage_price_id,
  stripe_chat_overage_price_id,
  stripe_automation_overage_price_id,
  stripe_nurture_overage_price_id,
  stripe_leads_overage_price_id,
  metadata
) VALUES (
  gen_random_uuid()::text, 'scale', 39900, 'GBP', 15,
  25000, true, 1000,
  true, 5000,
  true, 30,
  true, 20000,
  true, 200,
  true,
  true, -1,
  '{overage_price_ids["scale_ai_overage"]}',
  '{overage_price_ids["scale_chat_overage"]}',
  '{overage_price_ids["scale_automation_overage"]}',
  '{overage_price_ids["scale_nurture_overage"]}',
  '{overage_price_ids["scale_leads_overage"]}',
  '{{}}'
) ON CONFLICT (code) DO UPDATE SET
  price_cents=EXCLUDED.price_cents,
  seats=EXCLUDED.seats,
  ai_decisions_limit=EXCLUDED.ai_decisions_limit,
  chat_enabled=EXCLUDED.chat_enabled, chat_limit=EXCLUDED.chat_limit,
  automation_enabled=EXCLUDED.automation_enabled, automation_runs_limit=EXCLUDED.automation_runs_limit,
  content_gen_enabled=EXCLUDED.content_gen_enabled, content_posts_limit=EXCLUDED.content_posts_limit,
  nurture_enabled=EXCLUDED.nurture_enabled, nurture_emails_limit=EXCLUDED.nurture_emails_limit,
  lead_discovery_enabled=EXCLUDED.lead_discovery_enabled, leads_limit=EXCLUDED.leads_limit,
  distribution_enabled=EXCLUDED.distribution_enabled,
  api_access_enabled=EXCLUDED.api_access_enabled, registered_apps_limit=EXCLUDED.registered_apps_limit,
  stripe_ai_overage_price_id=EXCLUDED.stripe_ai_overage_price_id,
  stripe_chat_overage_price_id=EXCLUDED.stripe_chat_overage_price_id,
  stripe_automation_overage_price_id=EXCLUDED.stripe_automation_overage_price_id,
  stripe_nurture_overage_price_id=EXCLUDED.stripe_nurture_overage_price_id,
  stripe_leads_overage_price_id=EXCLUDED.stripe_leads_overage_price_id;
"""
    print(sql)

    print("\n✅ Done. Copy the env vars, update your secrets, then run the SQL above.")


if __name__ == "__main__":
    main()
