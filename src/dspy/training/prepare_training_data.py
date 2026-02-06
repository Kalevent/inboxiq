"""
DSPy Training Data Preparation

Exports historical data from database for DSPy module training.
Creates labeled datasets for each funnel module.

Usage:
    python -m src.dspy.training.prepare_training_data --module visitor_qualification
    python -m src.dspy.training.prepare_training_data --module all
"""
import os
import sys
import json
import argparse
from datetime import datetime, timedelta
from typing import List, Dict, Any

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..'))

from src.extensions import db
from src.models import Lead, LeadFunnelStage, LeadEngagementEvent, BlogPost


def export_visitor_qualification_data(output_dir: str) -> str:
    """
    Export training data for VisitorQualificationModule.

    Labels:
    - Positive examples: Leads that converted (reached conversion stage)
    - Negative examples: Leads that were disqualified or stalled in visits stage

    Returns path to training data file.
    """
    print("Exporting visitor qualification training data...")

    # Get qualified leads (reached at least consideration stage)
    qualified_leads = db.session.query(Lead).join(LeadFunnelStage).filter(
        LeadFunnelStage.stage.in_(['consideration', 'conversion', 'retention'])
    ).distinct().all()

    # Get disqualified leads (stuck in visits for >30 days)
    disqualified_leads = db.session.query(Lead).filter(
        Lead.current_funnel_stage == 'visits',
        Lead.stage_entered_at < datetime.now() - timedelta(days=30)
    ).limit(len(qualified_leads)).all()  # Balance dataset

    training_data = []

    # Positive examples (qualified = high fit score)
    for lead in qualified_leads:
        training_data.append({
            "company_name": lead.company_name or "Unknown",
            "company_domain": lead.email.split('@')[1] if lead.email else "unknown.com",
            "industry": lead.industry or "Unknown",
            "employee_count": str(lead.num_employees) if lead.num_employees else "Unknown",
            "location": "Unknown",
            "contact_title": "Unknown",
            "source": lead.source or "Unknown",
            "icp_criteria": json.dumps({
                "target_industries": ["SaaS", "Technology", "Financial Services"],
                "min_employees": 50,
                "max_employees": 5000,
                "target_locations": ["US", "CA", "UK", "EU"],
                "target_titles": ["VP", "Director", "Head", "C-level"],
                "disqualifiers": ["agency", "consultancy"]
            }),
            # Labels
            "fit_score": str(lead.fit_score or 8),  # Assume high fit for qualified leads
            "qualification_status": "qualified",
            "reasoning": f"Lead converted to {lead.current_funnel_stage} stage"
        })

    # Negative examples (disqualified = low fit score)
    for lead in disqualified_leads:
        training_data.append({
            "company_name": lead.company_name or "Unknown",
            "company_domain": lead.email.split('@')[1] if lead.email else "unknown.com",
            "industry": lead.industry or "Unknown",
            "employee_count": str(lead.num_employees) if lead.num_employees else "Unknown",
            "location": "Unknown",
            "contact_title": "Unknown",
            "source": lead.source or "Unknown",
            "icp_criteria": json.dumps({
                "target_industries": ["SaaS", "Technology", "Financial Services"],
                "min_employees": 50,
                "max_employees": 5000,
                "target_locations": ["US", "CA", "UK", "EU"],
                "target_titles": ["VP", "Director", "Head", "C-level"],
                "disqualifiers": ["agency", "consultancy"]
            }),
            # Labels
            "fit_score": str(lead.fit_score or 3),  # Assume low fit for stalled leads
            "qualification_status": "disqualified",
            "reasoning": f"Lead stalled in visits stage for >30 days"
        })

    output_path = os.path.join(output_dir, "visitor_qualification_training.jsonl")
    with open(output_path, 'w') as f:
        for example in training_data:
            f.write(json.dumps(example) + '\n')

    print(f"✓ Exported {len(training_data)} examples to {output_path}")
    return output_path


def export_interest_scoring_data(output_dir: str) -> str:
    """
    Export training data for InterestScoringModule.

    Labels based on lead progression through funnel stages.
    """
    print("Exporting interest scoring training data...")

    # Get leads with engagement data
    leads = db.session.query(Lead).filter(
        Lead.engagement_count > 0
    ).limit(500).all()

    training_data = []

    for lead in leads:
        # Get engagement events
        events = db.session.query(LeadEngagementEvent).filter(
            LeadEngagementEvent.lead_id == lead.id
        ).order_by(LeadEngagementEvent.created_at.desc()).limit(50).all()

        engagement_json = json.dumps([{
            "type": e.event_type,
            "timestamp": e.created_at.isoformat()
        } for e in events])

        days_since_first = (datetime.now() - lead.created_at).days if lead.created_at else 0

        # Determine intent score based on stage reached
        stage_to_intent = {
            'visits': 2,
            'discovery': 5,
            'consideration': 8,
            'conversion': 11,
            'retention': 12
        }
        intent_score = stage_to_intent.get(lead.current_funnel_stage, 0)

        training_data.append({
            "lead_name": lead.name,
            "company_name": lead.company_name or "Unknown",
            "fit_score": str(lead.fit_score or 5),
            "engagement_events": engagement_json,
            "days_since_first_touch": str(days_since_first),
            "total_engagement_count": str(lead.engagement_count),
            # Labels
            "intent_score": str(intent_score),
            "interest_level": "hot" if intent_score >= 8 else "warm" if intent_score >= 5 else "cold",
            "reasoning": f"Lead reached {lead.current_funnel_stage} with {lead.engagement_count} engagements"
        })

    output_path = os.path.join(output_dir, "interest_scoring_training.jsonl")
    with open(output_path, 'w') as f:
        for example in training_data:
            f.write(json.dumps(example) + '\n')

    print(f"✓ Exported {len(training_data)} examples to {output_path}")
    return output_path


def export_content_topic_data(output_dir: str) -> str:
    """
    Export training data for TopicGeneratorModule.

    Labels: Published blog posts with known traffic/performance.
    """
    print("Exporting topic generation training data...")

    # Get published blog posts
    posts = db.session.query(BlogPost).filter(
        BlogPost.status == 'published',
        BlogPost.published_at.isnot(None)
    ).limit(200).all()

    training_data = []

    for post in posts:
        # Simulate topic generation input/output
        training_data.append({
            "blog_niche": "Revenue Operations",
            "target_audience": "VP Revenue Operations, B2B SaaS, 100-500 employees",
            "num_topics": "1",
            "existing_topics": "[]",
            "search_trends": "[]",
            # Labels (output)
            "topics": json.dumps([{
                "title": post.title,
                "angle": "practical_guide",
                "search_intent": "commercial_investigation",
                "target_keyword": post.primary_keyword or "revenue operations",
                "secondary_keywords": post.secondary_keywords or [],
                "estimated_difficulty": 50,
                "estimated_monthly_searches": 1000,
                "target_stage": post.funnel_stage or "discovery"
            }]),
            "reasoning": f"Based on published post: {post.title}"
        })

    output_path = os.path.join(output_dir, "topic_generator_training.jsonl")
    with open(output_path, 'w') as f:
        for example in training_data:
            f.write(json.dumps(example) + '\n')

    print(f"✓ Exported {len(training_data)} examples to {output_path}")
    return output_path


def prepare_all_training_data(output_dir: str = "./training_data"):
    """
    Prepare training data for all DSPy modules.

    Args:
        output_dir: Directory to save training data files
    """
    os.makedirs(output_dir, exist_ok=True)

    print("\n" + "="*60)
    print("DSPy Training Data Preparation")
    print("="*60 + "\n")

    # Export data for each module
    files = []

    try:
        files.append(export_visitor_qualification_data(output_dir))
    except Exception as e:
        print(f"✗ Failed to export visitor qualification data: {e}")

    try:
        files.append(export_interest_scoring_data(output_dir))
    except Exception as e:
        print(f"✗ Failed to export interest scoring data: {e}")

    try:
        files.append(export_content_topic_data(output_dir))
    except Exception as e:
        print(f"✗ Failed to export content topic data: {e}")

    print("\n" + "="*60)
    print(f"Training data preparation complete!")
    print(f"Files saved to: {output_dir}")
    print("="*60 + "\n")

    return files


def main():
    parser = argparse.ArgumentParser(description='Prepare DSPy training data')
    parser.add_argument('--module', type=str, default='all',
                       help='Module to prepare data for (visitor_qualification, interest_scoring, content_topic, or all)')
    parser.add_argument('--output-dir', type=str, default='./training_data',
                       help='Output directory for training data')

    args = parser.parse_args()

    # Initialize Flask app context
    from src.app import create_app
    app = create_app()

    with app.app_context():
        if args.module == 'all':
            prepare_all_training_data(args.output_dir)
        elif args.module == 'visitor_qualification':
            export_visitor_qualification_data(args.output_dir)
        elif args.module == 'interest_scoring':
            export_interest_scoring_data(args.output_dir)
        elif args.module == 'content_topic':
            export_content_topic_data(args.output_dir)
        else:
            print(f"Unknown module: {args.module}")
            sys.exit(1)


if __name__ == "__main__":
    main()
