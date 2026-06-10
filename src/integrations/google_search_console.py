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
    if os.getenv('GSC_ENABLED', '').lower() not in ('true', '1', 'yes'):
        return None

    try:
        _gsc_client = GoogleSearchConsole()
        return _gsc_client
    except (ValueError, FileNotFoundError) as e:
        print(f"GSC client initialization failed: {e}")
        return None
