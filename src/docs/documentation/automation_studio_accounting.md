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

## Example 1: Invoice Extraction → Sage

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

## Example 2: Receipt Extraction → QuickBooks

**Use Case**: Capture payment receipts from Stripe, PayPal, Square and sync to QuickBooks.

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

## Configuring Webhook Providers

### Step 1: Add Provider

1. Navigate to **Settings → Integrations → Webhooks**
2. Scroll to **Configured Providers** section
3. Click **"+ Add Provider"** button

### Step 2: Select Provider Type

Choose from:
- **Sage Accounting** - Sage API integration
- **Intuit QuickBooks** - QuickBooks Online API
- **Slack** - Send notifications to Slack channels
- **Custom Webhook** - Any REST API endpoint

### Step 3: Enter Credentials

**For Sage:**
- Configuration Name (e.g., "Production Sage")
- API Key (encrypted)
- Company ID
- Environment (production/sandbox)
- API Endpoint URL

**For QuickBooks:**
- Configuration Name (e.g., "QuickBooks Production")
- Client ID
- Client Secret (encrypted)
- Company ID (Realm ID)
- Environment (production/sandbox)

**For Slack:**
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
