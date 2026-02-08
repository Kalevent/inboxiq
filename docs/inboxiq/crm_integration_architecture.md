# CRM Integration Architecture

## Overview

CRM integrations (Salesforce, HubSpot, Pipedrive) serve as knowledge sources for AI draft reply generation. This document outlines the architecture for syncing CRM data and using it to enrich customer context.

## Current Implementation Status

### ✅ Completed
- **UI**: CRM connection modal in Settings → Integrations
- **Backend**: Credential storage in `InboxConnection` table with provider="crm"
- **Security**: Encrypted credentials using `encrypt_value()` from `src/security/encryption.py`
- **Platforms**: Support for Salesforce, HubSpot, Pipedrive (with platform-specific fields)
- **Sync Settings**: Toggles for syncing contacts, accounts, and deals

### ⚠️ Pending Implementation
- **Data Sync**: Celery tasks to pull CRM data on schedule
- **Local Storage**: Models to store CRM contacts/accounts/deals
- **Embeddings**: Vector search for CRM data
- **Draft Reply Integration**: Inject CRM context into reply generation

---

## How CRM Data Enhances Draft Replies

When a support ticket arrives, the AI draft reply system:

1. **Identifies the customer** via email address
2. **Queries CRM for context**:
   - Contact profile (name, role, company)
   - Account health (deal stage, ARR, churn risk)
   - Recent interactions (calls, emails, notes)
   - Open opportunities (deal names, values, close dates)
3. **Enriches the draft reply**:
   - Personalized greeting with correct name/title
   - References specific deals or features customer is interested in
   - Adjusts tone based on account priority (enterprise vs. SMB)
   - Includes upsell opportunities if deal stage is appropriate

### Example Context Injection

**Without CRM**:
> "Hi, thanks for reaching out. I see you're having trouble with the API. Here's how to fix it..."

**With CRM Context**:
> "Hi Sarah, thanks for reaching out! I see you're the VP of Engineering at Acme Corp. Regarding your Enterprise plan API issue – I know you're in the middle of evaluating our Analytics add-on (great choice!). Let me get this resolved quickly so it doesn't impact your POC..."

---

## Architecture

### Data Models

#### CRM Contact
```python
class CRMContact(db.Model):
    __tablename__ = "crm_contacts"

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()))
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)
    integration_id = db.Column(db.String(64), db.ForeignKey("inbox_connections.id"), nullable=False)

    # External reference
    external_id = db.Column(db.String(255), nullable=False, index=True)
    platform = db.Column(db.String(50), nullable=False)  # salesforce, hubspot, pipedrive

    # Contact details
    email = db.Column(db.String(255), nullable=False, index=True)
    name = db.Column(db.String(255), nullable=True)
    title = db.Column(db.String(255), nullable=True)
    phone = db.Column(db.String(50), nullable=True)

    # Company/Account reference
    company_name = db.Column(db.String(255), nullable=True)
    company_external_id = db.Column(db.String(255), nullable=True)

    # Context for replies
    lifecycle_stage = db.Column(db.String(50), nullable=True)  # lead, mql, sql, customer, etc.
    customer_tier = db.Column(db.String(50), nullable=True)  # enterprise, mid-market, smb
    last_activity_at = db.Column(db.DateTime(timezone=True), nullable=True)

    # Search and RAG
    notes = db.Column(db.Text, nullable=True)  # Aggregated notes from CRM

    # Sync metadata
    synced_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

#### CRM Account
```python
class CRMAccount(db.Model):
    __tablename__ = "crm_accounts"

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()))
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)
    integration_id = db.Column(db.String(64), db.ForeignKey("inbox_connections.id"), nullable=False)

    # External reference
    external_id = db.Column(db.String(255), nullable=False, index=True)
    platform = db.Column(db.String(50), nullable=False)

    # Account details
    name = db.Column(db.String(255), nullable=False)
    domain = db.Column(db.String(255), nullable=True)
    industry = db.Column(db.String(100), nullable=True)
    employee_count = db.Column(db.Integer, nullable=True)
    arr = db.Column(db.Numeric(12, 2), nullable=True)

    # Health/status
    health_score = db.Column(db.String(50), nullable=True)  # green, yellow, red
    churn_risk = db.Column(db.String(50), nullable=True)  # low, medium, high
    plan_type = db.Column(db.String(100), nullable=True)  # free, starter, pro, enterprise

    # Context
    description = db.Column(db.Text, nullable=True)

    # Sync metadata
    synced_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

#### CRM Deal
```python
class CRMDeal(db.Model):
    __tablename__ = "crm_deals"

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()))
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)
    integration_id = db.Column(db.String(64), db.ForeignKey("inbox_connections.id"), nullable=False)

    # External reference
    external_id = db.Column(db.String(255), nullable=False, index=True)
    platform = db.Column(db.String(50), nullable=False)

    # Deal details
    name = db.Column(db.String(500), nullable=False)
    stage = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=True)
    close_date = db.Column(db.Date, nullable=True)
    probability = db.Column(db.Integer, nullable=True)  # 0-100

    # Relationships
    contact_external_id = db.Column(db.String(255), nullable=True)
    account_external_id = db.Column(db.String(255), nullable=True)

    # Status
    is_closed_won = db.Column(db.Boolean, default=False)
    is_closed_lost = db.Column(db.Boolean, default=False)

    # Context
    description = db.Column(db.Text, nullable=True)

    # Sync metadata
    synced_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

#### CRM Contact Embedding
```python
class CRMContactEmbedding(db.Model):
    __tablename__ = "crm_contact_embeddings"

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()))
    contact_id = db.Column(db.String(64), db.ForeignKey("crm_contacts.id"), nullable=False, index=True)

    # Embedding data (same pattern as KBArticleEmbedding)
    embedding_model = db.Column(db.String(100), default="text-embedding-3-small")
    embedding_vector = db.Column(Vector(1536)) if Vector else db.Column(db.JSON, nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
```

---

## CRM Sync Architecture

### Sync Tasks (Celery)

#### Task: `crm_sync_full`
- **Frequency**: Every 6 hours (configurable)
- **Scope**: Full sync of all contacts, accounts, and deals
- **Queue**: `crm_sync`

```python
@shared_task(name="crm.sync_full")
def crm_sync_full(account_id: int):
    """Full CRM sync for a single account."""
    connection = InboxConnection.query.filter_by(account_id=account_id, provider="crm").first()
    if not connection or connection.status != "connected":
        return {"error": "no_connection"}

    platform = connection.metadata_json.get("platform")
    sync_contacts = connection.metadata_json.get("sync_contacts", False)
    sync_accounts = connection.metadata_json.get("sync_accounts", False)
    sync_deals = connection.metadata_json.get("sync_deals", False)

    results = {}

    if sync_contacts and platform == "hubspot":
        results["contacts"] = sync_hubspot_contacts(connection)
    elif sync_contacts and platform == "salesforce":
        results["contacts"] = sync_salesforce_contacts(connection)
    elif sync_contacts and platform == "pipedrive":
        results["contacts"] = sync_pipedrive_contacts(connection)

    if sync_accounts:
        results["accounts"] = sync_accounts_for_platform(connection, platform)

    if sync_deals:
        results["deals"] = sync_deals_for_platform(connection, platform)

    return results
```

#### Task: `crm_sync_incremental`
- **Frequency**: Every 30 minutes
- **Scope**: Only changed records (delta sync)
- **Queue**: `crm_sync`

---

## Platform-Specific API Clients

### HubSpot Client
```python
class HubSpotClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.hubapi.com"

    def get_contacts(self, after: str = None) -> dict:
        """Get contacts with pagination."""
        url = f"{self.base_url}/crm/v3/objects/contacts"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        params = {"limit": 100, "after": after} if after else {"limit": 100}

        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()

    def get_companies(self, after: str = None) -> dict:
        """Get companies (accounts)."""
        url = f"{self.base_url}/crm/v3/objects/companies"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        params = {"limit": 100, "after": after} if after else {"limit": 100}

        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()

    def get_deals(self, after: str = None) -> dict:
        """Get deals (opportunities)."""
        url = f"{self.base_url}/crm/v3/objects/deals"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        params = {"limit": 100, "after": after} if after else {"limit": 100}

        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
```

### Salesforce Client
```python
class SalesforceClient:
    def __init__(self, instance_url: str, access_token: str):
        self.instance_url = instance_url
        self.access_token = access_token

    def query(self, soql: str) -> dict:
        """Execute SOQL query."""
        url = f"{self.instance_url}/services/data/v58.0/query"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        params = {"q": soql}

        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()

    def get_contacts(self) -> list:
        """Get all contacts."""
        soql = """
            SELECT Id, Email, FirstName, LastName, Title, Phone, AccountId, Account.Name
            FROM Contact
            WHERE Email != null
            ORDER BY LastModifiedDate DESC
        """
        result = self.query(soql)
        return result.get("records", [])
```

---

## Draft Reply Integration

### Enrichment Flow

1. **Ticket arrives** → `inboxiq.process_incoming_email` task
2. **Extract customer email** from `from_email`
3. **Query CRM contact**:
   ```python
   contact = CRMContact.query.filter_by(
       account_id=account_id,
       email=from_email
   ).first()
   ```
4. **Load related data**:
   ```python
   if contact:
       account = CRMAccount.query.filter_by(
           external_id=contact.company_external_id,
           platform=contact.platform
       ).first()

       deals = CRMDeal.query.filter_by(
           contact_external_id=contact.external_id,
           is_closed_won=False,
           is_closed_lost=False
       ).all()
   ```
5. **Build context dict**:
   ```python
   crm_context = {
       "contact_name": contact.name,
       "contact_title": contact.title,
       "company_name": account.name if account else None,
       "account_tier": account.plan_type if account else None,
       "health_score": account.health_score if account else None,
       "open_deals": [
           {"name": d.name, "stage": d.stage, "amount": float(d.amount)}
           for d in deals
       ]
   }
   ```
6. **Pass to DSPy reply generator**:
   ```python
   draft = generate_draft_reply(
       ticket=ticket,
       kb_articles=relevant_kb_articles,
       crm_context=crm_context  # <-- NEW
   )
   ```

### DSPy Signature Update

```python
class DraftReplySignature(dspy.Signature):
    """Generate a draft reply using ticket, KB, and CRM context."""

    ticket_subject = dspy.InputField(desc="Ticket subject")
    ticket_body = dspy.InputField(desc="Customer's message")
    kb_context = dspy.InputField(desc="Relevant KB articles")
    crm_context = dspy.InputField(desc="Customer profile, account, and deals from CRM")

    reply_text = dspy.OutputField(desc="Draft reply text")
    confidence = dspy.OutputField(desc="Confidence score 0-1")
```

---

## Security & Privacy

### Encrypted Storage
- All CRM credentials stored encrypted via `encrypt_value()`
- Access tokens refreshed automatically (OAuth flows)
- Decryption only happens in memory during sync tasks

### Data Minimization
- Only sync fields needed for draft replies
- Exclude sensitive fields (SSN, credit cards, etc.)
- Configurable sync depth (e.g., only contacts, not deals)

### GDPR Compliance
- Support for "right to be forgotten" (delete CRM data on request)
- Audit trail of all CRM data access
- Data retention policy (default: 90 days)

---

## Implementation Checklist

### Phase 1: Data Sync (Priority: High)
- [ ] Create CRM data models (CRMContact, CRMAccount, CRMDeal)
- [ ] Implement HubSpot sync client
- [ ] Implement Salesforce sync client
- [ ] Implement Pipedrive sync client
- [ ] Create `crm.sync_full` Celery task
- [ ] Create `crm.sync_incremental` Celery task
- [ ] Add Celery Beat schedules for auto-sync

### Phase 2: Embeddings & Search (Priority: Medium)
- [ ] Create CRMContactEmbedding model
- [ ] Generate embeddings for contact notes/descriptions
- [ ] Implement semantic search for CRM data
- [ ] Add CRM context to ticket detail view

### Phase 3: Draft Reply Integration (Priority: High)
- [ ] Update DSPy reply signature to include `crm_context`
- [ ] Query CRM data in `generate_draft_reply()`
- [ ] Inject CRM context into prompt
- [ ] Train/optimize DSPy module with CRM examples

### Phase 4: Advanced Features (Priority: Low)
- [ ] CRM data enrichment (Clearbit, ZoomInfo)
- [ ] Bidirectional sync (update CRM from tickets)
- [ ] CRM activity logging (log ticket creation in CRM)
- [ ] Custom field mapping (per-account configuration)

---

## Testing Strategy

### Unit Tests
- [ ] Test credential encryption/decryption
- [ ] Test API client error handling
- [ ] Test sync task retries

### Integration Tests
- [ ] Test full sync with mock CRM data
- [ ] Test incremental sync delta detection
- [ ] Test embedding generation

### E2E Tests
- [ ] Connect real HubSpot sandbox account
- [ ] Sync contacts → Verify in database
- [ ] Generate draft reply → Verify CRM context used

---

## Performance Considerations

### Sync Optimization
- **Pagination**: Process 100 records at a time
- **Rate Limiting**: Respect CRM API limits (e.g., HubSpot: 100 req/10sec)
- **Backoff**: Exponential backoff on 429 errors
- **Parallelization**: Sync contacts/accounts/deals in parallel

### Query Optimization
- **Indexes**: Add indexes on `email`, `external_id`, `company_external_id`
- **Caching**: Cache CRM lookups for 5 minutes
- **Preloading**: Eager load related data to avoid N+1 queries

---

## Monitoring & Observability

### Metrics to Track
- `crm_sync_duration_seconds` (histogram)
- `crm_sync_records_synced` (counter)
- `crm_sync_errors` (counter)
- `crm_context_injected` (counter)
- `draft_reply_with_crm_context` (counter)

### Alerts
- Alert if sync fails 3 times in a row
- Alert if sync duration > 10 minutes
- Alert if CRM API returns 401 (auth expired)

---

## Future Enhancements

1. **AI-Powered Account Health Detection**: Analyze ticket sentiment/frequency to predict churn risk
2. **Upsell Opportunity Detection**: Identify feature requests that map to paid add-ons
3. **CRM-Driven Routing**: Route tickets to account owner automatically
4. **Sales-Support Handoff**: Notify sales when support ticket indicates buying intent

---

## References

- [HubSpot CRM API Docs](https://developers.hubspot.com/docs/api/crm/contacts)
- [Salesforce REST API Docs](https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/)
- [Pipedrive API Docs](https://developers.pipedrive.com/docs/api/v1)
- [InboxIQ Upload Isolation](./upload_isolation.md)
- [InboxIQ Embeddings Architecture](./embeddings_architecture.md)
