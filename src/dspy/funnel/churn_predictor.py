"""
Churn Predictor DSPy Module

Predicts churn risk for customers in retention stage.
Outputs churn probability (0-1) and recommended retention actions.

Training data: Historical churned vs retained customers with engagement patterns.
"""
import dspy


class ChurnPredictorSignature(dspy.Signature):
    """Predict customer churn risk and recommend retention actions."""

    # Input fields
    lead_name = dspy.InputField(desc="Customer name")
    company_name = dspy.InputField(desc="Company name")
    days_since_conversion = dspy.InputField(desc="Days since became customer (int)")

    # Product usage signals
    product_usage = dspy.InputField(desc="""JSON object with usage metrics:
    {
      "last_login_days_ago": 14,
      "monthly_active_days": 8,
      "features_used": 3,
      "total_features": 10,
      "support_tickets_open": 2,
      "support_tickets_resolved": 5,
      "nps_score": 7,
      "adoption_rate": 0.3
    }""")

    # Engagement trends
    engagement_trend = dspy.InputField(desc="Recent engagement trend: increasing | stable | declining | stalled")
    recent_engagement_count = dspy.InputField(desc="Engagements in last 30 days (int)")
    last_engagement_days_ago = dspy.InputField(desc="Days since last engagement (int)")

    # Account health indicators
    contract_renewal_days = dspy.InputField(desc="Days until contract renewal (int, or 'unknown')")
    expansion_opportunities = dspy.InputField(desc="Boolean: has expansion opportunities (true/false)")
    negative_sentiment_detected = dspy.InputField(desc="Boolean: negative sentiment in support tickets (true/false)")

    # Output fields
    churn_probability = dspy.OutputField(desc="Probability of churn (0.0 to 1.0, e.g., 0.65 for 65% risk)")
    churn_risk_level = dspy.OutputField(desc="Risk level: low | medium | high | critical")
    reasoning = dspy.OutputField(desc="2-3 sentence explanation of churn risk and key warning signs")
    recommended_action = dspy.OutputField(desc="Retention action: check_in_call | feature_training | success_plan | executive_escalation | win_back_offer | no_action")
    churn_indicators = dspy.OutputField(desc="JSON array of churn signals: e.g., ['low_usage', 'support_issues', 'negative_sentiment', 'renewal_approaching']")
    retention_opportunities = dspy.OutputField(desc="JSON array of retention levers: e.g., ['upsell_feature_X', 'discount_offer', 'training_program', 'executive_sponsor']")
    urgency_level = dspy.OutputField(desc="Intervention urgency: low | medium | high | immediate")
    estimated_churn_days = dspy.OutputField(desc="Estimated days until churn (int, or 'unknown')")


class ChurnPredictorModule(dspy.Module):
    """DSPy module for churn prediction."""

    def __init__(self):
        super().__init__()
        self.predict = dspy.ChainOfThought(ChurnPredictorSignature)

    def forward(
        self,
        lead_name: str,
        company_name: str,
        days_since_conversion: int,
        product_usage: str,  # JSON string
        engagement_trend: str,
        recent_engagement_count: int,
        last_engagement_days_ago: int,
        contract_renewal_days: int,
        expansion_opportunities: bool,
        negative_sentiment_detected: bool
    ):
        """
        Predict customer churn risk.

        Args:
            lead_name: Customer name
            company_name: Company name
            days_since_conversion: Days since conversion
            product_usage: JSON with usage metrics
            engagement_trend: Engagement trend
            recent_engagement_count: Recent engagements
            last_engagement_days_ago: Days since last engagement
            contract_renewal_days: Days until renewal
            expansion_opportunities: Expansion flag
            negative_sentiment_detected: Negative sentiment flag

        Returns:
            dspy.Prediction with churn_probability, risk_level, reasoning, etc.
        """
        return self.predict(
            lead_name=lead_name,
            company_name=company_name,
            days_since_conversion=str(days_since_conversion),
            product_usage=product_usage,
            engagement_trend=engagement_trend,
            recent_engagement_count=str(recent_engagement_count),
            last_engagement_days_ago=str(last_engagement_days_ago),
            contract_renewal_days=str(contract_renewal_days),
            expansion_opportunities=str(expansion_opportunities).lower(),
            negative_sentiment_detected=str(negative_sentiment_detected).lower()
        )


# Example usage for testing
if __name__ == "__main__":
    import dspy
    import json

    # Configure DSPy
    lm = dspy.OpenAI(model="gpt-4", max_tokens=600)
    dspy.settings.configure(lm=lm)

    # Initialize module
    module = ChurnPredictorModule()

    # Test churn prediction
    product_usage = json.dumps({
        "last_login_days_ago": 21,
        "monthly_active_days": 4,
        "features_used": 2,
        "total_features": 10,
        "support_tickets_open": 3,
        "support_tickets_resolved": 2,
        "nps_score": 4,
        "adoption_rate": 0.2
    })

    result = module(
        lead_name="Jane Doe",
        company_name="Acme Corp",
        days_since_conversion=120,
        product_usage=product_usage,
        engagement_trend="declining",
        recent_engagement_count=2,
        last_engagement_days_ago=21,
        contract_renewal_days=45,
        expansion_opportunities=False,
        negative_sentiment_detected=True
    )

    print(f"Churn Probability: {result.churn_probability}")
    print(f"Churn Risk Level: {result.churn_risk_level}")
    print(f"Reasoning: {result.reasoning}")
    print(f"Recommended Action: {result.recommended_action}")
    print(f"Churn Indicators: {result.churn_indicators}")
    print(f"Retention Opportunities: {result.retention_opportunities}")
    print(f"Urgency Level: {result.urgency_level}")
    print(f"Estimated Churn Days: {result.estimated_churn_days}")
