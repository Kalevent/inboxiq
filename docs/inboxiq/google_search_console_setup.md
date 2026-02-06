# Google Search Console Integration Setup

**Goal**: Display real impressions and clicks data in the admin dashboard

**Current Status**: Hardcoded to `None` - needs API integration

---

## Setup Steps

### 1. **Verify Site in Google Search Console**

First, ensure your site is verified in GSC:

1. Go to [Google Search Console](https://search.google.com/search-console/)
2. Add your property: `https://kalevent.com` (or your domain)
3. Verify ownership via:
   - HTML file upload
   - DNS TXT record
   - Google Analytics
   - Google Tag Manager

### 2. **Enable Search Console API**

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Select your project (or create one)
3. Go to **APIs & Services** > **Library**
4. Search for "**Google Search Console API**"
5. Click **Enable**

### 3. **Create Service Account Credentials**

**Option A: Service Account (Recommended for automation)**

1. Go to **APIs & Services** > **Credentials**
2. Click **Create Credentials** > **Service Account**
3. Fill in details:
   - Name: `InboxIQ GSC Reader`
   - Role: `Viewer`
4. Click **Done**
5. Click on the created service account
6. Go to **Keys** tab > **Add Key** > **Create new key**
7. Choose **JSON** format
8. Download the JSON file
9. Save it securely (e.g., `/path/to/gsc-service-account.json`)

**Option B: OAuth 2.0 (If you want user-specific access)**

1. Go to **APIs & Services** > **Credentials**
2. Click **Create Credentials** > **OAuth client ID**
3. Application type: **Desktop app**
4. Download credentials JSON

### 4. **Grant Service Account Access to GSC**

1. Go back to [Google Search Console](https://search.google.com/search-console/)
2. Select your property
3. Click **Settings** (gear icon)
4. Click **Users and permissions**
5. Click **Add user**
6. Enter the service account email (from step 3):
   - Format: `inboxiq-gsc-reader@project-id.iam.gserviceaccount.com`
7. Permission level: **Restricted** (read-only)
8. Click **Add**

### 5. **Add Environment Variables**

Add to your `.env` file:

```bash
# Google Search Console API
GSC_ENABLED=true
GSC_SERVICE_ACCOUNT_FILE=/path/to/gsc-service-account.json
GSC_SITE_URL=https://kalevent.com  # Your verified site URL

# Or if using OAuth 2.0
GSC_CREDENTIALS_FILE=/path/to/gsc-oauth-credentials.json
GSC_TOKEN_FILE=/path/to/gsc-token.json  # Auto-generated
```

---

## Implementation Code

### Install Required Package

```bash
pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
```

Add to `requirements.txt`:
```
google-api-python-client>=2.0.0
google-auth-httplib2>=0.1.0
google-auth-oauthlib>=0.5.0
```

### Create GSC Helper Module

**File**: `src/integrations/google_search_console.py`

```python
"""
Google Search Console API integration for blog metrics.
"""
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


class GoogleSearchConsole:
    """Client for Google Search Console API."""

    SCOPES = ['https://www.googleapis.com/auth/webmasters.readonly']

    def __init__(self, service_account_file: Optional[str] = None, site_url: Optional[str] = None):
        """
        Initialize GSC client.

        Args:
            service_account_file: Path to service account JSON file
            site_url: Verified site URL (e.g., 'https://kalevent.com')
        """
        self.service_account_file = service_account_file or os.getenv('GSC_SERVICE_ACCOUNT_FILE')
        self.site_url = site_url or os.getenv('GSC_SITE_URL')

        if not self.service_account_file:
            raise ValueError("GSC_SERVICE_ACCOUNT_FILE not configured")
        if not self.site_url:
            raise ValueError("GSC_SITE_URL not configured")

        # Authenticate
        credentials = service_account.Credentials.from_service_account_file(
            self.service_account_file,
            scopes=self.SCOPES
        )

        # Build Search Console service
        self.service = build('searchconsole', 'v1', credentials=credentials)

    def get_search_analytics(
        self,
        days: int = 30,
        dimensions: Optional[List[str]] = None,
        row_limit: int = 1000
    ) -> Dict:
        """
        Get search analytics data from GSC.

        Args:
            days: Number of days to look back (default: 30)
            dimensions: List of dimensions to group by (e.g., ['page', 'query'])
            row_limit: Max rows to return (default: 1000)

        Returns:
            Dict with impressions, clicks, ctr, position data
        """
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)

        request_body = {
            'startDate': start_date.isoformat(),
            'endDate': end_date.isoformat(),
            'dimensions': dimensions or [],
            'rowLimit': row_limit
        }

        try:
            response = self.service.searchanalytics().query(
                siteUrl=self.site_url,
                body=request_body
            ).execute()

            # Aggregate totals
            total_impressions = 0
            total_clicks = 0
            total_ctr = 0.0
            total_position = 0.0
            rows = response.get('rows', [])

            for row in rows:
                total_impressions += row.get('impressions', 0)
                total_clicks += row.get('clicks', 0)
                total_ctr += row.get('ctr', 0.0)
                total_position += row.get('position', 0.0)

            avg_ctr = (total_ctr / len(rows)) if rows else 0.0
            avg_position = (total_position / len(rows)) if rows else 0.0

            return {
                'impressions': total_impressions,
                'clicks': total_clicks,
                'ctr': avg_ctr,
                'position': avg_position,
                'rows': rows,
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            }

        except HttpError as error:
            print(f"GSC API error: {error}")
            return {
                'impressions': None,
                'clicks': None,
                'ctr': None,
                'position': None,
                'error': str(error)
            }

    def get_blog_metrics(self, path_prefix: str = '/blog/') -> Dict:
        """
        Get metrics specifically for blog posts.

        Args:
            path_prefix: URL path prefix for blog posts (default: '/blog/')

        Returns:
            Dict with blog-specific metrics
        """
        # Get all pages with blog prefix
        data = self.get_search_analytics(
            days=30,
            dimensions=['page'],
            row_limit=1000
        )

        if data.get('error'):
            return data

        # Filter to blog posts only
        blog_rows = [
            row for row in data.get('rows', [])
            if path_prefix in row.get('keys', [''])[0]
        ]

        blog_impressions = sum(row.get('impressions', 0) for row in blog_rows)
        blog_clicks = sum(row.get('clicks', 0) for row in blog_rows)
        blog_ctr = (blog_clicks / blog_impressions * 100) if blog_impressions > 0 else 0.0

        return {
            'impressions': blog_impressions,
            'clicks': blog_clicks,
            'ctr': blog_ctr,
            'indexed_pages': len(blog_rows),
            'top_posts': sorted(
                blog_rows,
                key=lambda x: x.get('clicks', 0),
                reverse=True
            )[:10]  # Top 10 posts by clicks
        }

    def get_top_queries(self, limit: int = 10) -> List[Dict]:
        """
        Get top search queries driving traffic.

        Args:
            limit: Number of queries to return

        Returns:
            List of top queries with metrics
        """
        data = self.get_search_analytics(
            days=30,
            dimensions=['query'],
            row_limit=limit
        )

        return sorted(
            data.get('rows', []),
            key=lambda x: x.get('clicks', 0),
            reverse=True
        )[:limit]


# Singleton instance
_gsc_client = None


def get_gsc_client() -> Optional[GoogleSearchConsole]:
    """
    Get or create GSC client singleton.

    Returns:
        GoogleSearchConsole instance or None if not configured
    """
    global _gsc_client

    if _gsc_client is not None:
        return _gsc_client

    # Check if GSC is enabled
    if not os.getenv('GSC_ENABLED', '').lower() in ('true', '1', 'yes'):
        return None

    try:
        _gsc_client = GoogleSearchConsole()
        return _gsc_client
    except (ValueError, FileNotFoundError) as e:
        print(f"GSC client initialization failed: {e}")
        return None
```

### Update Admin API Endpoint

**File**: `src/api/v1/admin.py`

Replace the placeholder `admin_blog_metrics()` function:

```python
@v1.route("/admin/blog-metrics", methods=["GET"])
@jwt_required()
def admin_blog_metrics():
    """
    Weekly blog metrics with real GSC data.
    """
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    try:
        from src.models import BlogPost
        from src.integrations.google_search_console import get_gsc_client

        # Get blog post counts from database
        total_posts = db.session.query(func.count(BlogPost.id)).scalar() or 0
        published = (
            db.session.query(func.count(BlogPost.id))
            .filter(BlogPost.status == "published")
            .scalar()
            or 0
        )
        avg_word_count = (
            db.session.query(func.avg(BlogPost.word_count))
            .filter(BlogPost.word_count.isnot(None))
            .scalar()
        )
        avg_read_time = (
            db.session.query(func.avg(BlogPost.read_time_minutes))
            .filter(BlogPost.read_time_minutes.isnot(None))
            .scalar()
        )

        # Get GSC data if configured
        gsc_client = get_gsc_client()
        gsc_data = {}

        if gsc_client:
            try:
                gsc_data = gsc_client.get_blog_metrics(path_prefix='/blog/')
            except Exception as gsc_error:
                print(f"GSC fetch error: {gsc_error}")
                gsc_data = {
                    'impressions': None,
                    'clicks': None,
                    'ctr': None,
                    'indexed_pages': None
                }
        else:
            # GSC not configured - return None values
            gsc_data = {
                'impressions': None,
                'clicks': None,
                'ctr': None,
                'indexed_pages': None
            }

        return jsonify(
            {
                "impressions": gsc_data.get('impressions'),
                "clicks": gsc_data.get('clicks'),
                "ctr": gsc_data.get('ctr'),
                "indexed_pages": gsc_data.get('indexed_pages'),
                "total_posts": int(total_posts),
                "published_posts": int(published),
                "avg_word_count": float(avg_word_count) if avg_word_count else None,
                "avg_read_time_minutes": float(avg_read_time) if avg_read_time else None,
                "rankings": [],  # Could add top queries here
                "signups_from_blog": None,  # Would come from GA or your analytics
                "time_on_page_seconds": None,  # Would come from GA
            }
        )

    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
```

---

## Testing

### 1. **Test GSC Connection**

Create a test script: `test_gsc.py`

```python
from src.integrations.google_search_console import GoogleSearchConsole

gsc = GoogleSearchConsole()

# Test basic connection
data = gsc.get_search_analytics(days=7)
print(f"Last 7 days:")
print(f"  Impressions: {data['impressions']}")
print(f"  Clicks: {data['clicks']}")
print(f"  CTR: {data['ctr']:.2%}")

# Test blog metrics
blog_data = gsc.get_blog_metrics()
print(f"\nBlog metrics:")
print(f"  Impressions: {blog_data['impressions']}")
print(f"  Clicks: {blog_data['clicks']}")
print(f"  Indexed pages: {blog_data['indexed_pages']}")

# Test top queries
queries = gsc.get_top_queries(limit=5)
print(f"\nTop 5 queries:")
for i, query in enumerate(queries, 1):
    print(f"  {i}. {query['keys'][0]} - {query['clicks']} clicks")
```

Run it:
```bash
python test_gsc.py
```

### 2. **Test Admin Endpoint**

```bash
export TOKEN="your_jwt_token"

curl -X GET "http://localhost:8000/api/v1/admin/blog-metrics" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json"
```

Expected response:
```json
{
  "impressions": 1234,
  "clicks": 56,
  "ctr": 4.5,
  "indexed_pages": 13,
  "total_posts": 15,
  "published_posts": 13,
  "avg_word_count": 1523,
  "avg_read_time_minutes": 7.2
}
```

---

## Caching Strategy (Optional)

Since GSC API has rate limits (600 queries per 100 seconds), add caching:

```python
from functools import lru_cache
from datetime import datetime, timedelta

# Cache GSC data for 1 hour
@lru_cache(maxsize=1)
def get_cached_gsc_metrics(timestamp: int):
    """
    Get GSC metrics with 1-hour cache.

    Args:
        timestamp: Unix timestamp rounded to nearest hour
    """
    gsc = get_gsc_client()
    if not gsc:
        return None
    return gsc.get_blog_metrics()

# In admin endpoint
def admin_blog_metrics():
    # ... existing code ...

    # Get current hour timestamp for cache key
    current_hour = int(datetime.now().timestamp() // 3600)
    gsc_data = get_cached_gsc_metrics(current_hour)

    # ... rest of code ...
```

---

## Troubleshooting

### Error: "User does not have sufficient permissions"

**Fix**: Make sure you added the service account email to GSC with at least "Restricted" permissions.

### Error: "Service account file not found"

**Fix**: Check the file path in `GSC_SERVICE_ACCOUNT_FILE` is correct and the file exists.

### Error: "Site not found"

**Fix**: Ensure `GSC_SITE_URL` exactly matches the property URL in Search Console (including `https://` and trailing slash if applicable).

### No data returned

**Possible causes**:
1. **Blog posts are new**: GSC data has a 2-3 day delay
2. **Not indexed yet**: Check Google Search Console → Coverage report
3. **URL mismatch**: Ensure blog post URLs match the site URL pattern

---

## Alternative: Google Analytics 4

If you prefer GA4 data over GSC:

1. Enable **Google Analytics Data API** in Cloud Console
2. Use `google-analytics-data` package
3. Track pageviews, time on page, bounce rate
4. More real-time than GSC (but less SEO-specific)

**Quick setup**:
```bash
pip install google-analytics-data
```

```python
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import RunReportRequest

def get_ga4_blog_metrics(property_id: str, days: int = 30):
    client = BetaAnalyticsDataClient()

    request = RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[{"start_date": f"{days}daysAgo", "end_date": "today"}],
        dimensions=[{"name": "pagePath"}],
        metrics=[
            {"name": "screenPageViews"},
            {"name": "averageSessionDuration"},
            {"name": "bounceRate"}
        ],
        dimension_filter={
            "filter": {
                "field_name": "pagePath",
                "string_filter": {"match_type": "BEGINS_WITH", "value": "/blog/"}
            }
        }
    )

    response = client.run_report(request)
    # Process response...
```

---

## Environment Variables Summary

Add these to `.env`:

```bash
# Google Search Console
GSC_ENABLED=true
GSC_SERVICE_ACCOUNT_FILE=/Users/kofi/inboxiq/gsc-service-account.json
GSC_SITE_URL=https://kalevent.com

# Optional: Google Analytics 4
GA4_ENABLED=false
GA4_PROPERTY_ID=123456789
GA4_SERVICE_ACCOUNT_FILE=/Users/kofi/inboxiq/ga4-service-account.json
```

---

**Next Steps**:
1. Complete Google Cloud Console setup
2. Download service account JSON
3. Add to GSC with permissions
4. Add .env variables
5. Create `src/integrations/google_search_console.py`
6. Update `src/api/v1/admin.py`
7. Restart Flask app
8. Refresh admin page → see real data! 📊
