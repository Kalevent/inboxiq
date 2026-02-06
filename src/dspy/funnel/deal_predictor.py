"""
Deal Predictor DSPy Module

Predicts conversion probability and estimates deal close timeline.
Outputs conversion probability (0-1) and expected close date.

Training data: Historical deals (closed-won + closed-lost) with full engagement history.
"""
import dspy
from typing import Optional


class DealPredictorSignature(dspy.Signature):
    """Predict deal conversion probability and close timeline."""

    # Input fields
    lead_name = dspy.InputField(desc="Lead name")
    company_name = dspy.InputField(desc="Company name")
    fit_score = dspy.InputField(desc="ICP fit score (0-10)")
    intent_score = dspy.InputField(desc="Interest intent score (0-12)")
    buying_stage = dspy.InputField(desc="Current buying stage: awareness | consideration | evaluation | decision | purchase")

    # Historical engagement data
    total_engagements = dspy.InputField(desc="Total number of engagements (int)")
    days_in_funnel = dspy.InputField(desc="Total days in funnel (int)")
    touchpoints = dspy.InputField(desc="Number of unique touchpoints/channels (int)")
    demo_completed = dspy.InputField(desc="Boolean: has completed demo call (true/false)")
    proposal_sent = dspy.InputField(desc="Boolean: has received proposal (true/false)")
    pricing_discussed = dspy.InputField(desc="Boolean: has discussed pricing (true/false)")

    # Company context
    company_size = dspy.InputField(desc="Company size in employees (int or 'unknown')")
    buying_committee_size = dspy.InputField(desc="Number of known buying committee members (int)")
    competitor_evaluation = dspy.InputField(desc="Boolean: known to be evaluating competitors (true/false)")

    # Output fields
    conversion_probability = dspy.OutputField(desc="Probability of conversion (0.0 to 1.0, e.g., 0.75 for 75%)")
    confidence_level = dspy.OutputField(desc="Prediction confidence: low | medium | high | very_high")
    reasoning = dspy.OutputField(desc="2-3 sentence explanation of probability score and key factors")
    estimated_close_days = dspy.OutputField(desc="Estimated days until close (int, or 'unknown' if too early)")
    deal_stage_prediction = dspy.OutputField(desc="Predicted next stage: qualified | demo | proposal | negotiation | closed_won | closed_lost")
    win_factors = dspy.OutputField(desc="JSON array of positive factors: e.g., ['strong_engagement', 'senior_buyer', 'budget_confirmed']")
    risk_factors = dspy.OutputField(desc="JSON array of risk factors: e.g., ['long_sales_cycle', 'competitor_engaged', 'low_engagement']")
    recommended_push = dspy.OutputField(desc="Recommended action to accelerate close: urgency_trigger | discount_offer | executive_engagement | none")


class DealPredictorModule(dspy.Module):
    """DSPy module for deal conversion prediction."""

    def __init__(self):
        super().__init__()
        self.predict = dspy.ChainOfThought(DealPredictorSignature)

    def forward(
        self,
        lead_name: str,
        company_name: str,
        fit_score: int,
        intent_score: int,
        buying_stage: str,
        total_engagements: int,
        days_in_funnel: int,
        touchpoints: int,
        demo_completed: bool,
        proposal_sent: bool,
        pricing_discussed: bool,
        company_size: int,
        buying_committee_size: int,
        competitor_evaluation: bool
    ):
        """
        Predict deal conversion probability.

        Args:
            lead_name: Lead name
            company_name: Company name
            fit_score: ICP fit score (0-10)
            intent_score: Interest score (0-12)
            buying_stage: Current buying stage
            total_engagements: Total engagement count
            days_in_funnel: Days in funnel
            touchpoints: Unique touchpoints
            demo_completed: Demo completed flag
            proposal_sent: Proposal sent flag
            pricing_discussed: Pricing discussed flag
            company_size: Company size
            buying_committee_size: Committee size
            competitor_evaluation: Competitor evaluation flag

        Returns:
            dspy.Prediction with conversion_probability, reasoning, etc.
        """
        return self.predict(
            lead_name=lead_name,
            company_name=company_name,
            fit_score=str(fit_score),
            intent_score=str(intent_score),
            buying_stage=buying_stage,
            total_engagements=str(total_engagements),
            days_in_funnel=str(days_in_funnel),
            touchpoints=str(touchpoints),
            demo_completed=str(demo_completed).lower(),
            proposal_sent=str(proposal_sent).lower(),
            pricing_discussed=str(pricing_discussed).lower(),
            company_size=str(company_size),
            buying_committee_size=str(buying_committee_size),
            competitor_evaluation=str(competitor_evaluation).lower()
        )


# Example usage for testing
if __name__ == "__main__":
    import dspy

    # Configure DSPy
    lm = dspy.OpenAI(model="gpt-4", max_tokens=600)
    dspy.settings.configure(lm=lm)

    # Initialize module
    module = DealPredictorModule()

    # Test deal prediction
    result = module(
        lead_name="Jane Doe",
        company_name="Acme Corp",
        fit_score=8,
        intent_score=10,
        buying_stage="evaluation",
        total_engagements=45,
        days_in_funnel=28,
        touchpoints=5,
        demo_completed=True,
        proposal_sent=True,
        pricing_discussed=True,
        company_size=250,
        buying_committee_size=3,
        competitor_evaluation=True
    )

    print(f"Conversion Probability: {result.conversion_probability}")
    print(f"Confidence Level: {result.confidence_level}")
    print(f"Reasoning: {result.reasoning}")
    print(f"Estimated Close Days: {result.estimated_close_days}")
    print(f"Next Stage Prediction: {result.deal_stage_prediction}")
    print(f"Win Factors: {result.win_factors}")
    print(f"Risk Factors: {result.risk_factors}")
    print(f"Recommended Push: {result.recommended_push}")
