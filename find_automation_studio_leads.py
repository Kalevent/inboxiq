#!/usr/bin/env python3
"""
Automated Lead Discovery for Automation Studio Beta.

Finds 30 companies hiring support agents (signal: they need automation)
and discovers their Head of Support/VP Customer Success for outreach.

Usage:
    python find_automation_studio_leads.py
"""
import sys
import asyncio
import csv
from pathlib import Path
from datetime import datetime

sys.path.insert(0, 'src')

# Load environment
from dotenv import load_dotenv
load_dotenv(Path('src/.env'))

from src.mcp.lead_discovery_mcp import discover_companies, find_decision_makers, find_buying_signals


async def find_target_accounts():
    """Find 30 target accounts for Automation Studio outreach."""

    print("=" * 80)
    print("🎯 Automation Studio Lead Discovery")
    print("=" * 80)
    print("\nTarget: Companies hiring support agents (need automation)")
    print("Looking for: Head of Support, VP Customer Success, CS Operations\n")

    all_leads = []

    # Step 1: Find companies showing hiring signals (they're scaling support teams)
    print("\n[1/3] Finding companies hiring support agents...")

    niches = [
        "B2B SaaS customer support",
        "E-commerce customer service",
        "Healthcare customer support",
    ]

    for niche in niches:
        try:
            result = await find_buying_signals(
                niche=niche,
                signal_type="hiring",
                max_results=10
            )

            signals = result.get("signals", [])
            print(f"  ✓ Found {len(signals)} companies in {niche}")

            for signal in signals:
                all_leads.append({
                    "company_name": signal["company_name"],
                    "domain": signal["domain"],
                    "signal": f"Hiring: {signal['title'][:50]}",
                    "url": signal["url"],
                    "niche": niche,
                })

        except Exception as e:
            print(f"  ✗ Error searching {niche}: {e}")

    print(f"\n✅ Total companies found: {len(all_leads)}")

    # Step 2: Discover more companies directly (backup method)
    if len(all_leads) < 25:
        print("\n[2/3] Discovering additional SaaS companies...")

        try:
            result = await discover_companies(
                query="customer support software SaaS",
                max_results=15
            )

            companies = result.get("companies", [])
            print(f"  ✓ Found {len(companies)} additional companies")

            for company in companies:
                all_leads.append({
                    "company_name": company["name"],
                    "domain": company["domain"],
                    "signal": "Company website",
                    "url": company["url"],
                    "niche": "SaaS",
                })

        except Exception as e:
            print(f"  ✗ Error discovering companies: {e}")

    # Step 3: Find decision makers for each company
    print(f"\n[3/3] Finding decision makers at {min(len(all_leads), 30)} companies...")

    enriched_leads = []

    for i, lead in enumerate(all_leads[:30], 1):
        domain = lead["domain"]
        company_name = lead["company_name"]

        print(f"  [{i}/30] {company_name[:30]:<30} ({domain})", end="")

        try:
            result = await find_decision_makers(
                company_domain=domain,
                job_titles=["Head of Support", "VP Customer Success", "Director of Support", "CS Operations"],
                max_results=3
            )

            contacts = result.get("contacts", [])

            if contacts:
                # Use the first contact found
                contact = contacts[0]
                enriched_leads.append({
                    **lead,
                    "contact_name": contact["name"],
                    "contact_title": contact["job_title"],
                    "linkedin_url": contact["linkedin_url"],
                })
                print(f" ✓ {contact['name']}")
            else:
                # No contact found, but save the company anyway
                enriched_leads.append({
                    **lead,
                    "contact_name": "Not found",
                    "contact_title": "",
                    "linkedin_url": "",
                })
                print(" ⚠ No contact found")

        except Exception as e:
            print(f" ✗ Error: {e}")
            # Add company without contact info
            enriched_leads.append({
                **lead,
                "contact_name": "Error",
                "contact_title": "",
                "linkedin_url": "",
            })

    # Step 4: Save to CSV
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_file = f"automation_studio_leads_{timestamp}.csv"

    print(f"\n📊 Saving {len(enriched_leads)} leads to {csv_file}...")

    with open(csv_file, 'w', newline='') as f:
        fieldnames = [
            "company_name", "domain", "contact_name", "contact_title",
            "linkedin_url", "signal", "url", "niche"
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)

        writer.writeheader()
        writer.writerows(enriched_leads)

    print(f"✅ Done! Leads saved to {csv_file}")

    # Summary
    print("\n" + "=" * 80)
    print("📈 SUMMARY")
    print("=" * 80)
    print(f"Total leads discovered: {len(enriched_leads)}")
    print(f"Leads with contact info: {sum(1 for l in enriched_leads if l['contact_name'] not in ['Not found', 'Error'])}")
    print(f"Companies hiring support: {sum(1 for l in enriched_leads if 'Hiring' in l['signal'])}")
    print("\n🚀 Next Steps:")
    print("1. Open the CSV file and review the leads")
    print("2. Find email addresses using Hunter.io or LinkedIn")
    print("3. Send personalized outreach emails (use template from earlier)")
    print("4. Target: 10 waitlist signups this week!")
    print("=" * 80 + "\n")

    return enriched_leads


if __name__ == "__main__":
    leads = asyncio.run(find_target_accounts())

    if len(leads) >= 25:
        print("✅ SUCCESS: Found 25+ leads ready for outreach")
        sys.exit(0)
    else:
        print(f"⚠️  WARNING: Only found {len(leads)} leads (target: 30)")
        print("You can still proceed with outreach, or run the script again")
        sys.exit(0)
