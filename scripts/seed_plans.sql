-- InboxIQ plan seed — run once after migration 905fa2fad69f
-- Uses INSERT ... ON CONFLICT so it works whether rows exist or not.

-- ── Pro ─────────────────────────────────────────────────────────
INSERT INTO plans (
  id, code, price_cents, currency, seats,
  ai_decisions_limit,
  chat_enabled, automation_enabled, content_gen_enabled,
  lead_discovery_enabled, nurture_enabled, distribution_enabled,
  api_access_enabled, registered_apps_limit,
  stripe_ai_overage_price_id,
  metadata
) VALUES (
  gen_random_uuid()::text, 'pro', 4900, 'GBP', 2,
  1000,
  false, false, false,
  false, false, false,
  false, 0,
  'price_1T3QtBJSevdfPcyKqixrbQD2',
  '{}'
) ON CONFLICT (code) DO UPDATE SET
  price_cents=EXCLUDED.price_cents,
  seats=EXCLUDED.seats,
  ai_decisions_limit=EXCLUDED.ai_decisions_limit,
  chat_enabled=EXCLUDED.chat_enabled,
  automation_enabled=EXCLUDED.automation_enabled,
  content_gen_enabled=EXCLUDED.content_gen_enabled,
  lead_discovery_enabled=EXCLUDED.lead_discovery_enabled,
  nurture_enabled=EXCLUDED.nurture_enabled,
  distribution_enabled=EXCLUDED.distribution_enabled,
  api_access_enabled=EXCLUDED.api_access_enabled,
  registered_apps_limit=EXCLUDED.registered_apps_limit,
  stripe_ai_overage_price_id=EXCLUDED.stripe_ai_overage_price_id;

-- ── Business ─────────────────────────────────────────────────────
INSERT INTO plans (
  id, code, price_cents, currency, seats,
  ai_decisions_limit, chat_enabled, chat_limit,
  automation_enabled, automation_runs_limit,
  content_gen_enabled, content_posts_limit,
  nurture_enabled, nurture_emails_limit,
  lead_discovery_enabled, distribution_enabled,
  api_access_enabled, registered_apps_limit,
  stripe_ai_overage_price_id,
  stripe_chat_overage_price_id,
  stripe_automation_overage_price_id,
  stripe_nurture_overage_price_id,
  metadata
) VALUES (
  gen_random_uuid()::text, 'business', 14900, 'GBP', 5,
  5000, true, 200,
  true, 500,
  true, 8,
  true, 2000,
  false, false,
  true, 2,
  'price_1T3QtBJSevdfPcyKO7az2Bnh',
  'price_1T3QtCJSevdfPcyKdXODzJ41',
  'price_1T3QtDJSevdfPcyKWvbnclxe',
  'price_1T3QtDJSevdfPcyK5YUJsopX',
  '{}'
) ON CONFLICT (code) DO UPDATE SET
  price_cents=EXCLUDED.price_cents,
  seats=EXCLUDED.seats,
  ai_decisions_limit=EXCLUDED.ai_decisions_limit,
  chat_enabled=EXCLUDED.chat_enabled, chat_limit=EXCLUDED.chat_limit,
  automation_enabled=EXCLUDED.automation_enabled, automation_runs_limit=EXCLUDED.automation_runs_limit,
  content_gen_enabled=EXCLUDED.content_gen_enabled, content_posts_limit=EXCLUDED.content_posts_limit,
  nurture_enabled=EXCLUDED.nurture_enabled, nurture_emails_limit=EXCLUDED.nurture_emails_limit,
  lead_discovery_enabled=EXCLUDED.lead_discovery_enabled,
  distribution_enabled=EXCLUDED.distribution_enabled,
  api_access_enabled=EXCLUDED.api_access_enabled, registered_apps_limit=EXCLUDED.registered_apps_limit,
  stripe_ai_overage_price_id=EXCLUDED.stripe_ai_overage_price_id,
  stripe_chat_overage_price_id=EXCLUDED.stripe_chat_overage_price_id,
  stripe_automation_overage_price_id=EXCLUDED.stripe_automation_overage_price_id,
  stripe_nurture_overage_price_id=EXCLUDED.stripe_nurture_overage_price_id;

-- ── Scale ────────────────────────────────────────────────────────
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
  'price_1T3QtEJSevdfPcyKwEr1qCZM',
  'price_1T3QtEJSevdfPcyK0J9Cq240',
  'price_1T3QtFJSevdfPcyKSv89eccb',
  'price_1T3QtGJSevdfPcyKtq1lPtMK',
  'price_1T3QtGJSevdfPcyKGoEpkwEj',
  '{}'
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

-- ── Enterprise ───────────────────────────────────────────────
INSERT INTO plans (
  id, code, price_cents, currency, seats,
  ai_decisions_limit, chat_enabled, chat_limit,
  automation_enabled, automation_runs_limit,
  content_gen_enabled, content_posts_limit,
  nurture_enabled, nurture_emails_limit,
  lead_discovery_enabled, leads_limit,
  distribution_enabled,
  api_access_enabled, registered_apps_limit,
  metadata
) VALUES (
  gen_random_uuid()::text, 'enterprise', 0, 'GBP', NULL,
  NULL, true, NULL,
  true, NULL,
  true, NULL,
  true, NULL,
  true, NULL,
  true,
  true, -1,
  '{"custom_invoiced": true, "value_based_pricing": true}'
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
  metadata=EXCLUDED.metadata;

-- Verify
SELECT code, price_cents, seats, ai_decisions_limit, chat_enabled, automation_enabled,
       stripe_ai_overage_price_id IS NOT NULL AS has_ai_overage
FROM plans ORDER BY price_cents;
