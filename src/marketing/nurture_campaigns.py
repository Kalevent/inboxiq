"""
Intelligent nurture campaign automation using DSPy.

Creates personalized nurture sequences for:
- Discovery stage: Educational content, thought leadership
- Consideration stage: Demos, ROI calculators, case studies
- Retention stage: Feature adoption, success stories

Uses DSPy to personalize content based on:
- Industry/vertical
- Company size
- Role/persona
- Engagement history
- Pain points
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional

from src.celery_inboxiq import celery
from src.extensions import db
from src.models import Lead, EmailCampaign
import dspy

logger = logging.getLogger(__name__)


class NurtureEmailGenerator(dspy.Signature):
    """
    Generate personalized nurture email content.

    Adapts messaging based on lead attributes and funnel stage.
    """
    lead_name = dspy.InputField(desc="Lead's first name")
    company_name = dspy.InputField(desc="Company name")
    industry = dspy.InputField(desc="Industry/vertical (healthcare, insurance, B2B SaaS)")
    role = dspy.InputField(desc="Lead's role/title")
    funnel_stage = dspy.InputField(desc="Current funnel stage (DISCOVERY, CONSIDERATION, CONVERSION)")
    email_sequence_day = dspy.InputField(desc="Day number in nurture sequence (1, 3, 7, 14)")
    pain_points = dspy.InputField(desc="Known pain points or interests")
    engagement_history = dspy.InputField(desc="Brief engagement summary (opened emails, visited pages)")

    subject_line = dspy.OutputField(desc="Personalized subject line (40-60 chars)")
    email_body = dspy.OutputField(desc="Email body in HTML with personalization")
    call_to_action = dspy.OutputField(desc="Primary CTA text and URL")
    personalization_angle = dspy.OutputField(desc="Why this message resonates with this lead")


class NurtureSequenceDesigner(dspy.Signature):
    """
    Design optimal nurture sequence for a lead.

    Determines timing, content themes, and channel mix.
    """
    lead_profile = dspy.InputField(desc="JSON of lead attributes (industry, role, company_size, pain_points)")
    funnel_stage = dspy.InputField(desc="Current funnel stage")
    engagement_level = dspy.InputField(desc="Engagement level: high, medium, low")
    available_content = dspy.InputField(desc="Available content types: blog, case_study, webinar, demo, calculator")

    sequence_length_days = dspy.OutputField(desc="Total sequence duration in days (7, 14, 21, 30)")
    email_days = dspy.OutputField(desc="Comma-separated list of days to send emails (e.g., '1,3,7,14')")
    content_themes = dspy.OutputField(desc="JSON array of content themes per email [{day: 1, theme: 'education'}, ...]")
    channel_mix = dspy.OutputField(desc="JSON of channel distribution {email: 70%, linkedin: 20%, retargeting: 10%}")
    reasoning = dspy.OutputField(desc="Explanation of sequence design")


class NurtureIntelligenceModule(dspy.Module):
    """
    Complete nurture campaign intelligence module.

    Combines sequence design with personalized email generation.
    """

    def __init__(self):
        super().__init__()
        self.sequence_designer = dspy.ChainOfThought(NurtureSequenceDesigner)
        self.email_generator = dspy.ChainOfThought(NurtureEmailGenerator)

    def design_nurture_sequence(
        self,
        lead: Lead,
        engagement_level: str = "medium"
    ) -> Dict[str, Any]:
        """
        Design personalized nurture sequence for a lead.

        Args:
            lead: Lead object
            engagement_level: high, medium, or low

        Returns:
            Nurture sequence design with timing and themes
        """
        # Build lead profile
        lead_profile = {
            "industry": lead.industry or "B2B SaaS",
            "company_name": lead.company_name or "their company",
            "company_size": lead.company_size or "mid-market",
            "role": lead.title or "Operations Leader",
            "pain_points": lead.pain_points or "inbox overload, manual triage"
        }

        # Determine available content
        available_content = "blog, case_study, webinar, demo, calculator, testimonials"

        # Design sequence
        sequence = self.sequence_designer(
            lead_profile=str(lead_profile),
            funnel_stage=lead.current_funnel_stage,
            engagement_level=engagement_level,
            available_content=available_content
        )

        return {
            "sequence_length_days": int(sequence.sequence_length_days),
            "email_days": [int(d.strip()) for d in sequence.email_days.split(',')],
            "content_themes": sequence.content_themes,
            "channel_mix": sequence.channel_mix,
            "reasoning": sequence.reasoning
        }

    def generate_nurture_email(
        self,
        lead: Lead,
        day_number: int,
        theme: str = "education"
    ) -> Dict[str, str]:
        """
        Generate personalized nurture email.

        Args:
            lead: Lead object
            day_number: Day in sequence (1, 3, 7, etc.)
            theme: Content theme (education, social_proof, demo_offer, etc.)

        Returns:
            Email with subject, body, CTA
        """
        # Build engagement history
        engagement_summary = f"Visited site {lead.visit_count or 0} times"
        if lead.last_page_visited:
            engagement_summary += f", last viewed: {lead.last_page_visited}"

        # Generate email
        email = self.email_generator(
            lead_name=lead.name.split()[0] if lead.name else "there",
            company_name=lead.company_name or "your company",
            industry=lead.industry or "your industry",
            role=lead.title or "your role",
            funnel_stage=lead.current_funnel_stage,
            email_sequence_day=str(day_number),
            pain_points=lead.pain_points or "inbox management challenges",
            engagement_history=engagement_summary
        )

        return {
            "subject": email.subject_line,
            "body_html": email.email_body,
            "cta": email.call_to_action,
            "personalization_angle": email.personalization_angle
        }


@celery.task(name="marketing.send_discovery_nurture")
def send_discovery_nurture(max_sends: int = 50) -> Dict[str, Any]:
    """
    Send Discovery stage nurture emails.

    Sends educational content to leads in DISCOVERY stage who:
    - Have been in stage for 2+ days
    - Haven't received a nurture email in 7 days
    - Are engaged (opened/clicked recent emails)

    Args:
        max_sends: Maximum emails to send in this run

    Returns:
        Summary of emails sent
    """
    from src.email_utils import send_email

    # Find leads ready for Discovery nurture
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    two_days_ago = datetime.now(timezone.utc) - timedelta(days=2)

    eligible_leads = db.session.query(Lead).filter(
        Lead.current_funnel_stage == "DISCOVERY",
        Lead.stage_entered_at <= two_days_ago,
        Lead.deleted == False,  # noqa: E712
        Lead.email.isnot(None)
    ).limit(max_sends).all()

    if not eligible_leads:
        return {"status": "no_eligible_leads", "sent": 0}

    # Initialize DSPy intelligence
    from src.dspy import _configure_dspy
    _configure_dspy()

    nurture_module = NurtureIntelligenceModule()

    sent_count = 0
    failed_count = 0

    for lead in eligible_leads:
        try:
            # Determine day in sequence
            # TODO: Track this in database - for now use days since stage entry
            days_in_stage = (datetime.now(timezone.utc) - lead.stage_entered_at).days

            # Map days to sequence (1, 3, 7, 14, 21)
            if days_in_stage < 3:
                day_number = 1
            elif days_in_stage < 7:
                day_number = 3
            elif days_in_stage < 14:
                day_number = 7
            elif days_in_stage < 21:
                day_number = 14
            else:
                day_number = 21

            # Generate personalized email
            email_content = nurture_module.generate_nurture_email(
                lead=lead,
                day_number=day_number,
                theme="education" if day_number <= 3 else "use_cases"
            )

            # Send email
            success = send_email(
                to_email=lead.email,
                subject=email_content["subject"],
                html_body=email_content["body_html"],
                from_email="growth@kalevent.com"
            )

            if success:
                sent_count += 1
                lead.last_email_sent_at = datetime.now(timezone.utc)
                logger.info(f"Sent Discovery nurture Day {day_number} to {lead.email}")
            else:
                failed_count += 1

        except Exception as e:
            logger.error(f"Failed to send Discovery nurture to {lead.email}: {e}")
            failed_count += 1

    db.session.commit()

    return {
        "status": "completed",
        "sent": sent_count,
        "failed": failed_count,
        "eligible_leads": len(eligible_leads)
    }


@celery.task(name="marketing.send_consideration_nurture")
def send_consideration_nurture(max_sends: int = 30) -> Dict[str, Any]:
    """
    Send Consideration stage nurture emails.

    Sends conversion-focused content to leads in CONSIDERATION:
    - Demo offers with personalized value props
    - ROI calculators
    - Industry-specific case studies
    - Customer testimonials

    Args:
        max_sends: Maximum emails to send

    Returns:
        Summary of emails sent
    """
    from src.email_utils import send_email

    # Find leads in Consideration stage
    two_days_ago = datetime.now(timezone.utc) - timedelta(days=2)

    eligible_leads = db.session.query(Lead).filter(
        Lead.current_funnel_stage == "CONSIDERATION",
        Lead.stage_entered_at <= two_days_ago,
        Lead.deleted == False,  # noqa: E712
        Lead.email.isnot(None)
    ).limit(max_sends).all()

    if not eligible_leads:
        return {"status": "no_eligible_leads", "sent": 0}

    # Initialize DSPy
    from src.dspy import _configure_dspy
    _configure_dspy()

    nurture_module = NurtureIntelligenceModule()

    sent_count = 0
    failed_count = 0

    for lead in eligible_leads:
        try:
            # Determine day in sequence
            days_in_stage = (datetime.now(timezone.utc) - lead.stage_entered_at).days

            # Consideration sequence: Demo, ROI, Case Study, Final Ask
            if days_in_stage < 3:
                day_number = 1
                theme = "demo_offer"
            elif days_in_stage < 7:
                day_number = 3
                theme = "roi_calculator"
            elif days_in_stage < 14:
                day_number = 7
                theme = "case_study"
            else:
                day_number = 14
                theme = "final_ask"

            # Generate personalized email
            email_content = nurture_module.generate_nurture_email(
                lead=lead,
                day_number=day_number,
                theme=theme
            )

            # Send email
            success = send_email(
                to_email=lead.email,
                subject=email_content["subject"],
                html_body=email_content["body_html"],
                from_email="growth@kalevent.com"
            )

            if success:
                sent_count += 1
                lead.last_email_sent_at = datetime.now(timezone.utc)
                logger.info(f"Sent Consideration nurture Day {day_number} ({theme}) to {lead.email}")
            else:
                failed_count += 1

        except Exception as e:
            logger.error(f"Failed to send Consideration nurture to {lead.email}: {e}")
            failed_count += 1

    db.session.commit()

    return {
        "status": "completed",
        "sent": sent_count,
        "failed": failed_count,
        "eligible_leads": len(eligible_leads)
    }


# Convenience functions

def create_nurture_campaign(
    name: str,
    funnel_stage: str,
    sequence_days: List[int],
    content_themes: List[str]
) -> EmailCampaign:
    """
    Create a new nurture campaign in the database.

    Args:
        name: Campaign name
        funnel_stage: Target funnel stage
        sequence_days: List of days to send (e.g., [1, 3, 7, 14])
        content_themes: Content theme per email

    Returns:
        Created EmailCampaign object
    """
    from uuid import uuid4

    campaign = EmailCampaign(
        id=str(uuid4()),
        name=name,
        description=f"Nurture sequence for {funnel_stage} stage",
        campaign_type="nurture",
        status="active",
        target_funnel_stage=funnel_stage,
        follow_up_delays_days=sequence_days[1:],  # Exclude day 0
        created_at=datetime.now(timezone.utc)
    )

    db.session.add(campaign)
    db.session.commit()

    logger.info(f"Created nurture campaign: {name} for {funnel_stage}")

    return campaign


def get_next_nurture_email_for_lead(lead_id: str) -> Optional[Dict[str, Any]]:
    """
    Determine what nurture email should be sent next for a lead.

    Args:
        lead_id: Lead UUID

    Returns:
        {
            "day_number": 3,
            "theme": "use_cases",
            "send_at": "2026-02-18T10:00:00Z"
        }
        or None if no email due
    """
    lead = db.session.get(Lead, lead_id)
    if not lead:
        return None

    days_in_stage = (datetime.now(timezone.utc) - lead.stage_entered_at).days

    # Determine next email based on stage and days
    if lead.current_funnel_stage == "DISCOVERY":
        sequence = [(1, "education"), (3, "use_cases"), (7, "thought_leadership"), (14, "community")]
    elif lead.current_funnel_stage == "CONSIDERATION":
        sequence = [(1, "demo_offer"), (3, "roi_calculator"), (7, "case_study"), (14, "final_ask")]
    else:
        return None

    # Find next email
    for day, theme in sequence:
        if days_in_stage >= day and days_in_stage < day + 2:  # 2-day send window
            return {
                "day_number": day,
                "theme": theme,
                "send_at": datetime.now(timezone.utc).isoformat()
            }

    return None
