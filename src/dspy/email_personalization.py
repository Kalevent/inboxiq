"""
Vertical-specific email personalization for InboxIQ nurture campaigns.

Priority order (per product decision):
  1. B2B SaaS — primary target, no API dependency
  2. E-commerce — secondary target, no API dependency
  3. Healthcare — deferred until FHIR API integration is complete

This module:
- Infers vertical from lead data when industry is not set
- Provides vertical-specific pain points, case studies, and CTAs
- Generates fully personalized emails via DSPy ChainOfThought
"""
from __future__ import annotations

import logging
from typing import Optional

import dspy

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Vertical messaging playbooks
# B2B SaaS and E-commerce prioritized per product decision.
# Healthcare is excluded until FHIR API integration is complete.
# ---------------------------------------------------------------------------

VERTICAL_PLAYBOOKS = {
    "b2b_saas": {
        "label": "B2B SaaS",
        "pain_points": [
            "Support volume scales faster than the team",
            "First-response time hurts trial-to-paid conversion",
            "Agents waste time on repetitive questions that should be automated",
            "Support tickets are routed to the wrong team or person",
            "No single view of the customer across email, chat, and CRM",
        ],
        "value_props": [
            "Reduce first-response time by 60% with AI triage",
            "Auto-handle repetitive questions — free agents for complex issues",
            "Route every ticket to the right person, every time",
            "Unified inbox across email, chat, and CRM context",
        ],
        "case_study_hook": (
            "A B2B SaaS team of 5 support agents was handling 800 tickets/week manually. "
            "After InboxIQ, 40% of tickets were auto-resolved and average response time "
            "dropped from 6 hours to 45 minutes."
        ),
        "cta_demo": "Book a 20-min demo — we'll show your exact ticket volume handled",
        "cta_trial": "Start your 7-day free trial — no credit card required",
    },
    "ecommerce": {
        "label": "E-commerce / DTC",
        "pain_points": [
            "Post-purchase complaints spike after every promotion",
            "Returns and refund requests handled manually at high cost",
            "Shipping dispute resolution takes days and frustrates customers",
            "Support team overwhelmed during peak seasons (BFCM, holiday)",
            "No visibility into support volume until it's already a problem",
        ],
        "value_props": [
            "Auto-handle returns, refund requests, and shipping disputes",
            "Survive peak seasons without hiring temporary agents",
            "Classify and prioritize every post-purchase complaint instantly",
            "Reduce support cost-per-ticket by up to 50%",
        ],
        "case_study_hook": (
            "A DTC brand with 10,000 monthly orders was spending 30 hours/week on "
            "post-purchase support. InboxIQ auto-resolved 55% of returns and shipping "
            "disputes, cutting support cost by £4,200/month."
        ),
        "cta_demo": "See a live demo with your order volume — takes 15 minutes",
        "cta_trial": "Try InboxIQ free for 7 days — set up in under 30 minutes",
    },
}

# Keywords used to infer vertical from company/domain/role when industry is unset
_B2B_SAAS_SIGNALS = [
    "saas", "software", "platform", "tech", "cloud", "api", "dev", "app",
    "analytics", "crm", "erp", "hr", "payroll", "fintech", "proptech",
    "martech", "automation", "workflow", "integration",
]
_ECOMMERCE_SIGNALS = [
    "shop", "store", "brand", "retail", "commerce", "goods", "dtc", "direct",
    "products", "fashion", "apparel", "beauty", "health", "food", "drink",
    "fulfilment", "fulfillment", "logistics", "ecommerce", "woo", "shopify",
]


def infer_vertical(industry: Optional[str], company_name: Optional[str], email: Optional[str]) -> str:
    """
    Infer vertical from available lead data.
    Returns 'b2b_saas', 'ecommerce', or 'generic'.
    """
    text = " ".join(filter(None, [
        (industry or "").lower(),
        (company_name or "").lower(),
        (email or "").lower().split("@")[-1].split(".")[0],  # domain prefix
    ]))

    saas_score = sum(1 for kw in _B2B_SAAS_SIGNALS if kw in text)
    ecom_score = sum(1 for kw in _ECOMMERCE_SIGNALS if kw in text)

    if saas_score > ecom_score and saas_score > 0:
        return "b2b_saas"
    if ecom_score > saas_score and ecom_score > 0:
        return "ecommerce"

    # Fall back to explicit industry string matching
    ind = (industry or "").lower()
    if any(k in ind for k in ["saas", "software", "tech", "b2b"]):
        return "b2b_saas"
    if any(k in ind for k in ["ecommerce", "e-commerce", "retail", "dtc", "shop"]):
        return "ecommerce"

    # Default to B2B SaaS as the primary target segment
    return "b2b_saas"


# ---------------------------------------------------------------------------
# DSPy Signatures
# ---------------------------------------------------------------------------

class VerticalEmailSignature(dspy.Signature):
    """
    Generate a highly personalized nurture email for a specific vertical.

    Use the vertical playbook context to write copy that speaks directly
    to the lead's known pain points and situation.
    """
    lead_first_name: str = dspy.InputField(desc="Lead's first name or 'there' if unknown")
    company_name: str = dspy.InputField(desc="Lead's company name")
    vertical_label: str = dspy.InputField(desc="Industry vertical label (B2B SaaS, E-commerce / DTC)")
    pain_points: str = dspy.InputField(desc="Comma-separated list of vertical pain points most relevant to this lead")
    value_props: str = dspy.InputField(desc="Comma-separated value propositions tailored to vertical")
    case_study_hook: str = dspy.InputField(desc="One-sentence case study hook showing real results")
    cta_text: str = dspy.InputField(desc="Call-to-action text")
    funnel_stage: str = dspy.InputField(desc="Funnel stage: DISCOVERY or CONSIDERATION")
    sequence_day: str = dspy.InputField(desc="Day in nurture sequence: 1, 3, 7, 14, or 21")
    extra_context: str = dspy.InputField(desc="Any extra known context: role, company size, engagement history")

    subject_line: str = dspy.OutputField(desc="Email subject line, 45-65 chars, no clickbait. Personalize with name or company.")
    email_body_html: str = dspy.OutputField(desc="Email body as HTML. 3-5 short paragraphs. No unsubscribe link needed (handled by platform).")
    preview_text: str = dspy.OutputField(desc="Email preview text shown in inbox (50-90 chars)")


class PersonalizedEmailModule(dspy.Module):
    """
    Generates vertical-specific personalized nurture emails.

    Priority: B2B SaaS → E-commerce. Healthcare deferred.
    """

    def __init__(self):
        super().__init__()
        self.generator = dspy.ChainOfThought(VerticalEmailSignature)

    def generate(
        self,
        lead_first_name: str,
        company_name: str,
        industry: Optional[str],
        email: Optional[str],
        funnel_stage: str,
        sequence_day: int,
        extra_context: str = "",
    ) -> dict:
        """
        Generate a personalized email for the lead.

        Args:
            lead_first_name: First name or fallback
            company_name: Company name
            industry: Lead's industry field (may be None)
            email: Lead's email address (used for vertical inference)
            funnel_stage: 'DISCOVERY' or 'CONSIDERATION'
            sequence_day: Day number in sequence (1, 3, 7, 14, 21)
            extra_context: Optional extra context string

        Returns:
            Dict with subject_line, email_body_html, preview_text, vertical
        """
        vertical_key = infer_vertical(industry, company_name, email)
        playbook = VERTICAL_PLAYBOOKS.get(vertical_key, VERTICAL_PLAYBOOKS["b2b_saas"])

        # Select most relevant pain points (first 3)
        pain_points_str = "; ".join(playbook["pain_points"][:3])
        value_props_str = "; ".join(playbook["value_props"][:3])

        # Adjust CTA by stage
        cta = playbook["cta_demo"] if funnel_stage == "CONSIDERATION" else playbook["cta_trial"]

        try:
            result = self.generator(
                lead_first_name=lead_first_name,
                company_name=company_name,
                vertical_label=playbook["label"],
                pain_points=pain_points_str,
                value_props=value_props_str,
                case_study_hook=playbook["case_study_hook"],
                cta_text=cta,
                funnel_stage=funnel_stage,
                sequence_day=str(sequence_day),
                extra_context=extra_context or "No additional context",
            )
            return {
                "subject_line": result.subject_line,
                "email_body_html": result.email_body_html,
                "preview_text": result.preview_text,
                "vertical": vertical_key,
                "playbook_label": playbook["label"],
            }
        except Exception as exc:
            logger.exception("PersonalizedEmailModule.generate failed: %s", exc)
            # Return a safe fallback so the nurture task doesn't crash
            return {
                "subject_line": f"Quick question for {company_name}",
                "email_body_html": (
                    f"<p>Hi {lead_first_name},</p>"
                    f"<p>We help teams like {company_name} handle support at scale. "
                    "Would a quick 15-minute call be useful?</p>"
                    "<p>Best,<br>Team InboxIQ</p>"
                ),
                "preview_text": "A quick note from InboxIQ",
                "vertical": vertical_key,
                "playbook_label": playbook["label"],
            }
