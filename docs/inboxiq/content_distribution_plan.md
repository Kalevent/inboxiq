# Content Distribution & Social Media Strategy

**Status**: Planning Phase
**Created**: 2026-02-06
**Goal**: Automate blog post distribution to social media and other channels to maximize reach

---

## Current State Analysis

### ✅ What's Working
- **Content Generation**: Fully automated DSPy-powered blog generation
- **Pitched Topics**: Manual topic submission system complete
- **Publishing**: Blogs auto-published to `/blog/{slug}` with SEO optimization
- **Google Analytics**: Already integrated for tracking
- **Funnel System**: Complete 5-stage lead tracking

### ❌ What's Missing
- **Social Media Distribution**: No automated posting to social platforms
- **Content Promotion**: Blogs are published but not actively promoted
- **Multi-channel Reach**: Limited to organic SEO traffic only
- **Engagement Tracking**: No tracking of social engagement metrics
- **Content Calendar**: No scheduled distribution strategy

---

## Required Environment Variables

### Google Calendar Integration (for Demo Scheduling)

```bash
# Google Calendar API Setup
GCAL_BOOKING_URL="https://calendar.google.com/calendar/appointments/schedules/..."  # Your booking page URL
GCAL_CREDENTIALS_FILE="/path/to/google-oauth-credentials.json"  # OAuth 2.0 Desktop app credentials
GCAL_TOKEN_FILE="/path/to/google-calendar-token.json"  # Auto-generated after first auth

# Setup Steps:
# 1. Go to https://console.cloud.google.com/
# 2. Enable Google Calendar API
# 3. Create OAuth 2.0 credentials (Desktop app)
# 4. Download credentials.json
# 5. First run will open browser for authorization
# 6. Token stored automatically for future use
```

### Social Media APIs (Optional - For Distribution)

```bash
# Twitter/X API v2 (if using Twitter distribution)
TWITTER_API_KEY="your_api_key"
TWITTER_API_SECRET="your_api_secret"
TWITTER_ACCESS_TOKEN="your_access_token"
TWITTER_ACCESS_SECRET="your_access_secret"
TWITTER_BEARER_TOKEN="your_bearer_token"

# LinkedIn API (if using LinkedIn distribution)
LINKEDIN_ACCESS_TOKEN="your_linkedin_token"
LINKEDIN_ORGANIZATION_ID="your_company_page_id"  # For company page posts

# Facebook/Meta API (if using Facebook distribution)
FACEBOOK_PAGE_ACCESS_TOKEN="your_page_token"
FACEBOOK_PAGE_ID="your_page_id"

# Buffer API (Alternative - easier multi-platform posting)
BUFFER_ACCESS_TOKEN="your_buffer_token"
BUFFER_PROFILE_IDS="profile1_id,profile2_id"  # Comma-separated

# Zapier/Make Webhook (Easiest option - no code needed)
ZAPIER_WEBHOOK_URL="https://hooks.zapier.com/hooks/catch/..."
MAKE_WEBHOOK_URL="https://hook.integromat.com/..."
```

### Content Distribution Settings

```bash
# Distribution Configuration
CONTENT_DISTRIBUTION_ENABLED="true"  # Enable/disable auto-distribution
DISTRIBUTION_DELAY_HOURS="2"  # Wait N hours after publish before distributing
DISTRIBUTION_PLATFORMS="twitter,linkedin"  # Comma-separated list

# Social Media Posting Settings
TWITTER_POST_ENABLED="true"
LINKEDIN_POST_ENABLED="true"
FACEBOOK_POST_ENABLED="false"

# Post Template Settings
SOCIAL_POST_INCLUDE_IMAGE="true"  # Include blog hero image
SOCIAL_POST_MAX_LENGTH_TWITTER="280"
SOCIAL_POST_MAX_LENGTH_LINKEDIN="3000"
SOCIAL_POST_HASHTAGS_MAX="5"
```

---

## Blog Distribution Strategy

### Current Flow (What Exists)
```
1. Generate Topic (DSPy)
   ↓
2. Create Outline (DSPy)
   ↓
3. Write Content (DSPy)
   ↓
4. Edit & Polish (DSPy)
   ↓
5. SEO Optimize (DSPy)
   ↓
6. Generate Hero Image (DALL-E 3)
   ↓
7. Publish to /blog/{slug}
   ↓
8. ❌ END (No distribution!)
```

### Proposed Flow (What We Need)
```
1-7. [Same as above]
   ↓
8. Generate Social Posts (NEW - DSPy)
   ↓
9. Distribute to Social Media (NEW)
   ├── Twitter/X
   ├── LinkedIn
   ├── Facebook
   └── Buffer/Zapier
   ↓
10. Track Engagement (NEW)
    ├── Clicks from social
    ├── Shares/Retweets
    ├── Comments
    └── Conversions
```

---

## Implementation Options

### Option 1: Direct API Integration (Most Control)
**Pros**: Full control, no third-party dependency, free
**Cons**: Need API keys for each platform, rate limits, maintenance

**Components**:
- Social Media MCP Server (`src/mcp/social_media_mcp.py`)
- Platform-specific posting logic
- Error handling and retries
- Engagement tracking

**Effort**: 2-3 days

---

### Option 2: Buffer API (Recommended - Easiest)
**Pros**: One API for all platforms, scheduling, analytics
**Cons**: Monthly cost ($6-12/month), limited customization

**Components**:
- Buffer MCP Server (`src/mcp/buffer_mcp.py`)
- Simple HTTP POST to Buffer API
- Buffer handles all platform specifics

**Effort**: 4-6 hours

---

### Option 3: Zapier/Make Webhooks (No Code Required)
**Pros**: No code needed, visual workflow builder, many integrations
**Cons**: Monthly cost ($20-50/month), less customization

**Setup**:
1. Create Zap/Scenario: Webhook → Format → Post to Social Media
2. Send webhook from our app when blog published
3. Zapier handles rest automatically

**Effort**: 1-2 hours

---

### Option 4: MCP for Claude Desktop (Hybrid Approach)
**Pros**: Use existing Claude MCP ecosystem, human oversight
**Cons**: Not fully automated, requires Claude Desktop

**Available MCP Servers**:
- `@modelcontextprotocol/server-twitter` - Post to Twitter/X
- Community LinkedIn MCP servers
- Custom webhook MCP for any platform

**Workflow**:
1. Blog published → Notification sent
2. Claude Desktop reviews blog
3. Claude generates social posts using MCPs
4. Human approves and posts via Claude

**Effort**: 2-3 hours

---

## Recommended Implementation Plan

### Phase 1: Quick Win with Webhooks (1-2 hours)
**Goal**: Get basic distribution working ASAP

1. Add webhook trigger when blog published
2. Set up Zapier/Make to receive webhook
3. Configure social media posts in Zapier
4. Test with one blog post

**No code changes needed** - Just configuration!

---

### Phase 2: DSPy Social Post Generator (4-6 hours)
**Goal**: AI-generated social media posts

**New DSPy Module**: `SocialPostGeneratorModule`

```python
class SocialPostGeneratorSignature(dspy.Signature):
    """Generate social media posts from blog content."""

    blog_title = dspy.InputField(desc="Blog post title")
    blog_summary = dspy.InputField(desc="First 200 words of blog")
    target_keyword = dspy.InputField(desc="Primary SEO keyword")
    platform = dspy.InputField(desc="twitter | linkedin | facebook")
    tone = dspy.InputField(desc="Tone: professional | casual | thought-leadership")

    post_text = dspy.OutputField(desc="Social media post text (respects platform char limits)")
    hashtags = dspy.OutputField(desc="JSON array of relevant hashtags (3-5)")
    cta = dspy.OutputField(desc="Call-to-action: read_more | comment | share | book_demo")
    post_type = dspy.OutputField(desc="text_only | with_image | with_video | carousel")
```

**Implementation**:
- File: `src/dspy/social/post_generator.py`
- Training data: High-performing social posts
- Optimization metric: Engagement rate (likes + comments + shares)

---

### Phase 3: Automated Distribution (6-8 hours)
**Goal**: Fully automated posting to social platforms

**Option A: Build Direct Integration**
- Implement Twitter API v2 posting
- Implement LinkedIn API posting
- Add rate limiting and retry logic
- Track engagement metrics

**Option B: Use Buffer API (Recommended)**
- Single API endpoint for all platforms
- Built-in scheduling and analytics
- Much easier to maintain

**Components**:
1. Buffer MCP Server or HTTP client
2. Celery task: `distribute_blog_to_social(blog_id)`
3. Social post tracking table in DB
4. Engagement metrics collection

---

### Phase 4: Analytics & Optimization (4-6 hours)
**Goal**: Track what works and optimize

**Metrics to Track**:
- Clicks from each platform
- Engagement rate (likes, comments, shares)
- Conversion rate (social → funnel)
- Best posting times
- Best hashtags
- Best post formats

**Implementation**:
- UTM parameters: `?utm_source=twitter&utm_medium=social&utm_campaign=blog_post`
- Social engagement webhook listeners
- Performance dashboard
- A/B testing for post variations

---

## Database Schema for Social Distribution

```sql
-- Social media posts tracking
CREATE TABLE social_media_posts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    blog_post_id VARCHAR(64) REFERENCES blog_posts(id) ON DELETE CASCADE,
    platform VARCHAR(50) NOT NULL, -- twitter, linkedin, facebook, buffer
    post_text TEXT NOT NULL,
    hashtags JSONB, -- ["hashtag1", "hashtag2"]
    post_url TEXT, -- URL of published social post
    scheduled_at TIMESTAMP WITH TIME ZONE,
    published_at TIMESTAMP WITH TIME ZONE,
    status VARCHAR(50) DEFAULT 'pending', -- pending, published, failed
    error_message TEXT,
    metadata_json JSONB, -- platform-specific data
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Social engagement metrics
CREATE TABLE social_engagement_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    social_post_id UUID REFERENCES social_media_posts(id) ON DELETE CASCADE,
    platform VARCHAR(50) NOT NULL,
    likes_count INT DEFAULT 0,
    comments_count INT DEFAULT 0,
    shares_count INT DEFAULT 0,
    clicks_count INT DEFAULT 0,
    impressions_count INT DEFAULT 0,
    engagement_rate FLOAT, -- (likes + comments + shares) / impressions
    collected_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_social_posts_blog ON social_media_posts(blog_post_id);
CREATE INDEX idx_social_posts_platform ON social_media_posts(platform, status);
CREATE INDEX idx_social_engagement_post ON social_engagement_metrics(social_post_id);
```

---

## Content Calendar Strategy

### Posting Schedule (Automated)

**Weekly Blog Generation** (Already Exists):
- Monday 6am UTC: Generate 1 blog post
- Auto-publish to website

**Social Media Distribution** (New):
- Monday 8am UTC: Post to LinkedIn (B2B audience active)
- Monday 12pm UTC: Post to Twitter (lunch hour engagement)
- Monday 6pm UTC: Repost to Twitter with different angle
- Wednesday 10am UTC: Share on LinkedIn with community question
- Friday 2pm UTC: Final Twitter post with key takeaway

**Monthly Newsletter** (Future):
- First Monday of month: Email newsletter with all month's content
- Curated list of top 3-4 posts
- Personal insights from "founder"

---

## Social Media Post Templates

### Twitter/X Template
```
🚀 New Post: {blog_title}

{key_insight_1_sentence}

Read more: {url}?utm_source=twitter

{hashtag1} {hashtag2} {hashtag3}
```

### LinkedIn Template
```
{hook_question}

{2_paragraph_summary}

🔗 Full article: {url}?utm_source=linkedin

What's your experience with {topic}? Let me know in the comments! 👇

{hashtag1} {hashtag2} {hashtag3}
```

### Facebook Template
```
{engaging_opening}

{blog_summary_3_paragraphs}

➡️ Continue reading: {url}?utm_source=facebook

[Image: Hero image from blog]

{hashtag1} {hashtag2} {hashtag3}
```

---

## Integration with Existing Funnel

### Attribution Tracking

When someone clicks from social media:
1. **UTM Parameters**: `?utm_source=twitter&utm_medium=social&utm_campaign=blog_revops_automation`
2. **Lead Creation**: If they sign up, create Lead with `first_attribution_source=twitter`
3. **Funnel Stage**: Start at "visits" stage
4. **Engagement Event**: Record `lead_engagement_events` with `event_source=twitter`
5. **Attribution**: Track in `lead_attribution` table

### Conversion Tracking

```python
# In funnel engagement tracking
@mcp.tool()
def track_social_click(post_id: str, platform: str, visitor_id: str):
    """
    Track when someone clicks blog link from social media.

    Creates Lead if new visitor, records engagement event.
    """
    # Parse UTM parameters from request
    utm_source = request.args.get('utm_source')
    utm_campaign = request.args.get('utm_campaign')

    # Create or update lead
    lead = Lead.query.filter_by(visitor_id=visitor_id).first()
    if not lead:
        lead = Lead(
            visitor_id=visitor_id,
            first_attribution_source=platform,
            first_attribution_campaign=utm_campaign,
            current_funnel_stage='visits'
        )
        db.session.add(lead)

    # Record engagement
    event = LeadEngagementEvent(
        lead_id=lead.id,
        event_type='social_media_click',
        event_source=platform,
        event_data={'post_id': post_id, 'campaign': utm_campaign}
    )
    db.session.add(event)
    db.session.commit()
```

---

## Recommended MCP Servers for Social Media

### 1. Buffer MCP (Easiest - Multi-platform)
```bash
# Install Buffer MCP
npm install -g @buffer/mcp-server

# Configure
export BUFFER_ACCESS_TOKEN="your_token"
export BUFFER_PROFILE_IDS="twitter_id,linkedin_id"
```

**Tools**:
- `create_post(text, profile_ids, scheduled_at, media_url)`
- `get_analytics(post_id)`
- `schedule_posts(posts_array)`

---

### 2. Twitter MCP (Official)
```bash
# Install Twitter MCP
npm install -g @modelcontextprotocol/server-twitter

# Configure
export TWITTER_API_KEY="..."
export TWITTER_API_SECRET="..."
```

**Tools**:
- `post_tweet(text, media_ids, reply_to)`
- `get_mentions()`
- `get_analytics(tweet_id)`

---

### 3. Custom Social Distribution MCP

**File**: `src/mcp/social_distribution_mcp.py`

```python
@mcp.tool()
def distribute_blog_post(blog_id: str, platforms: List[str], delay_hours: int = 2):
    """
    Distribute blog post to social media platforms.

    Args:
        blog_id: Blog post UUID
        platforms: ["twitter", "linkedin", "facebook"]
        delay_hours: Wait N hours before posting

    Returns:
        Task IDs for scheduled posts
    """
    blog = BlogPost.query.get(blog_id)
    if not blog:
        return {"error": "Blog not found"}

    # Generate social posts using DSPy
    post_generator = SocialPostGeneratorModule()

    task_ids = []
    for platform in platforms:
        # Generate platform-specific post
        result = post_generator(
            blog_title=blog.title,
            blog_summary=blog.content[:500],
            target_keyword=blog.meta_data.get('target_keywords', [''])[0],
            platform=platform,
            tone="professional"
        )

        # Schedule Celery task
        scheduled_time = datetime.now() + timedelta(hours=delay_hours)
        task = post_to_social_media.apply_async(
            args=[blog_id, platform, result.post_text, result.hashtags],
            eta=scheduled_time
        )
        task_ids.append(task.id)

    return {"success": True, "task_ids": task_ids, "scheduled_for": scheduled_time.isoformat()}
```

---

## Implementation Priorities

### Must Have (Week 1)
1. ✅ **Webhook to Zapier** - Get distribution working (1-2 hours)
2. ✅ **UTM parameter tracking** - Attribution from social (2 hours)
3. ✅ **Social post generator DSPy module** - AI-written posts (4-6 hours)

### Should Have (Week 2)
4. ⚠️ **Buffer integration** - Multi-platform posting (4-6 hours)
5. ⚠️ **Social posts tracking table** - Database schema (2 hours)
6. ⚠️ **Engagement metrics collection** - Track performance (4 hours)

### Nice to Have (Week 3+)
7. ⚪ **A/B testing for posts** - Optimize performance
8. ⚪ **Best time to post analysis** - ML-based scheduling
9. ⚪ **Content repurposing** - Turn 1 blog into 5+ social posts
10. ⚪ **Community engagement automation** - Auto-reply to comments

---

## Cost Analysis

### Free Options
- ✅ Direct API integration (Twitter, LinkedIn, Facebook)
- ✅ Zapier Free tier (100 tasks/month - enough for testing)
- ✅ Make Free tier (1000 ops/month)

### Paid Options (Recommended)
- **Buffer Essentials**: $6/month (1 user, all platforms, scheduling)
- **Buffer Team**: $12/month (better analytics, more posts)
- **Zapier Starter**: $20/month (750 tasks/month)
- **Make Core**: $9/month (10,000 ops/month)

**Recommended**: Buffer Essentials ($6/month) - Easiest, most reliable

---

## Success Metrics

### Social Media KPIs
- **Reach**: Impressions per post
- **Engagement Rate**: (Likes + Comments + Shares) / Impressions
- **Click-Through Rate**: Clicks / Impressions
- **Conversion Rate**: Leads from social / Total clicks
- **Cost Per Lead**: Social media budget / Leads generated

### Content Performance
- **Best Performing Platforms**: Twitter vs LinkedIn vs Facebook
- **Best Post Times**: Weekday/weekend, morning/afternoon
- **Best Content Types**: How-to vs thought-leadership vs case studies
- **Best Hashtags**: Which generate most engagement

### Funnel Impact
- **Social → Visits Conversion**: % who enter funnel from social
- **Social → Discovery Conversion**: % who engage after social visit
- **Attribution Share**: % of conversions attributed to social media
- **LTV by Source**: Lifetime value of social media leads vs others

---

## Next Steps

1. **Choose Distribution Method**:
   - Quick: Zapier webhook (1-2 hours)
   - Best: Buffer API (4-6 hours)
   - Full Control: Direct APIs (2-3 days)

2. **Implement Social Post Generator**:
   - Create DSPy module
   - Train on successful posts
   - Integrate with blog generation pipeline

3. **Set Up Tracking**:
   - UTM parameters
   - Social engagement webhooks
   - Analytics dashboard

4. **Test & Iterate**:
   - Publish 1 blog with social distribution
   - Monitor engagement
   - Optimize based on data

---

## Questions to Answer

1. **Which social platforms are priority?**
   - Twitter/X (tech audience)
   - LinkedIn (B2B, RevOps professionals)
   - Facebook (broader reach)
   - All of the above?

2. **Distribution frequency?**
   - 1 post per blog (simple)
   - Multiple posts over time (better reach)
   - Scheduled reposts (maximize visibility)

3. **Human oversight?**
   - Fully automated (trust the AI)
   - Review before posting (safer)
   - Claude Desktop hybrid (best of both)

4. **Budget for tools?**
   - Free (direct APIs, more work)
   - ~$10/month (Buffer, easiest)
   - ~$20-50/month (Zapier/Make, no code)

---

**Status**: Ready to implement once we decide on approach
**Next**: User input on preferred method and priorities
