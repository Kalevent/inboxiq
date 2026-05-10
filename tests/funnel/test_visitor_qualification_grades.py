"""Assert VisitorQualificationModule output is non-degenerate.

Symptom this test guards against: production showed 100% of leads with
fit_score=7 because the LLM-driven save_lead path was hardcoding 7. The
fix is to centralize scoring through VisitorQualificationModule, which
this test verifies behaves like a real grader (varied output for varied input).
"""
from unittest.mock import patch, MagicMock

from src.dspy.funnel.visitor_qualification import VisitorQualificationModule


def _fake_prediction(score: int, status: str = "qualified"):
    return MagicMock(
        fit_score=str(score),
        qualification_status=status,
        reasoning="test",
        recommended_action="cold_email",
        red_flags="[]",
        strengths="[]",
    )


def test_module_produces_graded_distribution_across_inputs():
    """Module must produce varied scores when given varied inputs.

    Mocks the LLM to return whatever it would for distinct profiles.
    The point is to assert the *plumbing* doesn't collapse the grade,
    not to assert the LLM is good at grading.
    """
    test_inputs_and_expected_scores = [
        ({"company_name": "Acme SaaS", "company_domain": "acme.com", "industry": "SaaS",
          "employee_count": "250", "location": "San Francisco, US", "contact_title": "VP Sales"}, 9),
        ({"company_name": "TinyCo", "company_domain": "tiny.co", "industry": "Agency",
          "employee_count": "3", "location": "Unknown", "contact_title": "Freelancer"}, 2),
        ({"company_name": "MidCo", "company_domain": "mid.co", "industry": "Healthcare",
          "employee_count": "120", "location": "UK", "contact_title": "Manager"}, 6),
        ({"company_name": "WrongFit", "company_domain": "wf.io", "industry": "Education",
          "employee_count": "5000", "location": "Unknown", "contact_title": "Student"}, 3),
    ]
    seen_scores = set()
    for inputs, score in test_inputs_and_expected_scores:
        with patch("src.dspy.funnel.visitor_qualification.dspy.ChainOfThought") as cot:
            cot.return_value.return_value = _fake_prediction(score)
            module = VisitorQualificationModule()
            result = module(**inputs)
            seen_scores.add(int(result.fit_score))

    assert len(seen_scores) >= 3, f"degenerate distribution: only saw {seen_scores}"


def test_module_does_not_default_to_seven():
    """Regression guard: production data showed 100% leads at fit_score=7.

    If this test ever fails because the module returns 7 even when the LLM
    returned a different value, the plumbing is corrupting the grade.
    """
    with patch("src.dspy.funnel.visitor_qualification.dspy.ChainOfThought") as cot:
        cot.return_value.return_value = _fake_prediction(2, status="disqualified")
        module = VisitorQualificationModule()
        result = module(
            company_name="TinyCo",
            company_domain="tiny.co",
            industry="Agency",
            employee_count="3",
        )
        assert int(result.fit_score) == 2
        assert result.qualification_status == "disqualified"
