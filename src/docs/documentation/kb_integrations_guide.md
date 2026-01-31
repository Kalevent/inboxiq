# Knowledge Base Integrations

Connect your existing knowledge base to InboxIQ to supercharge AI-powered draft replies with your organization's documentation and help articles.

## Why Connect Your Knowledge Base?

When your KB is connected, InboxIQ can:
- **Auto-reference** relevant articles in draft replies
- **Cite sources** so agents can verify information
- **Include links** for customers to self-serve
- **Stay current** with your latest documentation
- **Maintain accuracy** using your approved content

## Supported Platforms

### Ready for Integration

| Platform | Status | Sync Method | OAuth |
|----------|--------|-------------|-------|
| **Zendesk Guide** | 🔧 Coming Soon | REST API | ✅ |
| **Notion** | 🔧 Coming Soon | REST API | ✅ |
| **Confluence** | 🔧 Coming Soon | REST API | ✅ |
| **Intercom Articles** | 🔧 Coming Soon | REST API | ✅ |
| **HelpScout Docs** | 🔧 Coming Soon | REST API | ✅ |
| **GitBook** | 🔧 Coming Soon | REST API | ✅ |
| **Custom REST API** | 🔧 Coming Soon | Configurable | 🔑 |
| **File Upload** | 🔧 Coming Soon | Manual | ➖ |

### Architecture

InboxIQ uses vector embeddings for intelligent KB search:

```
Your KB → Sync Worker → Embeddings → Vector Database
                              ↓
        Customer Email → Query → Similarity Search → Top 3 Articles
                              ↓
                    Draft Reply (with citations)
```

## How It Works

### 1. Connect Your KB
Navigate to **Settings → Integrations → Knowledge Base**:
- Click "Connect" next to your platform
- Authorize InboxIQ to read your articles
- Configure sync settings (frequency, filters)

### 2. Initial Sync
InboxIQ imports your content:
- Fetches all published articles
- Generates semantic embeddings
- Builds searchable index
- Time: 10-30 minutes depending on article count

### 3. Ongoing Sync
Keeps your KB up to date:
- **Hourly**: Check for changes
- **Daily**: Full sync (default)
- **Weekly**: For large KBs
- **Manual**: Trigger sync anytime

### 4. Smart Retrieval
When generating drafts:
1. Analyze customer question
2. Search KB with semantic similarity
3. Retrieve top 3 most relevant articles
4. Include in AI context
5. Cite sources in draft reply

## Setting Up Each Platform

### Zendesk Guide

**Prerequisites:**
- Zendesk account with Guide enabled
- Admin or agent permissions
- Published help center articles

**Setup Steps:**
1. Go to **Settings → Integrations → Zendesk**
2. Click "Connect Zendesk Guide"
3. Enter your Zendesk subdomain (e.g., `company.zendesk.com`)
4. Click "Authorize"
5. Grant InboxIQ read access to articles
6. Configure sync:
   - **Categories**: Select which categories to sync
   - **Sections**: Filter by section if needed
   - **Languages**: Choose languages to include
7. Click "Start Initial Sync"

**What's Synced:**
- Article titles and content
- Article URLs
- Categories and sections
- Last updated timestamps
- Published articles only (drafts excluded)

### Notion

**Prerequisites:**
- Notion workspace
- Integration permissions
- Database or page structure

**Setup Steps:**
1. Go to **Settings → Integrations → Notion**
2. Click "Connect Notion"
3. Select workspace
4. Choose databases or pages to sync
5. Configure access:
   - **Read permissions**: Required
   - **Specific pages**: Select documentation pages
6. Start sync

**What's Synced:**
- Page titles and content (markdown)
- Database entries
- Nested pages (configurable depth)
- Last edited timestamps

### Confluence

**Prerequisites:**
- Atlassian account
- Confluence space access
- Published pages

**Setup Steps:**
1. Go to **Settings → Integrations → Confluence**
2. Click "Connect Confluence"
3. Enter site URL (e.g., `company.atlassian.net`)
4. Authorize with Atlassian
5. Select spaces to sync
6. Configure filters:
   - **Spaces**: Choose documentation spaces
   - **Labels**: Filter by label (optional)
   - **Include attachments**: Yes/No
7. Start sync

**What's Synced:**
- Page titles and content
- Page tree structure
- Labels and metadata
- Published pages only

### Custom REST API

**For custom or self-hosted knowledge bases:**

**API Requirements:**
```json
GET /api/articles
Response:
{
  "articles": [
    {
      "id": "unique-id",
      "title": "Article Title",
      "content": "Full article content...",
      "url": "https://kb.example.com/articles/123",
      "updated_at": "2026-01-31T10:00:00Z"
    }
  ]
}
```

**Setup:**
1. Go to **Settings → Integrations → Custom API**
2. Enter API endpoint URL
3. Configure authentication:
   - **API Key**: Header-based
   - **OAuth**: Client credentials
   - **Basic Auth**: Username/password
4. Map JSON fields:
   - ID field → `id`
   - Title field → `title`
   - Content field → `content`
   - URL field → `url`
5. Test connection
6. Start sync

### File Upload

**For offline or small knowledge bases:**

**Supported Formats:**
- Markdown (`.md`)
- HTML (`.html`)
- Plain text (`.txt`)
- PDF (`.pdf`) - text extraction

**Setup:**
1. Go to **Settings → Integrations → File Upload**
2. Click "Upload KB Articles"
3. Drag and drop files or browse
4. InboxIQ will:
   - Extract text content
   - Generate embeddings
   - Create searchable articles
5. Articles appear in KB list

**Limitations:**
- Manual updates required
- No automatic sync
- Max 100 files per upload
- Max 10 MB per file

## Managing Your KB Integration

### View Sync Status

**Settings → Integrations → [Your Platform]**

See:
- ✅ **Connected**: Active and syncing
- 🔄 **Syncing**: Update in progress
- ⚠️ **Error**: Connection issue
- 🔇 **Paused**: Manually paused

### Monitor Article Count

Dashboard shows:
- **Total Articles**: Number of KB articles synced
- **Last Sync**: Time of most recent sync
- **Sync Frequency**: Current schedule
- **Storage Used**: Embedding storage

### Force Sync

To manually trigger a sync:
1. Go to **Settings → Integrations → [Platform]**
2. Click "Sync Now"
3. Wait for sync to complete (progress bar shown)

### Update Settings

Change sync configuration:
- **Frequency**: Hourly, daily, weekly
- **Filters**: Categories, labels, spaces
- **Languages**: Which languages to include
- **Exclusions**: Articles to skip

### Disconnect

To remove integration:
1. Go to **Settings → Integrations → [Platform]**
2. Click "Disconnect"
3. Confirm disconnection
4. Articles remain cached for 30 days
5. Embeddings deleted after 30 days

## Optimizing KB for AI

### Best Practices

**Article Structure:**
- ✅ Clear, descriptive titles
- ✅ Well-organized sections with headings
- ✅ Concise paragraphs (3-5 sentences)
- ✅ Step-by-step instructions
- ✅ Examples and screenshots

**Content Quality:**
- ✅ Keep articles up to date
- ✅ Remove outdated information
- ✅ Use consistent terminology
- ✅ Include common variations of questions
- ✅ Link related articles

**Metadata:**
- ✅ Tag articles with topics
- ✅ Categorize by product/feature
- ✅ Mark internal vs customer-facing
- ✅ Set visibility (public/internal)

### What AI Looks For

The AI prioritizes articles with:
- **High relevance**: Semantic match to query
- **Recency**: Recently updated articles
- **Completeness**: Comprehensive answers
- **Clarity**: Easy-to-understand language
- **Examples**: Practical demonstrations

### Testing Article Retrieval

**Test your KB integration:**
1. Go to **Settings → Integrations → Test KB**
2. Enter a sample customer question
3. View top 3 retrieved articles
4. Adjust filters if results aren't relevant

Example:
```
Query: "How do I reset my password?"

Results:
1. ⭐⭐⭐⭐⭐ "Password Reset Guide" (95% match)
2. ⭐⭐⭐⭐ "Account Security FAQ" (78% match)
3. ⭐⭐⭐ "Troubleshooting Login Issues" (65% match)
```

## Advanced Configuration

### Embedding Model

Choose embedding model (affects accuracy):
- **text-embedding-3-small**: Fast, good quality (default)
- **text-embedding-3-large**: Slower, higher quality
- **Custom**: Bring your own model

### Similarity Threshold

Set minimum similarity score:
- **High (0.8-1.0)**: Only very relevant articles
- **Medium (0.6-0.8)**: Moderately relevant (default)
- **Low (0.4-0.6)**: Cast wider net

### Article Limit

Number of articles to include in context:
- **1 article**: Highly focused
- **3 articles**: Balanced (default)
- **5 articles**: Comprehensive

### Language Detection

Auto-detect customer language and return articles in matching language.

### Exclude Patterns

Skip articles containing:
- Internal documentation markers
- Deprecated tags
- Draft status
- Specific categories

## Monitoring & Analytics

### KB Usage Metrics

**Settings → Analytics → Knowledge Base**

Track:
- **Articles Retrieved**: How often each article is used
- **Hit Rate**: % of queries that find relevant articles
- **Avg Relevance Score**: Quality of matches
- **Top Articles**: Most frequently cited
- **Low Performers**: Articles never used

### Impact on Draft Quality

Compare draft quality with/without KB:
- **With KB**: Higher acceptance rate, fewer edits
- **Without KB**: More generic responses

### Article Performance

See which articles help the most:
```
Article: "Refund Policy Guide"
- Retrieved: 145 times
- Cited in drafts: 98 times
- Draft acceptance: 92%
- Time saved: 4.2 minutes avg
```

## Troubleshooting

### Sync Failing

**Common causes:**
- ❌ Invalid credentials → Re-authorize
- ❌ Permission changes → Check access
- ❌ API rate limits → Reduce frequency
- ❌ Network issues → Retry later

### Articles Not Appearing

**Check:**
- ✅ Article is published (not draft)
- ✅ Article in synced category/space
- ✅ Language matches configured languages
- ✅ Article not in exclusion list

### Low Relevance Scores

**Improve by:**
- Optimize article titles for common questions
- Add more context to article content
- Use customer language (not internal jargon)
- Include question variations in articles

### High Storage Usage

**Reduce by:**
- Filter to essential categories
- Exclude archived content
- Remove duplicate articles
- Compress embedded media

## Privacy & Security

### Data Access
- **Read-only**: InboxIQ only reads articles
- **No modifications**: We never write to your KB
- **Secure storage**: Encrypted at rest
- **Access logs**: Audit trail available

### Compliance
- ✅ GDPR compliant
- ✅ SOC 2 certified
- ✅ Data residency options
- ✅ Customer data isolation

## Support

Questions about KB integrations?
- **Email**: support@kalevent.com
- **Docs**: [kalevent.com/docs](https://kalevent.com/docs)
- **Request Platform**: Submit integration request
