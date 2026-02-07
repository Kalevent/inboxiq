#!/usr/bin/env python3
"""
Simple Lead Discovery for Automation Studio (No MCP dependencies).

Finds companies hiring support agents using direct web search.
"""
import os
import sys
import csv
import requests
from datetime import datetime
from urllib.parse import quote
from pathlib import Path

sys.path.insert(0, 'src')

# Load environment
from dotenv import load_dotenv
load_dotenv(Path('src/.env'))


def search_web(query, max_results=10):
    """Search using SearXNG."""
    searxng_url = os.getenv("SEARXNG_URL", "https://ranger-search.kalevent.com")

    try:
        url = f"{searxng_url}/search?q={quote(query)}&format=json"
        response = requests.get(url, timeout=30)

        if response.status_code == 200:
            data = response.json()
            return data.get("results", [])[:max_results]
        else:
            print(f"  ✗ Search failed with status {response.status_code}")
            return []
    except Exception as e:
        print(f"  ✗ Search error: {e}")
        return []


def extract_domain(url):
    """Extract domain from URL."""
    from urllib.parse import urlparse
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path
        domain = domain.replace('www.', '')
        return domain
    except:
        return url


def find_hiring_companies():
    """Find companies hiring support agents."""
    print("=" * 80)
    print("🎯 Finding Companies Hiring Support Agents")
    print("=" * 80)

    companies = []

    # Search queries for companies hiring support
    queries = [
        'site:linkedin.com/jobs "customer support" OR "support agent"',
        'site:greenhouse.io "customer support representative"',
        '"customer success" OR "support agent" hiring',
    ]

    for i, query in enumerate(queries, 1):
        print(f"\n[{i}/{len(queries)}] Searching: {query[:60]}...")

        results = search_web(query, max_results=10)

        for result in results:
            url = result.get("url", "")
            domain = extract_domain(url)

            # Skip job board domains, extract the company
            if any(skip in domain for skip in ["linkedin.com", "greenhouse.io", "indeed.com"]):
                # Extract company name from title
                title = result.get("title", "")
                if " - " in title:
                    company_name = title.split(" - ")[0].strip()
                elif " at " in title:
                    company_name = title.split(" at ")[-1].strip()
                else:
                    company_name = "Unknown"

                companies.append({
                    "company_name": company_name,
                    "signal": f"Hiring: {title[:50]}",
                    "url": url,
                    "domain": "linkedin.com",  # Placeholder
                    "contact_name": "Find on LinkedIn",
                    "contact_title": "Head of Support",
                    "linkedin_url": "",
                })
            else:
                companies.append({
                    "company_name": result.get("title", "")[:30],
                    "domain": domain,
                    "signal": "Company website",
                    "url": url,
                    "contact_name": "Find via LinkedIn",
                    "contact_title": "Head of Support",
                    "linkedin_url": "",
                })

        print(f"  ✓ Found {len(results)} results")

    # Remove duplicates by company name
    seen = set()
    unique_companies = []
    for company in companies:
        name = company["company_name"].lower()
        if name not in seen and len(name) > 2:
            seen.add(name)
            unique_companies.append(company)

    return unique_companies[:30]


def save_to_csv(companies):
    """Save leads to CSV."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_file = f"automation_studio_leads_{timestamp}.csv"

    print(f"\n📊 Saving {len(companies)} leads to {csv_file}...")

    with open(csv_file, 'w', newline='') as f:
        fieldnames = [
            "company_name", "domain", "contact_name", "contact_title",
            "linkedin_url", "signal", "url"
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)

        writer.writeheader()
        writer.writerows(companies)

    print(f"✅ Done! Leads saved to {csv_file}")
    return csv_file


def main():
    """Main function."""
    # Check if SearXNG is configured
    searxng_url = os.getenv("SEARXNG_URL")
    if not searxng_url:
        print("❌ Error: SEARXNG_URL not configured in src/.env")
        print("Set it to: https://ranger-search.kalevent.com")
        sys.exit(1)

    print(f"Using SearXNG: {searxng_url}\n")

    # Find companies
    companies = find_hiring_companies()

    if not companies:
        print("\n⚠️  No companies found. This could be because:")
        print("1. SearXNG is not accessible from your network")
        print("2. Search queries need adjustment")
        print("3. Try running from a different network or VPN")
        sys.exit(1)

    # Save to CSV
    csv_file = save_to_csv(companies)

    # Summary
    print("\n" + "=" * 80)
    print("📈 SUMMARY")
    print("=" * 80)
    print(f"Total leads found: {len(companies)}")
    print(f"CSV file: {csv_file}")
    print("\n🚀 Next Steps:")
    print("1. Open the CSV and review companies")
    print("2. Search LinkedIn for: '[Company Name] Head of Support'")
    print("3. Use Hunter.io to find email addresses")
    print("4. Send personalized outreach emails")
    print("5. Target: 10 waitlist signups this week!")
    print("=" * 80 + "\n")

    return len(companies)


if __name__ == "__main__":
    try:
        count = main()
        sys.exit(0 if count >= 10 else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
