# Automation Studio: Invoice & Receipt Extraction

Extract invoice and receipt data from emails and send directly to your accounting software (Sage, QuickBooks, etc.) using Automation Studio rules.

## Overview

InboxIQ's Automation Studio can automatically:
- Detect invoices and receipts in incoming emails
- Extract structured data using AI (invoice numbers, amounts, vendors, etc.)
- Send data directly to configured accounting providers via webhooks
- Tag and organize accounting-related emails

## Prerequisites

1. **Configure Provider Credentials**: Navigate to [Settings → Integrations → Webhooks](/settings/integrations?tab=integrations&view=webhooks) and add your accounting provider (Sage, QuickBooks, Slack, or Custom Webhook)

2. **Generate Intake Token**: Create an API token for automation rules to authenticate webhook calls

3. **Enable Automation Studio**: Ensure your plan includes automation features

---

## Two Integration Approaches

InboxIQ supports **two distinct methods** for processing invoices and receipts. Choose the approach that best fits your workflow:

### Approach 1: Email-Based Processing (Default)

**How it works:**
```
Payment Processor → Email Receipt → Your Gmail/Outlook → InboxIQ (Email Integration)
→ AI Extracts Data → Automation Rule → Sage/QuickBooks API
```

**Best for:**
- Processing receipts from payment processors (Stripe, Square, PayPal, etc.) that send email confirmations
- Vendor invoices received via email
- Historical email data already in your inbox
- Simple setup with no additional API configuration

**Configuration:**
1. Connect your email account (Gmail/Outlook) to InboxIQ
2. Configure automation rules to detect invoices/receipts by:
   - Sender email (e.g., `payment@stripe.com`, `receipts@square.com`)
   - Subject keywords (e.g., "invoice", "receipt", "payment confirmation")
   - Attachment type (PDF, images)
3. Configure destination accounting software (Sage/QuickBooks)

**Supported Payment Processors (Email):**
- Stripe (`payment@stripe.com`)
- Square (`receipts@square.com`)
- PayPal (`service@paypal.com`)
- Braintree (`donotreply@braintree.com`)
- Authorize.net (`noreply@authorize.net`)

---

### Approach 2: Direct API Integration (Advanced)

**How it works:**
```
Payment Processor Webhook → InboxIQ /api/v1/intake → Verify Signature
→ Transform Data → Sage/QuickBooks API (Real-time)
```

**Best for:**
- Real-time payment processing (no email delay)
- High transaction volumes
- Webhook-based integrations
- Pulling historical transaction data for reconciliation
- Direct data flow without email intermediary

**Configuration:**
1. **In InboxIQ**: Add payment processor to [Provider Configurations](/settings/integrations?tab=integrations&view=webhooks)
   - **Stripe**: Webhook signing secret + optional API key
   - **Square**: Webhook signature key + optional access token
   - **PayPal**: Webhook ID + optional client credentials
2. **In Payment Processor Dashboard**: Configure webhook URL pointing to InboxIQ:
   ```
   https://yourdomain.com/api/v1/intake
   ```
3. **Webhook Verification**: InboxIQ automatically verifies webhook signatures for security
4. **Destination**: Configure where to send data (Sage, QuickBooks, Slack)

**Features:**
- ✅ **Real-time**: Process payments instantly (no email delay)
- ✅ **Signature Verification**: Secure webhook authentication
- ✅ **Historical Data**: Pull past transactions using API credentials
- ✅ **Reconciliation**: Sync data on-demand for auditing
- ✅ **Higher Reliability**: No dependency on email delivery

**Example Stripe Configuration:**
```javascript
// In Stripe Dashboard → Webhooks
Webhook URL: https://yourdomain.com/api/v1/intake
Events: payment_intent.succeeded, charge.succeeded

// In InboxIQ Provider Modal
Provider: Stripe
Webhook Signing Secret: whsec_xxxxx (for signature verification)
API Key (optional): sk_live_xxxxx (for pulling historical data)
Destination: Sage Accounting
```

---

## Choosing the Right Approach

| Feature | Email-Based | Direct API |
|---------|-------------|------------|
| **Setup Complexity** | Simple | Moderate |
| **Real-time Processing** | No (email delay) | Yes |
| **Historical Data Sync** | Manual | Automated |
| **Reliability** | Depends on email | High |
| **Security** | Email forwarding | Webhook signatures |
| **Best For** | Small businesses, simple workflows | High-volume, real-time needs |

**Recommendation**: Start with **Email-Based** for simplicity, then migrate to **Direct API** as transaction volume grows or real-time processing becomes critical.

---

## Example 1: Invoice Extraction → Sage (Email-Based)

**Use Case**: Automatically extract invoice data from vendor emails and create invoices in Sage Accounting.

### Rule Configuration

```yaml
Rule Name: "Extract Invoices to Sage"
Trigger: Email contains invoice attachment OR subject contains "invoice"

Conditions:
  - Email has PDF attachment
  - Subject matches pattern: /invoice|bill|payment due/i
  - From domain is trusted vendor list

Actions:
  1. Extract Invoice Data (AI)
     - Invoice number
     - Vendor name
     - Total amount
     - Currency
     - Due date
     - Line items (description, quantity, unit price)

  2. Send to Webhook Provider: "Sage Accounting"
     POST to configured Sage endpoint

     Payload:
     {
       "invoice_number": "{{extracted.invoice_number}}",
       "vendor_name": "{{extracted.vendor_name}}",
       "total_amount": {{extracted.total_amount}},
       "currency": "{{extracted.currency}}",
       "due_date": "{{extracted.due_date}}",
       "line_items": [
         {
           "description": "{{item.description}}",
           "quantity": {{item.quantity}},
           "unit_price": {{item.unit_price}}
         }
       ],
       "source": "automation_studio",
       "original_email_id": "{{email.id}}"
     }

  3. Tag Email: "invoice_processed"
  4. Move to Folder: "Accounting/Invoices"
```

### Expected Behavior

1. Email arrives with invoice PDF attachment
2. AI extracts invoice data automatically
3. Webhook sends structured data to Sage API using stored credentials
4. Sage creates new invoice record
5. Email tagged and moved to designated folder

---

## Example 2: Receipt Extraction → QuickBooks (Email-Based)

**Use Case**: Capture payment receipts from Stripe, PayPal, Square email confirmations and sync to QuickBooks.

### Rule Configuration

```yaml
Rule Name: "Extract Receipts to QuickBooks"
Trigger: Email subject contains "receipt" OR "payment confirmation"

Conditions:
  - Email from: payment@stripe.com, receipts@square.com, noreply@paypal.com
  - Contains payment amount pattern: $XX.XX or €XX.XX
  - Received in last 24 hours

Actions:
  1. Extract Receipt Data (AI)
     - Receipt number
     - Customer name/email
     - Payment amount
     - Payment method (card, ACH, PayPal)
     - Payment date
     - Transaction ID

  2. Send to Webhook Provider: "QuickBooks Production"
     POST to configured QuickBooks endpoint

     Payload:
     {
       "receipt_number": "{{extracted.receipt_number}}",
       "customer_email": "{{extracted.customer_email}}",
       "payment_amount": {{extracted.payment_amount}},
       "payment_method": "{{extracted.payment_method}}",
       "payment_date": "{{extracted.payment_date}}",
       "transaction_id": "{{extracted.transaction_id}}",
       "source": "automation_studio",
       "metadata": {
         "processed_at": "{{now}}",
         "processor": "stripe"
       }
     }

  3. Create Internal Note: "Receipt synced to QuickBooks"
  4. Send Confirmation Email to Finance Team
```

### Payment Processor Support

The AI extraction works with receipts from:
- **Stripe** - payment@stripe.com
- **Square** - receipts@square.com
- **PayPal** - service@paypal.com
- **Braintree** - donotreply@braintree.com
- **Authorize.net** - noreply@authorize.net

---

## Example 3: Employee Expense Receipts

**Use Case**: Employees forward expense receipts to expenses@company.com for automatic processing and approval routing.

### Rule Configuration

```yaml
Rule Name: "Employee Expense Receipts"
Trigger: Email to expenses@company.com with attachment

Conditions:
  - From domain: @company.com (employees only)
  - Has image/PDF attachment (receipt photo)
  - Subject contains: "expense" OR "reimbursement"

Actions:
  1. OCR + AI Extraction
     - Merchant name
     - Expense category (meals, travel, office supplies)
     - Amount
     - Date
     - Employee name (from sender)

  2. Route Based on Amount:
     IF amount < $100:
       - Send to Webhook: "QuickBooks Auto-Approve"
     ELSE:
       - Send to Webhook: "Slack Approval Channel"
       - Create approval task in system

  3. Store Receipt:
     - Upload to S3: s3://expenses/{{employee_id}}/{{date}}/
     - Generate public URL (7-day expiry)

  4. Send Webhook Payload:
     {
       "expense_type": "employee_reimbursement",
       "employee_email": "{{email.from}}",
       "merchant": "{{extracted.merchant}}",
       "category": "{{extracted.category}}",
       "amount": {{extracted.amount}},
       "receipt_url": "{{s3.public_url}}",
       "requires_approval": {{amount >= 100}},
       "submitted_at": "{{email.received_at}}"
     }
```

### Approval Workflow

- **Under $100**: Automatically approved and sent to QuickBooks
- **$100+**: Sent to Slack channel for manager approval
- **Approved**: Forwarded to QuickBooks
- **Rejected**: Email notification to employee with reason

---

## Example 4: Direct Stripe Integration → Sage (API-Based)

**Use Case**: Real-time payment processing - Stripe webhooks send payment data directly to InboxIQ, which immediately forwards to Sage Accounting.

### Configuration Steps

**Step 1: Configure Stripe Provider in InboxIQ**

Navigate to **Settings → Integrations → Webhooks** → Click **"+ Add Provider"** → Select **"Stripe"**

```
Configuration Name: Production Stripe
Webhook Signing Secret: whsec_xxxxxxxxxxxxx (from Stripe Dashboard → Webhooks)
API Key (optional): sk_live_xxxxxxxxxxxxx (for pulling historical transactions)
Destination: Sage Accounting
```

**Step 2: Configure Webhook in Stripe Dashboard**

1. Go to Stripe Dashboard → **Developers** → **Webhooks**
2. Click **"Add endpoint"**
3. Configure webhook:
   ```
   Endpoint URL: https://yourdomain.com/api/v1/intake
   Events to send:
     - payment_intent.succeeded
     - charge.succeeded
     - invoice.payment_succeeded
   ```
4. Copy the **Signing Secret** (whsec_...) and add it to InboxIQ provider configuration

**Step 3: How It Works**

```
Stripe Payment → Webhook Fired → InboxIQ /api/v1/intake
→ Verify Stripe Signature (using webhook_secret)
→ Extract Payment Data (amount, customer, payment method)
→ Transform to Sage Invoice Format
→ POST to Sage API (using configured credentials)
→ Tag as "stripe_processed" in InboxIQ
```

### Webhook Payload Example

**Stripe sends to InboxIQ:**
```json
{
  "type": "payment_intent.succeeded",
  "data": {
    "object": {
      "id": "pi_3AbCdEf123",
      "amount": 50000,
      "currency": "usd",
      "customer": "cus_xxxxx",
      "description": "Invoice #INV-001",
      "receipt_email": "customer@example.com"
    }
  }
}
```

**InboxIQ transforms and sends to Sage:**
```json
{
  "invoice_number": "INV-001",
  "customer_name": "Acme Corp",
  "amount": 500.00,
  "currency": "USD",
  "payment_method": "Credit Card",
  "payment_date": "2026-02-09",
  "transaction_id": "pi_3AbCdEf123",
  "source": "stripe_webhook",
  "metadata": {
    "stripe_customer_id": "cus_xxxxx",
    "receipt_email": "customer@example.com"
  }
}
```

### Benefits Over Email-Based

| Feature | Email-Based | Direct API |
| --- | --- | --- |
| **Processing Speed** | 1-5 minutes (email delay) | <1 second (instant) |
| **Reliability** | 99% (email delivery) | 99.9% (direct webhook) |
| **Data Accuracy** | AI extraction from email text | Structured API data |
| **Historical Sync** | Manual | Automated (via API key) |
| **Transaction Volume** | Up to 1000/day | Unlimited |

### Reconciliation & Historical Data

If you provided the **API Key (optional)** during configuration, InboxIQ can pull historical transactions for reconciliation:

**Manual Reconciliation:**
1. Go to **Settings → Integrations → Webhooks**
2. Click on your Stripe provider
3. Click **"Sync Historical Data"**
4. Select date range (e.g., last 30 days)
5. InboxIQ pulls all transactions from Stripe API and syncs to Sage

**Automated Daily Reconciliation:**
- Configure a scheduled Celery task to run daily
- Pulls previous day's transactions from Stripe
- Compares with Sage records
- Reports discrepancies to Slack

---

## Configuring Webhook Providers

### Step 1: Add Provider

1. Navigate to **Settings → Integrations → Webhooks**
2. Scroll to **Configured Providers** section
3. Click **"+ Add Provider"** button

### Step 2: Select Provider Type

Choose from:

**Accounting Software (Destinations):**
- **Sage Accounting** - Sage API integration
- **Intuit QuickBooks** - QuickBooks Online API

**Payment Processors (Sources):**
- **Stripe** - Real-time payment webhooks + API
- **Square** - Payment processor integration
- **PayPal** - Payment notifications and API

**Notifications & Custom:**
- **Slack** - Send notifications to Slack channels
- **Custom Webhook** - Any REST API endpoint

### Step 3: Enter Credentials

**For Sage (Destination):**
- Configuration Name (e.g., "Production Sage")
- API Key (encrypted)
- Company ID
- Environment (production/sandbox)
- API Endpoint URL

**For QuickBooks (Destination):**
- Configuration Name (e.g., "QuickBooks Production")
- Client ID
- Client Secret (encrypted)
- Company ID (Realm ID)
- Environment (production/sandbox)

**For Stripe (Source):**
- Configuration Name (e.g., "Production Stripe")
- Webhook Signing Secret (whsec_...) - Required for webhook verification
- API Key (sk_live_... or sk_test_...) - Optional, for pulling historical data
- Destination Provider (where to send data: Sage, QuickBooks, Slack, or Custom)

**For Square (Source):**
- Configuration Name (e.g., "Production Square")
- Webhook Signature Key - Required for webhook verification
- Access Token - Optional, for pulling historical payments
- Environment (production/sandbox)
- Destination Provider (Sage, QuickBooks, Slack, or Custom)

**For PayPal (Source):**
- Configuration Name (e.g., "Production PayPal")
- Webhook ID - Required for webhook verification
- Client ID - Optional, for API access
- Client Secret - Optional, for API access
- Environment (production/sandbox)
- Destination Provider (Sage, QuickBooks, Slack, or Custom)

**For Slack (Notification):**
- Configuration Name
- Webhook URL (from Slack app)
- Default Channel (optional)

**For Custom:**
- Configuration Name
- Webhook URL
- Authorization Header (optional)
- Custom Headers JSON (optional)

### Step 4: Save & Test

1. Click **"Save Provider"**
2. Credentials encrypted and stored
3. Provider appears in Configured Providers list
4. Now available in Automation Studio rules

---

## Data Flow Diagram

```
┌─────────────────┐
│  Email Arrives  │
│  (with invoice) │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  AI Extraction  │
│  - Invoice #    │
│  - Amount       │
│  - Vendor       │
└────────┬────────┘
         │
         ▼
┌─────────────────────┐
│ Automation Rule     │
│ Fires & Validates   │
└────────┬────────────┘
         │
         ▼
┌─────────────────────────┐
│ Webhook Provider: Sage  │
│ (Uses stored creds)     │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────────┐
│ POST https://api.sage.com   │
│ Authorization: Bearer token │
│ {invoice_data}              │
└────────┬────────────────────┘
         │
         ▼
┌─────────────────────┐
│ Sage Creates        │
│ Invoice Record      │
└────────┬────────────┘
         │
         ▼
┌─────────────────┐
│ Email Tagged    │
│ "Processed ✓"   │
└─────────────────┘
```

---

## Webhook Payload Examples

### Invoice Payload (Sage)

```json
{
  "subject": "Invoice: Acme Corp - $500.00",
  "body": "Invoice #INV-001 created via automation studio",
  "source": "automation_studio",
  "metadata": {
    "invoice_number": "INV-001",
    "customer_name": "Acme Corp",
    "amount": 500.00,
    "currency": "USD",
    "due_date": "2026-03-09",
    "line_items": [
      {
        "description": "Consulting services",
        "quantity": 1,
        "unit_price": 500.00
      }
    ]
  }
}
```

### Receipt Payload (QuickBooks)

```json
{
  "subject": "Receipt: Payment received - $250.00",
  "body": "Payment from John Doe via Credit Card",
  "source": "automation_studio",
  "metadata": {
    "receipt_number": "RCP-123",
    "customer_email": "john@example.com",
    "payment_amount": 250.00,
    "payment_method": "Credit Card",
    "payment_date": "2026-02-09",
    "transaction_id": "ch_3AbCdEf123"
  }
}
```

---

## Security & Compliance

### Credential Encryption

- All API keys and secrets encrypted at rest
- AES-256 encryption standard
- Keys never exposed in logs or error messages
- Automatic rotation support (coming soon)

### Access Control

- Provider configurations scoped to account
- Only account owners can add/delete providers
- Audit log of all provider changes
- Rate limiting on webhook calls

### Data Privacy

- Invoice/receipt data only stored if configured
- Automatic deletion after processing (optional)
- GDPR compliant data handling
- SOC 2 Type II certified infrastructure

---

## Troubleshooting

### Issue: Invoices not being detected

**Solution:**
- Check trigger conditions (file type, subject pattern)
- Verify email source is in trusted list
- Review AI extraction confidence threshold
- Check automation rule logs for errors

### Issue: Webhook calls failing

**Solution:**
- Verify provider credentials are correct
- Check API endpoint URL is accessible
- Review Sage/QuickBooks API limits (rate limiting)
- Confirm account has active subscription
- Check webhook logs for detailed error messages

### Issue: Incorrect data extraction

**Solution:**
- Provide sample invoices to improve AI model
- Add extraction field mappings manually
- Use OCR preprocessing for scanned PDFs
- Verify document quality (clear, high-res images)

---

## Best Practices

1. **Start with Manual Review**: Enable approval workflow for first 10-20 invoices to verify accuracy

2. **Use Sandbox Environments**: Test with Sage/QuickBooks sandbox before production

3. **Set Amount Thresholds**: Require approval for invoices over $X

4. **Tag Everything**: Use consistent tagging for easy filtering and reporting

5. **Monitor Regularly**: Review automation logs weekly for errors or edge cases

6. **Keep Providers Updated**: Rotate API credentials quarterly for security

---

## API Reference

### Intake API Endpoint

```
POST https://yourdomain.com/api/v1/intake
```

**Headers:**
```
X-Intake-Token: your-intake-token
Content-Type: application/json
```

**Body:**
```json
{
  "subject": "Invoice from vendor",
  "body": "Invoice details...",
  "source": "automation_studio",
  "metadata": {
    "invoice_number": "INV-001",
    "amount": 500.00
  }
}
```

See full [Intake API documentation](/docs/intake_api) for complete reference.

---

## Related Documentation

- [Webhook/API Configuration](/settings/integrations?tab=integrations&view=webhooks)
- [Intake API Guide](/docs/intake_api)
- [Automation Studio Overview](/docs/automation_studio)
- [Security & Authentication](/docs/security_auth)

---

## Support

Need help setting up accounting automation?

- **Email**: support@kalevent.com
- **Documentation**: https://docs.kalevent.com
- **Community**: https://community.kalevent.com

---

*Last updated: February 9, 2026*
