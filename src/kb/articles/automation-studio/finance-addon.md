# Finance Add-on — Stripe to QuickBooks

The Finance Add-on automates Stripe payment events into QuickBooks. When a Stripe payment notification arrives in your inbox, InboxIQ detects and labels it as a transaction, then either syncs it to QuickBooks in real time or includes it in a weekly CSV export sent to your email.

Available on **Business and Enterprise** plans.

## How it works

Stripe sends a payment confirmation email to your connected inbox. InboxIQ classifies it as a `transaction` and fires the Finance Add-on automation, which:

- **Direct sync mode** — posts the transaction to QuickBooks via the API immediately.
- **CSV export mode** — batches transactions and emails you an Intuit-compatible CSV every Monday at 08:00 UTC.

No separate Stripe webhook configuration is needed. The email is the trigger.

## Set up the Finance Add-on

1. Go to **Settings → Integrations → Finance Add-on** (or click the Finance Add-on card in Automation Studio).
2. If the add-on is not active, click **Upgrade to unlock →** to upgrade your plan.
3. Once on a Business or Enterprise plan, the setup wizard opens automatically.

### Step 1 — Connect Stripe

Select the Stripe webhook provider that receives your payment events from the dropdown. If you haven't added one yet, click **+ Add a new Stripe provider first →** to go to Webhook Providers and add it, then return here.

### Step 2 — Choose output mode

Select how processed transactions should be handled:

- **⚡ Direct sync** — transactions are posted to QuickBooks via the API in real time.
- **📎 CSV export** — transactions are batched and emailed to you as an Intuit-compatible CSV every Monday at 08:00 UTC.

### Step 3 — Connect QuickBooks (direct sync only)

If you chose Direct sync, select your QuickBooks provider from the dropdown. If you haven't added one yet, click **+ Add a new QuickBooks provider first →**.

For CSV export, no further input is needed — the CSV goes to your account owner's email address automatically.

4. Click **Activate add-on ⚡**.

## Reconfigure or deactivate

From the Finance Add-on page, when the add-on is active:

- **Reconfigure** — opens the setup wizard again. The add-on stays active until you submit new settings.
- **Deactivate** — stops processing immediately. Your configuration is saved and can be reactivated later.

## Adding webhook providers

Stripe and QuickBooks providers are managed in **Settings → Integrations → Webhook Providers**. You need at least one enabled Stripe provider before activating the Finance Add-on. For direct sync mode, you also need an enabled QuickBooks provider.

## CSV export format

The weekly CSV uses Intuit-compatible column headers and can be imported directly into QuickBooks Desktop or QuickBooks Online via the Import Data feature. The file is sent as an email attachment every Monday at 08:00 UTC to the account owner's email address.

## Frequently asked questions

**Do I need to configure a Stripe webhook separately?**
No. InboxIQ detects Stripe payment confirmation emails directly. The email notification from Stripe is the trigger — no webhook endpoint setup required.

**What if I have multiple Stripe accounts?**
Add each as a separate Stripe webhook provider in Settings → Integrations → Webhook Providers, then select the correct one during Finance Add-on setup.

**Can I change from CSV export to direct sync later?**
Yes. Click **Reconfigure** on the Finance Add-on page, go through the wizard, select Direct sync, and submit. The change takes effect immediately.

**Which QuickBooks versions are supported?**
Direct sync uses the QuickBooks Online API. CSV export is compatible with both QuickBooks Online and QuickBooks Desktop via the Import Data feature.
