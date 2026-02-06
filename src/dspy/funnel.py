"""
DSPy modules for Funnel v2.0 - 5-stage lead management

Modules:
1. VisitorQualificationModule - Qualify new visitors (Visits → Discovery)
2. InterestScoringModule - Score lead interest/engagement (Discovery → Consideration)
3. BuyingIntentModule - Assess buying signals (Consideration → Conversion)
4. DealPredictorModule - Predict deal closure likelihood
5. ChurnPredictorModule - Analyze churn risk for customers (Retention stage)
"""
import dspy


# ============================================================================
# Stage 1: Visitor Qualification (Visits → Discovery)
# ============================================================================

class VisitorQualificationSignature(dspy.Signature):
    """
    Qualify new visitors based on company fit and ICP match.

    Assess whether this visitor matches our Ideal Customer Profile (ICP)
    and should progress from passive visits to active discovery stage.
    """
    company_name = dspy.InputField(desc="Company name")
    company_domain = dspy.InputField(desc="Company domain or email domain")
    industry = dspy.InputField(desc="Industry or vertical (optional)")
    employee_count = dspy.InputField(desc="Number of employees (optional)")
    source = dspy.InputField(desc="Traffic source or referral channel")

    fit_score = dspy.OutputField(desc="ICP fit score from 1-10. Score 8-10 = excellent fit, 6-7 = good fit, 3-5 = maybe, 1-2 = poor fit")
    qualification_status = dspy.OutputField(desc="One of: qualified | nurture | disqualified")
    reasoning = dspy.OutputField(desc="Brief explanation of fit assessment and key factors")
    recommended_action = dspy.OutputField(desc="Next step: progress to discovery | continue monitoring | exclude from active outreach")


class VisitorQualificationModule(dspy.Module):
    """Qualify visitors for ICP fit."""

    def __init__(self):
        super().__init__()
        self.predict = dspy.ChainOfThought(VisitorQualificationSignature)

    def forward(self, company_name: str, company_domain: str, industry: str = None,
                employee_count: str = None, source: str = None):
        return self.predict(
            company_name=company_name,
            company_domain=company_domain,
            industry=industry or "unknown",
            employee_count=employee_count or "unknown",
            source=source or "direct"
        )


# ============================================================================
# Stage 2: Interest Scoring (Discovery → Consideration)
# ============================================================================

class InterestScoringSignature(dspy.Signature):
    """
    Score lead interest based on engagement patterns.

    Analyze behavioral signals to determine if lead is moving from
    passive discovery to active consideration of our solution.
    """
    lead_name = dspy.InputField(desc="Lead contact name")
    company_name = dspy.InputField(desc="Company name")
    fit_score = dspy.InputField(desc="ICP fit score (1-10)")
    engagement_events = dspy.InputField(desc="JSON array of recent engagement events with type and timestamp")
    days_since_first_touch = dspy.InputField(desc="Days since first interaction")
    total_engagement_count = dspy.InputField(desc="Total number of engagement touchpoints")

    intent_score = dspy.OutputField(desc="Intent/interest score from 1-10. High scores (8-10) indicate strong consideration signals")
    interest_level = dspy.OutputField(desc="One of: high | medium | low | dormant")
    reasoning = dspy.OutputField(desc="Key engagement signals and behavioral patterns observed")
    recommended_nurture = dspy.OutputField(desc="Suggested nurture strategy: accelerate outreach | continue nurturing | pause and monitor")


class InterestScoringModule(dspy.Module):
    """Score lead interest and engagement."""

    def __init__(self):
        super().__init__()
        self.predict = dspy.ChainOfThought(InterestScoringSignature)

    def forward(self, lead_name: str, company_name: str, fit_score: int,
                engagement_events: str, days_since_first_touch: int,
                total_engagement_count: int):
        return self.predict(
            lead_name=lead_name,
            company_name=company_name,
            fit_score=str(fit_score),
            engagement_events=engagement_events,
            days_since_first_touch=str(days_since_first_touch),
            total_engagement_count=str(total_engagement_count)
        )


# ============================================================================
# Stage 3: Buying Intent Assessment (Consideration → Conversion)
# ============================================================================

class BuyingIntentSignature(dspy.Signature):
    """
    Assess buying intent and readiness to purchase.

    Identify strong buying signals that indicate lead is ready to
    convert from consideration to active sales conversation.
    """
    lead_name = dspy.InputField(desc="Lead contact name")
    company_name = dspy.InputField(desc="Company name")
    intent_score = dspy.InputField(desc="Current intent score (1-10)")
    recent_signals = dspy.InputField(desc="JSON array of recent buying signals: pricing page views, demo requests, competitor research, etc.")
    engagement_velocity = dspy.InputField(desc="Recent engagement trend: increasing | stable | declining")
    stakeholder_count = dspy.InputField(desc="Number of stakeholders involved from organization")
    days_in_consideration = dspy.InputField(desc="Days spent in consideration stage")

    buying_intent = dspy.OutputField(desc="Buying intent score from 1-10. High scores (8-10) indicate imminent purchase decision")
    readiness_stage = dspy.OutputField(desc="One of: ready_to_buy | evaluating | researching | not_ready")
    key_signals = dspy.OutputField(desc="List of key buying signals observed")
    recommended_approach = dspy.OutputField(desc="Sales strategy: immediate outreach | schedule demo | send proposal | nurture further")
    risk_factors = dspy.OutputField(desc="Any concerns or red flags to address")


class BuyingIntentModule(dspy.Module):
    """Assess buying intent and conversion readiness."""

    def __init__(self):
        super().__init__()
        self.predict = dspy.ChainOfThought(BuyingIntentSignature)

    def forward(self, lead_name: str, company_name: str, intent_score: int,
                recent_signals: str, engagement_velocity: str, stakeholder_count: int,
                days_in_consideration: int):
        return self.predict(
            lead_name=lead_name,
            company_name=company_name,
            intent_score=str(intent_score),
            recent_signals=recent_signals,
            engagement_velocity=engagement_velocity,
            stakeholder_count=str(stakeholder_count),
            days_in_consideration=str(days_in_consideration)
        )


# ============================================================================
# Stage 4: Deal Prediction (Conversion stage)
# ============================================================================

class DealPredictorSignature(dspy.Signature):
    """
    Predict likelihood of deal closure.

    Analyze deal health and forecast close probability for active
    sales opportunities in the conversion stage.
    """
    lead_name = dspy.InputField(desc="Lead contact name")
    company_name = dspy.InputField(desc="Company name")
    deal_stage = dspy.InputField(desc="Current deal stage: demo_scheduled | proposal_sent | negotiation | verbal_commitment")
    deal_value = dspy.InputField(desc="Estimated deal value in USD")
    days_in_pipeline = dspy.InputField(desc="Days since opportunity created")
    stakeholder_engagement = dspy.InputField(desc="Engagement level of decision makers: high | medium | low")
    competitive_situation = dspy.InputField(desc="Competitive landscape: sole vendor | competitive | unknown")
    budget_confirmed = dspy.InputField(desc="Budget confirmed: yes | no | pending")
    decision_timeline = dspy.InputField(desc="Expected decision timeframe in days")

    close_probability = dspy.OutputField(desc="Probability of close from 0.0 to 1.0")
    predicted_close_date = dspy.OutputField(desc="Estimated close date in days from now")
    deal_health = dspy.OutputField(desc="Overall deal health: healthy | at_risk | stalled | strong")
    blockers = dspy.OutputField(desc="Key blockers or obstacles to closing")
    recommended_actions = dspy.OutputField(desc="Action items to advance the deal")


class DealPredictorModule(dspy.Module):
    """Predict deal closure probability."""

    def __init__(self):
        super().__init__()
        self.predict = dspy.ChainOfThought(DealPredictorSignature)

    def forward(self, lead_name: str, company_name: str, deal_stage: str,
                deal_value: float, days_in_pipeline: int, stakeholder_engagement: str,
                competitive_situation: str, budget_confirmed: str, decision_timeline: int):
        return self.predict(
            lead_name=lead_name,
            company_name=company_name,
            deal_stage=deal_stage,
            deal_value=str(deal_value),
            days_in_pipeline=str(days_in_pipeline),
            stakeholder_engagement=stakeholder_engagement,
            competitive_situation=competitive_situation,
            budget_confirmed=budget_confirmed,
            decision_timeline=str(decision_timeline)
        )


# ============================================================================
# Stage 5: Churn Prediction (Retention stage)
# ============================================================================

class ChurnPredictorSignature(dspy.Signature):
    """
    Predict customer churn risk.

    Analyze customer health signals to identify at-risk customers
    in the retention stage who may churn.
    """
    lead_name = dspy.InputField(desc="Customer contact name")
    company_name = dspy.InputField(desc="Company name")
    days_since_conversion = dspy.InputField(desc="Days since customer converted")
    product_usage = dspy.InputField(desc="JSON with usage metrics: login frequency, feature adoption, activity trends")
    engagement_trend = dspy.InputField(desc="Recent engagement trend: increasing | stable | declining | absent")
    recent_engagement_count = dspy.InputField(desc="Number of engagements in last 30 days")
    last_engagement_days_ago = dspy.InputField(desc="Days since last engagement")
    contract_renewal_days = dspy.InputField(desc="Days until contract renewal")
    expansion_opportunities = dspy.InputField(desc="Upsell/cross-sell opportunities identified: yes | no")
    negative_sentiment_detected = dspy.InputField(desc="Negative feedback or complaints detected: yes | no")

    churn_probability = dspy.OutputField(desc="Churn probability from 0.0 to 1.0. Scores above 0.7 indicate critical risk")
    churn_risk_level = dspy.OutputField(desc="Risk level: critical | high | medium | low | healthy")
    risk_factors = dspy.OutputField(desc="Key indicators of churn risk")
    health_score = dspy.OutputField(desc="Overall customer health score 1-10")
    recommended_intervention = dspy.OutputField(desc="Recommended action: executive escalation | check-in call | product training | success plan review | monitor")


class ChurnPredictorModule(dspy.Module):
    """Predict customer churn risk."""

    def __init__(self):
        super().__init__()
        self.predict = dspy.ChainOfThought(ChurnPredictorSignature)

    def forward(self, lead_name: str, company_name: str, days_since_conversion: int,
                product_usage: str, engagement_trend: str, recent_engagement_count: int,
                last_engagement_days_ago: int, contract_renewal_days: int,
                expansion_opportunities: bool, negative_sentiment_detected: bool):
        return self.predict(
            lead_name=lead_name,
            company_name=company_name,
            days_since_conversion=str(days_since_conversion),
            product_usage=product_usage,
            engagement_trend=engagement_trend,
            recent_engagement_count=str(recent_engagement_count),
            last_engagement_days_ago=str(last_engagement_days_ago),
            contract_renewal_days=str(contract_renewal_days),
            expansion_opportunities="yes" if expansion_opportunities else "no",
            negative_sentiment_detected="yes" if negative_sentiment_detected else "no"
        )
