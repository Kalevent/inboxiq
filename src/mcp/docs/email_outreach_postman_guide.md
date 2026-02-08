# Email Outreach API - Postman Collection Guide

Complete guide for managing automated email outreach campaigns using Postman.

## Overview

The Email Outreach API allows you to create and manage automated email campaigns for lead generation. This guide covers how to use the Postman collection to interact with the API.

---

## 📱 Step 1: Import the Collection in VS Code

1. Open **VS Code**
2. Open the **Postman extension** (Thunder Client or Postman for VS Code)
3. Click **"Import"** or **"Collections"** → **"Import Collection"**
4. Select `Email_Outreach_API.postman_collection.json` from the project root
5. You'll see **"Email Outreach API"** collection with 6 requests

---

## 🔑 Step 2: Get Your JWT Token (One-Time Setup)

You need your authentication token. Choose one of these methods:

### Option A: From Browser DevTools (Recommended)

1. Go to `https://kalevent.com/admin`
2. Open DevTools (**F12** or **Cmd+Option+I**)
3. Go to **Application** tab → **Cookies**
4. Copy the value of `access_token_cookie`

### Option B: From Postman Login Endpoint

```http
POST https://api.kalevent.com/api/v1/auth/login
Content-Type: application/json

{
  "email": "your@email.com",
  "password": "your_password"
}
```

Copy the token from the response.

---

## ⚙️ Step 3: Set the JWT Token in Collection

1. In Postman, click on **"Email Outreach API"** collection name
2. Go to **"Variables"** tab
3. Find `jwt_token` variable
4. Paste your token in the **"Current Value"** field
5. Click **Save**

**✅ Now all requests will automatically include your token!**

---

## 🚀 Step 4: Create Your First Campaign

Run the requests in this order:

### Request 1: Create Campaign

1. Click **"1. Create Campaign"**
2. You'll see the pre-filled template:

```json
{
  "name": "Automation Studio Beta Outreach",
  "subject_template": "Quick question about {{CompanyName}}",
  "body_template": "Hi {{FirstName}},\n\nSaw {{CompanyName}} is {{signal}}. Quick question: drowning in support tickets yet?\n\nI built Automation Studio to handle 80% of routine tickets automatically using AI. Early customers seeing 15-hour/week savings.\n\nOffering free beta access to 10 companies this month. 5 spots left.\n\nWant a 10-min demo?\n\nBest,\nKofi",
  "from_email": "support@kalevent.com",
  "from_name": "Kofi - Automation Studio",
  "max_recipients": 10,
  "follow_up_delay_days": [3, 7],
  "target_source": "buying_signal_discovery"
}
```

3. **Edit `from_email`** to your actual email address (must be verified in AWS SES)
4. Customize the message template if desired
5. Click **"Send"**

**Response:**
```json
{
  "success": true,
  "campaign_id": "abc123-456-789",
  "message": "Campaign created"
}
```

**⚡ Important:** The `campaign_id` is **automatically saved** to collection variables! No need to copy/paste.

---

### Request 2: List All Campaigns (Optional)

Verify your campaign was created:

1. Click **"2. List All Campaigns"**
2. Click **"Send"**
3. You'll see your campaign with current stats

---

### Request 3: Activate Campaign (Start Sending!)

This starts the automated email sending:

1. Click **"3. Activate Campaign (Start Sending)"**
2. Notice the URL uses `{{campaign_id}}` - **automatically filled** from Step 1
3. Click **"Send"**

**Response:**
```json
{
  "success": true,
  "message": "Campaign activated. Emails will be sent shortly.",
  "task_id": "xyz-123"
}
```

**🎉 Emails are now being sent automatically!**

---

## 📊 Step 5: Monitor Your Campaign

### Check Campaign Stats

Wait 2-3 minutes for the first batch to send, then:

1. Click **"5. Get Campaign Stats"**
2. Click **"Send"**

**Example Response:**
```json
{
  "campaign": {
    "name": "Automation Studio Beta Outreach",
    "total_sent": 8,
    "total_opened": 3,
    "total_clicked": 1,
    "total_replied": 0,
    "open_rate": 37.5,
    "click_rate": 12.5,
    "reply_rate": 0.0,
    "status": "active"
  }
}
```

### View Individual Email Details

1. Click **"6. List Campaign Outreaches"**
2. Click **"Send"**

**Example Response:**
```json
{
  "outreaches": [
    {
      "id": "out-123",
      "recipient_email": "john@acme.com",
      "recipient_name": "John",
      "subject": "Quick question about Acme Corp",
      "status": "opened",
      "sequence_step": 0,
      "sent_at": "2026-02-08T10:00:00",
      "first_opened_at": "2026-02-08T10:30:00",
      "open_count": 2,
      "click_count": 0
    }
  ]
}
```

---

## ⏸️ Step 6: Pause or Manage Campaign

### To Pause a Campaign

1. Click **"4. Pause Campaign"**
2. Click **"Send"**
3. No more emails will be sent (already scheduled follow-ups will still send)

### To Create Another Campaign

Simply run **"1. Create Campaign"** again with a different template or targeting!

---

## 🎯 Quick Tips

### ✅ Smart Collection Features

- **campaign_id** is auto-saved when you create a campaign
- **JWT token** is stored once and used for all requests
- **No copy/pasting** needed between requests!

### ✅ Typical Workflow

```
1. Create Campaign (once)
   ↓
2. Activate Campaign (starts automation)
   ↓
3. Check Stats (monitor progress)
   ↓
4. Pause when goals reached (e.g., 10 signups)
```

### ✅ Keep Leads Flowing

- Go to `https://kalevent.com/admin`
- Click **"🚀 Discover Leads Now"** daily with different niches
- Each enriched lead gets emailed automatically by your active campaign
- System handles follow-ups on Day 3 and Day 7 if no response

---

## ⚠️ Before You Start

### Verify Your Sender Email in AWS SES

**Important:** Your `from_email` must be verified in AWS SES or emails will fail.

Check verified emails:
```bash
aws ses list-verified-email-addresses
```

Verify a new email:
```bash
aws ses verify-email-identity --email-address your@domain.com
```

Then check your email inbox for the verification link from AWS.

---

## 🔧 Template Variables

Your email templates can use these variables (automatically filled from lead data):

| Variable | Description | Example |
|----------|-------------|---------|
| `{{FirstName}}` | Lead's first name | "John" |
| `{{CompanyName}}` | Company name | "Acme Corp" |
| `{{signal}}` | Why they were discovered | "hiring", "funding", "expansion" |
| `{{Email}}` | Lead's email | "john@acme.com" |
| `{{URL}}` | Company signal URL | LinkedIn job posting, etc. |

**Example:**
```
Subject: {{FirstName}}, question about {{CompanyName}}

Hi {{FirstName}},

Saw {{CompanyName}} is {{signal}}. Quick question...
```

---

## 📈 Understanding Campaign Metrics

| Metric | Description |
|--------|-------------|
| **total_sent** | Total emails sent |
| **total_opened** | How many recipients opened the email |
| **total_clicked** | How many clicked a link in the email |
| **total_replied** | How many replied (stops follow-ups) |
| **open_rate** | Percentage who opened (total_opened / total_sent × 100) |
| **click_rate** | Percentage who clicked (total_clicked / total_sent × 100) |
| **reply_rate** | Percentage who replied (total_replied / total_sent × 100) |

**Good benchmarks for B2B cold outreach:**
- Open rate: 30-50%
- Click rate: 5-15%
- Reply rate: 5-10%

---

## 🔄 Automated Follow-Up Sequence

When you activate a campaign, here's what happens automatically:

### Day 0 (Today)
- Lead discovered via "Discover Leads Now"
- Email enriched by Hunter.io
- **Initial email sent:**
  ```
  Hi John,
  Saw Acme Corp is hiring. Quick question: drowning in support tickets yet?
  ...
  ```

### Day 3 (If no response)
- **Auto follow-up sent:**
  ```
  Hi John, following up on my message about Automation Studio...
  ```

### Day 7 (If still no response)
- **Final follow-up sent:**
  ```
  Last chance for beta access. We're down to 3 spots...
  ```

### If They Reply
- ✅ No more follow-ups sent
- ✅ Campaign counter: `total_replied++`
- ✅ Campaign stops after `max_recipients` replies

---

## 🚨 Troubleshooting

### Getting 401 Unauthorized?
- Your JWT token expired
- Get a new token using Step 2 above
- Update the `jwt_token` variable in collection

### Getting 404 Not Found?
- Check that the backend is deployed with outreach routes
- Verify URL is: `https://api.kalevent.com/api/v1/outreach/campaigns`

### Emails Not Sending?
- Check `from_email` is verified in AWS SES
- Check campaign status is "active" not "draft" or "paused"
- Look at campaign stats - any errors?

### Follow-Ups Not Working?
- Check `follow_up_enabled` is `true` in campaign
- Check `follow_up_delay_days` is set (e.g., `[3, 7]`)
- Verify leads haven't already replied (stops follow-ups)

---

## 📚 Related Documentation

- [Lead Discovery Guide](lead_discovery_guide.md)
- [Users Guide](users_guide.md)
- [Security & Auth](security_auth.md)

---

## 🤝 Need Help?

If you encounter issues:

1. Check the **Troubleshooting** section above
2. Review campaign stats for error details
3. Contact the development team

---

**Ready to start?** Import the Postman collection and create your first campaign! 🚀
