# Pitched Blog Topics Feature

## Overview

The Pitched Blog Topics feature allows users to manually submit blog topic ideas in addition to the auto-generated topics by the Content Generation Agent. This provides flexibility for timely content, specific customer requests, or strategic content needs.

## Architecture

### Database Model: `PitchedBlogTopic`

Located in: `src/models.py`

**Fields:**
- `id` (UUID) - Primary key
- `title` - Topic title or idea (required)
- `description` - Optional description or angle
- `target_keyword` - Primary SEO keyword
- `secondary_keywords` - Array of additional keywords
- `funnel_stage` - discovery | consideration | decision
- `target_audience` - Target audience description
- `niche` - Blog niche (e.g., "Revenue Operations")
- `pitch_notes` - Additional notes from submitter
- `status` - pending | approved | rejected | generated
- `priority` - 1 (high) | 2 (medium) | 3 (low)
- `submitted_by` - Email of submitter
- `reviewed_by` - User ID of reviewer
- `reviewed_at` - Review timestamp
- `generated_content_id` - Link to generated content (if generated)

**Indexes:**
- `idx_pitched_topics_status` - For filtering by status
- `idx_pitched_topics_created` - For sorting by creation date

### API Endpoints

Located in: `src/api/v1/admin_content.py`

All endpoints require admin authentication via `@jwt_required()`.

#### Submit Topic
```
POST /api/v1/admin/content/pitch-topic
```

**Body:**
```json
{
  "title": "5 Ways to Automate Lead Routing",
  "description": "Focus on RevOps challenges",
  "target_keyword": "lead routing automation",
  "secondary_keywords": ["sales automation", "lead distribution"],
  "funnel_stage": "discovery",
  "target_audience": "VP Revenue Operations, B2B SaaS",
  "niche": "Revenue Operations",
  "pitch_notes": "Customer requested this topic",
  "priority": 1
}
```

#### List Topics
```
GET /api/v1/admin/content/pitched-topics
  ?status=pending
  &priority=1
  &limit=50
  &offset=0
```

#### Approve Topic
```
POST /api/v1/admin/content/pitched-topics/{topic_id}/approve
```

**Body:**
```json
{
  "generate_now": false,
  "priority": 1
}
```

Set `generate_now: true` to immediately queue content generation.

#### Reject Topic
```
POST /api/v1/admin/content/pitched-topics/{topic_id}/reject
```

**Body:**
```json
{
  "reason": "Too similar to existing content"
}
```

#### Delete Topic
```
DELETE /api/v1/admin/content/pitched-topics/{topic_id}
```

### Content Generation Task

Located in: `src/content/tasks.py`

**Task:** `generate_blog_from_pitched_topic(topic_id)`

**Process:**
1. Fetch pitched topic from database
2. Convert to internal topic format
3. Run through full DSPy content pipeline:
   - Outline creation
   - Content writing
   - Editing
   - SEO optimization
   - DALL-E 3 hero image generation
4. Save to `GeneratedContent` and `BlogPost` tables
5. Update pitched topic status to "generated"
6. Send email notification for review

**Security:**
- XSS protection via `sanitize_html()`
- Markdown to HTML conversion with safe extensions
- Hero images uploaded to S3 with Content-Disposition: inline

### Admin UI

Located in:
- Template: `src/templates/admin/pitched_topics.html`
- Routes: `src/admin/routes.py`

**URL:** `/admin/pitched-topics`

**Features:**
- Submit new topics via form
- Filter by status, priority, search query
- View all pitched topics in table
- Approve/reject/delete actions
- Generate content from approved topics
- View generated content (links to blog preview)
- Status badges and priority indicators

**Status Workflow:**
1. `pending` - Newly submitted, awaiting review
2. `approved` - Approved for generation
3. `generated` - Content generated successfully
4. `rejected` - Rejected with optional reason

**Dashboard Link:**
- Added to `/admin` page in Content section
- Button: "Manage Topics" → `/admin/pitched-topics`

## Usage Examples

### Manual Topic Submission (UI)

1. Navigate to `/admin/pitched-topics`
2. Fill out "Pitch a New Topic" form:
   - Title: "Complete Guide to RevOps Automation"
   - Target Keyword: "revenue operations automation"
   - Funnel Stage: discovery
   - Priority: High (1)
   - Description: "Comprehensive guide covering tools, processes, and metrics"
3. Click "Submit Topic"
4. Topic appears in table with status "pending"

### Approval & Generation (UI)

1. Review pending topics in table
2. Click "Approve" for desired topic
3. Click "Generate" to queue content generation
4. Wait 2-3 minutes for task to complete
5. Status updates to "generated"
6. Click "View Post" to preview generated blog

### API Workflow

```bash
# Submit topic
curl -X POST https://api.kalevent.com/api/v1/admin/content/pitch-topic \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Lead Scoring Best Practices 2025",
    "target_keyword": "lead scoring",
    "priority": 1
  }'

# List pending topics
curl -X GET https://api.kalevent.com/api/v1/admin/content/pitched-topics?status=pending \
  -H "Authorization: Bearer $TOKEN"

# Approve and generate
curl -X POST https://api.kalevent.com/api/v1/admin/content/pitched-topics/{id}/approve \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"generate_now": true}'
```

## Integration with Existing System

### Relationship to Auto-Generated Topics

- **Auto-generated**: `generate_blog_post()` task generates topics using `TopicGeneratorModule`
- **Pitched**: `generate_blog_from_pitched_topic()` task uses manually submitted topics
- Both use the same content pipeline (outline → write → edit → SEO → hero image)
- Both save to same tables: `GeneratedContent` and `BlogPost`

### Tracking

- Pitched topics linked via `generated_content_id` foreign key
- `meta_data` field includes `pitched_topic_id` for traceability
- `generation_pipeline` JSON includes full pipeline outputs

### Content Review Workflow

Generated content from pitched topics follows same workflow as auto-generated:
1. Status: `ready` (requires review)
2. Admin reviews at `/publishing/blog/draft/{id}`
3. Approve → status: `published`
4. Viewable at `/blog/{slug}`

## Configuration

No environment variables required. Uses existing DSPy and DALL-E 3 configuration:
- `DSPY_PROVIDER` - DSPy LLM provider (default: openai)
- `DSPY_MODEL` - DSPy model (default: gpt-4o-mini)
- `OPENAI_API_KEY` - For DALL-E 3 hero images

## Database Migration

After adding the `PitchedBlogTopic` model, run:

```bash
flask db migrate -m "Add pitched_blog_topics table"
flask db upgrade
```

Migration will create:
- `pitched_blog_topics` table
- Indexes on status and created_at
- Foreign key to `generated_content.id`

## Security Considerations

1. **Authentication**: All endpoints require admin JWT token
2. **XSS Protection**: HTML sanitization via `bleach.clean()`
3. **SQL Injection**: Parameterized queries via SQLAlchemy ORM
4. **File Upload Security**: Hero images uploaded to S3, not stored in DB
5. **Content-Disposition**: Images served with `inline` disposition

## Future Enhancements

Potential improvements:
- **Scheduling**: Schedule pitched topics for specific dates
- **Bulk Import**: CSV import for multiple topics
- **Keyword Research**: Auto-suggest keywords via SEO tools
- **Topic Clustering**: Group similar topics
- **Performance Metrics**: Track views/engagement per pitched topic
- **User Submissions**: Allow non-admin users to submit topics (with approval)
- **AI Topic Validation**: DSPy module to validate topic feasibility

## Related Documentation

- [Content Generation v2.0](./content_generation_v2.md)
- [DSPy Integration](./dspy_integration.md)
- [Upload Isolation](./upload_isolation.md)
- [Publishing Workflow](./publishing_workflow.md)
