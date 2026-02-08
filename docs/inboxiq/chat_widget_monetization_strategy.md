# Chat Widget Monetization Strategy

**Status**: Future Implementation (Currently Free for All Accounts)
**Created**: February 2026
**Last Updated**: February 2026

---

## Overview

The InboxIQ native chat widget is currently free for all accounts to enable beta testing and feedback collection. This document outlines the monetization strategy to be implemented once the feature is mature.

---

## 1. Plan-Based Access Control

### Implementation

Add account plan checking in `/api/v1/chat/submit` endpoint:

```python
# Check if account has chat feature enabled
from src.models import Account

account = Account.query.get(account_id_int)
if not account or not account.plan_allows_chat():
    return jsonify({
        "error": "upgrade_required",
        "message": "Chat widget requires Pro plan. Upgrade at inboxiq.com/pricing"
    }), 403
```

### Account Model Extension

Add method to `Account` model:

```python
def plan_allows_chat(self):
    """Check if account's plan includes chat widget."""
    if not self.plan:
        return False

    # Free/trial accounts: no chat
    if self.plan.lower() in ['free', 'trial']:
        return False

    # Paid plans: chat enabled
    return self.plan.lower() in ['starter', 'pro', 'business', 'enterprise']
```

---

## 2. Usage Limits

Track chat messages per account and enforce monthly limits:

### Pricing Tiers

| Plan | Monthly Messages | Overage Rate |
|------|-----------------|--------------|
| **Free** | 0 (disabled) | N/A |
| **Starter** | 100 | $0.10/message |
| **Pro** | 1,000 | $0.05/message |
| **Business** | 5,000 | $0.03/message |
| **Enterprise** | Unlimited | $0 |

### Implementation

```python
def check_chat_usage_limit(account_id: int) -> tuple[bool, dict]:
    """Check if account has exceeded chat message limit."""
    account = Account.query.get(account_id)
    if not account:
        return False, {"error": "account_not_found"}

    # Get current month's usage
    current_month = datetime.now().replace(day=1, hour=0, minute=0, second=0)
    usage = ChatUsage.query.filter_by(
        account_id=account_id,
        period_start=current_month
    ).first()

    message_count = usage.message_count if usage else 0
    limit = get_plan_message_limit(account.plan)

    if limit == -1:  # Unlimited
        return True, {"allowed": True}

    if message_count >= limit:
        return False, {
            "error": "limit_exceeded",
            "message": f"Monthly limit of {limit} messages reached. Upgrade your plan.",
            "current": message_count,
            "limit": limit
        }

    return True, {"allowed": True, "current": message_count, "limit": limit}
```

### Database Schema Addition

```python
class ChatUsage(db.Model):
    """Track monthly chat message usage per account."""
    __tablename__ = "chat_usage"

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    period_start = db.Column(db.DateTime, nullable=False)  # First day of month
    message_count = db.Column(db.Integer, default=0)
    overage_messages = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

---

## 3. Widget Branding

### Free/Starter Tiers
Show "Powered by InboxIQ" badge in chat widget footer:

```javascript
// Add to chat widget HTML for free accounts
const branding = account.plan === 'free' || account.plan === 'starter'
  ? '<div class="inboxiq-branding">Powered by <a href="https://inboxiq.com" target="_blank">InboxIQ</a></div>'
  : '';
```

### Pro+ Tiers
No branding - full white-label experience.

---

## 4. Feature Gating by Plan

### Feature Matrix

| Feature | Free | Starter | Pro | Business | Enterprise |
|---------|------|---------|-----|----------|------------|
| **Chat Widget** | ❌ | ✅ | ✅ | ✅ | ✅ |
| **Lead Capture** | ❌ | ✅ | ✅ | ✅ | ✅ |
| **Custom Welcome Message** | ❌ | ❌ | ✅ | ✅ | ✅ |
| **Custom Colors** | ❌ | ❌ | ✅ | ✅ | ✅ |
| **Remove Branding** | ❌ | ❌ | ✅ | ✅ | ✅ |
| **Multi-language** | ❌ | ❌ | ❌ | ✅ | ✅ |
| **Analytics Dashboard** | ❌ | Basic | Advanced | Advanced | Custom |
| **Priority Support** | ❌ | ❌ | ✅ | ✅ | ✅ |
| **SLA Guarantee** | ❌ | ❌ | ❌ | 24hr | 1hr |

### Implementation

```python
def get_chat_features(account_id: int) -> dict:
    """Return enabled chat features for account's plan."""
    account = Account.query.get(account_id)
    if not account:
        return {}

    features = {
        'free': {
            'enabled': False,
            'lead_capture': False,
            'custom_welcome': False,
            'custom_colors': False,
            'remove_branding': False,
            'multi_language': False,
            'analytics': None,
        },
        'starter': {
            'enabled': True,
            'lead_capture': True,
            'custom_welcome': False,
            'custom_colors': False,
            'remove_branding': False,
            'multi_language': False,
            'analytics': 'basic',
        },
        'pro': {
            'enabled': True,
            'lead_capture': True,
            'custom_welcome': True,
            'custom_colors': True,
            'remove_branding': True,
            'multi_language': False,
            'analytics': 'advanced',
        },
        'business': {
            'enabled': True,
            'lead_capture': True,
            'custom_welcome': True,
            'custom_colors': True,
            'remove_branding': True,
            'multi_language': True,
            'analytics': 'advanced',
        },
        'enterprise': {
            'enabled': True,
            'lead_capture': True,
            'custom_welcome': True,
            'custom_colors': True,
            'remove_branding': True,
            'multi_language': True,
            'analytics': 'custom',
        },
    }

    return features.get(account.plan.lower(), features['free'])
```

---

## 5. Implementation Checklist

### Phase 1: Backend Infrastructure
- [ ] Add `chat_enabled` flag to account plans in database
- [ ] Create `ChatUsage` model for tracking monthly usage
- [ ] Implement `plan_allows_chat()` method on Account model
- [ ] Add usage limit checking in `/api/v1/chat/submit`
- [ ] Create admin endpoint to view chat usage stats
- [ ] Add Celery task to reset monthly counters

### Phase 2: Frontend Gating
- [ ] Hide chat embed code for free accounts
- [ ] Show upgrade prompt in chat connection modal
- [ ] Display usage stats in dashboard
- [ ] Add "Powered by InboxIQ" branding for free/starter tiers
- [ ] Disable custom colors/welcome message for lower tiers

### Phase 3: Billing Integration
- [ ] Connect chat usage to Stripe billing
- [ ] Create webhook for plan upgrades/downgrades
- [ ] Implement overage billing for exceeded limits
- [ ] Send usage warning emails at 80% and 100% of limit
- [ ] Create billing page showing chat usage breakdown

### Phase 4: Analytics & Reporting
- [ ] Create chat analytics dashboard
- [ ] Track metrics: messages sent, response time, satisfaction
- [ ] Add export to CSV feature
- [ ] Create monthly usage reports
- [ ] Build admin panel for monitoring all accounts

### Phase 5: Advanced Features
- [ ] Multi-language support (Business+)
- [ ] Custom CSS themes (Pro+)
- [ ] Webhook notifications for new messages
- [ ] AI-powered auto-responses
- [ ] Integration with third-party CRMs

---

## 6. Pricing Strategy

### Recommended Pricing

```
Starter Plan: $29/month
- 100 chat messages/month
- Lead capture
- Basic analytics
- Standard support
- "Powered by InboxIQ" branding

Pro Plan: $99/month
- 1,000 chat messages/month
- Custom welcome message
- Custom colors
- Remove branding
- Advanced analytics
- Priority support

Business Plan: $299/month
- 5,000 chat messages/month
- Multi-language support
- Advanced customization
- API access
- 24hr SLA
- Dedicated account manager

Enterprise Plan: Custom
- Unlimited messages
- White-label
- Custom integrations
- 1hr SLA
- On-premise option
- Custom contracts
```

### Overage Pricing
- **Starter**: $0.10 per additional message
- **Pro**: $0.05 per additional message
- **Business**: $0.03 per additional message
- **Enterprise**: Unlimited included

---

## 7. Migration Strategy

### When Enabling Monetization

1. **Grandfather Existing Users**
   - All accounts using chat widget before launch date get 3 months free Pro access
   - Email notification 2 weeks before conversion
   - Offer 20% lifetime discount for early adopters

2. **Communication Timeline**
   - **T-30 days**: Announcement email about upcoming pricing
   - **T-14 days**: Reminder email with plan comparison
   - **T-7 days**: Final reminder with upgrade link
   - **T-0 days**: Enable enforcement, send confirmation
   - **T+7 days**: Follow-up email offering support

3. **Enforcement Strategy**
   - Start with soft limits (warnings only)
   - Move to hard limits after 1 month grace period
   - Provide downgrade path for users who can't pay

---

## 8. Success Metrics

### Key Performance Indicators (KPIs)

- **Conversion Rate**: % of free users upgrading to paid
- **Monthly Recurring Revenue (MRR)**: Total chat widget revenue
- **Churn Rate**: % of paid users downgrading/canceling
- **Usage Per Account**: Average messages per account per month
- **Customer Lifetime Value (LTV)**: Average revenue per user
- **Feature Adoption**: % of paid users using custom features

### Target Metrics (6 months post-launch)

- Conversion rate: 15-20% of active users
- MRR: $50,000+
- Churn rate: <5%
- Overage revenue: 10% of total revenue
- Enterprise customers: 5-10 accounts

---

## 9. Competitive Analysis

### Market Positioning

| Competitor | Price | Messages | Our Advantage |
|------------|-------|----------|---------------|
| **Intercom** | $74/mo | 1,000 | Unified triage + chat |
| **Drift** | $2,500/mo | Unlimited | More affordable |
| **Zendesk Chat** | $55/mo | Unlimited | AI triage included |
| **Crisp** | $25/mo | Unlimited | Lead capture + funnel |
| **LiveChat** | $20/mo | Unlimited | Decision automation |

**InboxIQ Differentiator**: Only platform combining chat, email, voice, and social into ONE AI-powered triage system with unified lead funnel.

---

## 10. Future Enhancements

### Roadmap (Post-Monetization)

**Q2 2026**
- [ ] AI-powered suggested responses
- [ ] Sentiment analysis in real-time
- [ ] Auto-translation for multi-language

**Q3 2026**
- [ ] Video chat integration
- [ ] Screen sharing support
- [ ] Co-browsing features

**Q4 2026**
- [ ] Chatbot builder (no-code)
- [ ] Intent-based routing
- [ ] Proactive chat triggers

**2027+**
- [ ] Voice-to-text chat
- [ ] AR/VR support
- [ ] Blockchain verification for enterprise

---

## Notes

- This strategy assumes successful beta testing with positive user feedback
- Pricing may be adjusted based on market response and costs
- Feature gating should be implemented gradually to avoid user backlash
- Always provide clear upgrade paths and value propositions
- Monitor competitor pricing and adjust accordingly

---

**Next Review Date**: Q2 2026
**Owner**: Product & Growth Teams
**Stakeholders**: Engineering, Sales, Customer Success
