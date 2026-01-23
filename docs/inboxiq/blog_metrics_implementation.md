# Blog / SEO Metrics Implementation Plan

## Goals
- Populate `/api/v1/admin/blog-metrics` with real data instead of placeholders.
- Surface weekly metrics in the Admin UI for SEO and conversion performance.
- Maintain a simple, secure, and cache-friendly integration pattern.

## Metrics to Deliver (weekly or rolling 7-day)
- Google Search Console (GSC): impressions, clicks, indexed pages.
- Rankings (avg position) for key keywords: `ai support agent`, `ai email triage`, `zendesk ai alternative`.
- Time on page (avg) for blog articles (from analytics).
- Signups attributed to blog traffic (from analytics/attribution).

## Data Sources
- **GSC API** via a service account (preferred) or OAuth client.
  - Endpoint: Search Analytics → `searchanalytics.query`.
  - Dimensions: `date`, `page`, `query` for keywords; filter to `page` containing `/blog`.
- **Analytics** (GA4 recommended) for time-on-page and signups by source/medium or landing page:
  - Metrics: `averageSessionDuration`, custom events for signup.
  - Dimensions: landing page (`/blog/*`), source/medium.
- **Attribution**: use analytics events for signups with landing page or referrer; fallback to DB if UTM/referrer stored on signup.

## Architecture
1) **Server-side fetcher**: create `src/metrics/blog_sources.py` to query GSC and GA4 (or your analytics provider).
2) **Config/env**: add credentials and property IDs to `.env` and `Config`:
   - `GSC_SITE_URL`, `GSC_CREDENTIALS_JSON` (or path), `GA_PROPERTY_ID`, `GA_API_SECRET` (if using Measurement Protocol), or GA service account JSON.
3) **Caching**: use Flask-Caching/Redis to cache responses for 12–24 hours to avoid API limits.
4) **Endpoint wiring**: update `/api/v1/admin/blog-metrics` to call the fetcher and return real values.

## Steps
1. **Credentials & config**
   - Add env vars for GSC and GA (or your analytics) to `.env`.
   - Update `src/config.py` to read them.
2. **GSC client**
   - Implement a helper in `src/metrics/gsc.py` that:
     - Authenticates with service account credentials.
     - Runs `searchanalytics.query` for last 7 days, filtering `page` contains `/blog`.
     - Aggregates impressions, clicks, indexed pages (via sitemaps index or coverage if available), and per-keyword positions.
3. **Analytics client**
   - Implement `src/metrics/analytics.py`:
     - Fetch average time on page for `/blog/*`.
     - Fetch signups attributed to blog (landing page `/blog/*` and event = signup).
4. **Aggregator**
   - Create `src/metrics/blog.py` to combine GSC + analytics; apply caching.
5. **API endpoint**
   - Update `/api/v1/admin/blog-metrics` to return real data from `blog.py` instead of placeholders.
6. **Admin UI**
   - No UI changes needed; it will display returned values.
7. **Testing**
   - Add unit tests for fetchers with mocked API responses.
   - Add a smoke test for the endpoint with stubbed metrics.

## Security & Ops
- Keep credentials in env vars or mounted secrets; never commit JSON keys.
- Cache responses to limit API calls.
- Add basic error handling; on failure, return cached stale data or `n/a` with an error flag.

## Optional Enhancements
- Store daily snapshots in DB for trend charts.
- Add UTM/referrer tracking to signups if not already captured.
- Add per-article metrics (impressions/clicks per slug) for deeper reporting.
