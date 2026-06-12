"""
Interest Scoring DSPy Module

Analyzes engagement signals to determine lead interest level and intent score.
Outputs intent score (0-12) and recommended nurture sequence.

Training data: Engagement patterns of converted customers vs churned leads.
"""
import dspy


class InterestScoringSignature(dspy.Signature):
    """Score lead interest based on engagement signals."""

    # Input fields
    lead_name = dspy.InputField(desc="Lead name")
    company_name = dspy.InputField(desc="Company name")
    fit_score = dspy.InputField(desc="ICP fit score from visitor qualification (0-10)")

    # Engagement data (JSON string)
    engagement_events = dspy.InputField(desc="""JSON array of engagement events:
    [
      {"type": "email_open", "timestamp": "2026-02-01T10:00:00Z"},
      {"type": "email_click", "timestamp": "2026-02-01T10:05:00Z"},
      {"type": "page_visit", "url": "/pricing", "timestamp": "2026-02-01T14:30:00Z"},
      {"type": "content_download", "asset": "whitepaper", "timestamp": "2026-02-02T09:00:00Z"}
    ]""")

    days_since_first_touch = dspy.InputField(desc="Number of days since first engagement (int)")
    total_engagement_count = dspy.InputField(desc="Total number of engagement events (int)")

    # Output fields
    intent_score = dspy.OutputField(desc="Buying intent score from 0-12 (0 = no interest, 12 = ready to buy)")
    interest_level = dspy.OutputField(desc="Category: cold | warm | hot | burning")
    reasoning = dspy.OutputField(desc="2-3 sentence explanation of interest signals and intent score")
    recommended_nurture = dspy.OutputField(desc="Next nurture action: cold_sequence | warm_sequence | hot_sequence | book_demo | send_proposal")
    engagement_quality = dspy.OutputField(desc="Quality assessment: high_quality | medium_quality | low_quality (based on signal strength)")
    key_signals = dspy.OutputField(desc="JSON array of most important signals: e.g., ['pricing_page_visit', 'demo_request', 'high_frequency']")
    velocity = dspy.OutputField(desc="Engagement velocity: accelerating | steady | declining | stalled")


class InterestScoringModule(dspy.Module):
    """DSPy module for interest scoring based on engagement patterns."""

    def __init__(self):
        super().__init__()
        self.score = dspy.ChainOfThought(InterestScoringSignature)

    def forward(
        self,
        lead_name: str,
        company_name: str,
        fit_score: int,
        engagement_events: str,  # JSON string
        days_since_first_touch: int,
        total_engagement_count: int
    ):
        """
        Score lead interest based on engagement signals.

        Args:
            lead_name: Lead name
            company_name: Company name
            fit_score: ICP fit score (0-10)
            engagement_events: JSON array of engagement events
            days_since_first_touch: Days since first touch
            total_engagement_count: Total engagement count

        Returns:
            dspy.Prediction with intent_score, interest_level, reasoning, etc.
        """
        return self.score(
            lead_name=lead_name,
            company_name=company_name,
            fit_score=str(fit_score),
            engagement_events=engagement_events,
            days_since_first_touch=str(days_since_first_touch),
            total_engagement_count=str(total_engagement_count)
        )


# Example usage for testing
if __name__ == "__main__":
    import dspy
    import json

    # Configure DSPy
    lm = dspy.OpenAI(model="gpt-4", max_tokens=500)
    dspy.settings.configure(lm=lm)

    # Initialize module
    module = InterestScoringModule()

    # Test interest scoring
    engagement_events = json.dumps([
        {"type": "email_open", "timestamp": "2026-02-01T10:00:00Z"},
        {"type": "email_click", "timestamp": "2026-02-01T10:05:00Z", "url": "https://site.com/pricing"},
        {"type": "page_visit", "url": "/pricing", "timestamp": "2026-02-01T14:30:00Z"},
        {"type": "page_visit", "url": "/demo", "timestamp": "2026-02-02T09:00:00Z"},
        {"type": "content_download", "asset": "case-study", "timestamp": "2026-02-02T09:15:00Z"}
    ])

    result = module(
        lead_name="Jane Doe",
        company_name="Acme Corp",
        fit_score=8,
        engagement_events=engagement_events,
        days_since_first_touch=5,
        total_engagement_count=12
    )

    print(f"Intent Score: {result.intent_score}")
    print(f"Interest Level: {result.interest_level}")
    print(f"Reasoning: {result.reasoning}")
    print(f"Recommended Nurture: {result.recommended_nurture}")
    print(f"Engagement Quality: {result.engagement_quality}")
    print(f"Key Signals: {result.key_signals}")
    print(f"Velocity: {result.velocity}")
