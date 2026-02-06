"""
Buying Intent DSPy Module

Identifies buying stage and detects signals that indicate active evaluation.
Outputs buying stage classification and recommended sales actions.

Training data: Leads who converted vs leads who stalled, with engagement patterns.
"""
import dspy
from typing import Optional


class BuyingIntentSignature(dspy.Signature):
    """Classify buying intent and identify evaluation stage."""

    # Input fields
    lead_name = dspy.InputField(desc="Lead name")
    company_name = dspy.InputField(desc="Company name")
    fit_score = dspy.InputField(desc="ICP fit score (0-10)")
    intent_score = dspy.InputField(desc="Interest intent score (0-12)")

    # Recent engagement patterns
    recent_engagement = dspy.InputField(desc="""JSON array of recent (last 14 days) engagement:
    [
      {"type": "pricing_page_view", "count": 3, "last_seen": "2026-02-04"},
      {"type": "demo_page_view", "count": 1, "last_seen": "2026-02-03"},
      {"type": "competitor_comparison", "count": 2, "last_seen": "2026-02-02"},
      {"type": "case_study_download", "count": 1, "last_seen": "2026-02-01"}
    ]""")

    days_in_funnel = dspy.InputField(desc="Total days in funnel (int)")
    buying_committee = dspy.InputField(desc="JSON array of identified committee members with roles (optional)")

    # Output fields
    buying_stage = dspy.OutputField(desc="Current stage: awareness | consideration | evaluation | decision | purchase")
    buying_intent_level = dspy.OutputField(desc="Intent level: low | medium | high | very_high")
    reasoning = dspy.OutputField(desc="2-3 sentence explanation of buying signals and stage classification")
    recommended_action = dspy.OutputField(desc="Next sales action: nurture | offer_demo | send_proposal | pricing_discussion | close_deal")
    objections_detected = dspy.OutputField(desc="JSON array of potential objections detected from behavior: e.g., ['price_concern', 'competitor_evaluation', 'internal_approval']")
    recommended_assets = dspy.OutputField(desc="JSON array of content assets to send: e.g., ['pricing_sheet', 'case_study', 'roi_calculator', 'implementation_guide']")
    urgency_level = dspy.OutputField(desc="Deal urgency: low | medium | high | critical")
    conversion_blockers = dspy.OutputField(desc="JSON array of potential blockers: e.g., ['multiple_stakeholders', 'budget_constraints', 'competing_priorities']")


class BuyingIntentModule(dspy.Module):
    """DSPy module for buying intent classification."""

    def __init__(self):
        super().__init__()
        self.classify = dspy.ChainOfThought(BuyingIntentSignature)

    def forward(
        self,
        lead_name: str,
        company_name: str,
        fit_score: int,
        intent_score: int,
        recent_engagement: str,  # JSON string
        days_in_funnel: int,
        buying_committee: Optional[str] = None
    ):
        """
        Classify buying intent and determine sales readiness.

        Args:
            lead_name: Lead name
            company_name: Company name
            fit_score: ICP fit score (0-10)
            intent_score: Interest score (0-12)
            recent_engagement: JSON array of recent engagement events
            days_in_funnel: Total days in funnel
            buying_committee: JSON array of committee members (optional)

        Returns:
            dspy.Prediction with buying_stage, buying_intent_level, reasoning, etc.
        """
        return self.classify(
            lead_name=lead_name,
            company_name=company_name,
            fit_score=str(fit_score),
            intent_score=str(intent_score),
            recent_engagement=recent_engagement,
            days_in_funnel=str(days_in_funnel),
            buying_committee=buying_committee or "[]"
        )


# Example usage for testing
if __name__ == "__main__":
    import dspy
    import json

    # Configure DSPy
    lm = dspy.OpenAI(model="gpt-4", max_tokens=600)
    dspy.settings.configure(lm=lm)

    # Initialize module
    module = BuyingIntentModule()

    # Test buying intent classification
    recent_engagement = json.dumps([
        {"type": "pricing_page_view", "count": 3, "last_seen": "2026-02-04"},
        {"type": "demo_page_view", "count": 2, "last_seen": "2026-02-03"},
        {"type": "case_study_download", "count": 1, "last_seen": "2026-02-02"},
        {"type": "roi_calculator_use", "count": 1, "last_seen": "2026-02-04"}
    ])

    buying_committee = json.dumps([
        {"name": "Jane Doe", "title": "VP Sales", "role": "economic_buyer"},
        {"name": "John Smith", "title": "Director RevOps", "role": "technical_buyer"}
    ])

    result = module(
        lead_name="Jane Doe",
        company_name="Acme Corp",
        fit_score=8,
        intent_score=10,
        recent_engagement=recent_engagement,
        days_in_funnel=21,
        buying_committee=buying_committee
    )

    print(f"Buying Stage: {result.buying_stage}")
    print(f"Buying Intent Level: {result.buying_intent_level}")
    print(f"Reasoning: {result.reasoning}")
    print(f"Recommended Action: {result.recommended_action}")
    print(f"Objections Detected: {result.objections_detected}")
    print(f"Recommended Assets: {result.recommended_assets}")
    print(f"Urgency Level: {result.urgency_level}")
    print(f"Conversion Blockers: {result.conversion_blockers}")
