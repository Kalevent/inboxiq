"""
DSPy modules for Leads Funnel v2.0

Automated qualification, scoring, and prediction modules for each funnel stage.
All modules use DSPy for prompt optimization and reasoning.
"""

from .visitor_qualification import VisitorQualificationModule
from .interest_scoring import InterestScoringModule
from .buying_intent import BuyingIntentModule
from .deal_predictor import DealPredictorModule
from .churn_predictor import ChurnPredictorModule

__all__ = [
    "VisitorQualificationModule",
    "InterestScoringModule",
    "BuyingIntentModule",
    "DealPredictorModule",
    "ChurnPredictorModule",
]
