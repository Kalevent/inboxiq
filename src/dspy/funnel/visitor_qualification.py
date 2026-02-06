"""
Visitor Qualification DSPy Module

Assesses ICP (Ideal Customer Profile) fit for prospects entering the funnel.
Outputs fit score (0-10) and recommended next action.

Training data: Historical qualified leads + closed-won customers vs poor-fit leads.
"""
import dspy
from typing import Optional


class VisitorQualificationSignature(dspy.Signature):
    """Qualify visitor as ICP match and recommend next action."""

    # Input fields
    company_name = dspy.InputField(desc="Company name")
    company_domain = dspy.InputField(desc="Company website domain (e.g., acme.com)")
    industry = dspy.InputField(desc="Company industry/vertical")
    employee_count = dspy.InputField(desc="Number of employees (int or range like '50-100')")
    location = dspy.InputField(desc="Company location (city, country)")
    contact_title = dspy.InputField(desc="Contact's job title (if available)")
    source = dspy.InputField(desc="How we discovered this lead (e.g., linkedin, search, referral)")

    # Target ICP criteria (provided as context)
    icp_criteria = dspy.InputField(desc="""JSON string with ICP criteria:
    {
      "target_industries": ["SaaS", "Technology", "Financial Services"],
      "min_employees": 50,
      "max_employees": 5000,
      "target_locations": ["US", "CA", "UK", "EU"],
      "target_titles": ["VP", "Director", "Head", "C-level", "Manager"],
      "disqualifiers": ["agency", "consultancy", "freelancer"]
    }""")

    # Output fields
    fit_score = dspy.OutputField(desc="ICP fit score from 0-10 (10 = perfect fit, 0 = terrible fit)")
    qualification_status = dspy.OutputField(desc="Status: qualified | maybe | disqualified")
    reasoning = dspy.OutputField(desc="2-3 sentence explanation of the fit score and why this lead does/doesn't match ICP")
    recommended_action = dspy.OutputField(desc="Next action: cold_email | nurture_sequence | research_more | discard")
    red_flags = dspy.OutputField(desc="JSON array of red flags if any, empty array if none: e.g., ['too_small', 'wrong_industry', 'competitor']")
    strengths = dspy.OutputField(desc="JSON array of positive signals: e.g., ['perfect_size', 'target_industry', 'senior_contact']")


class VisitorQualificationModule(dspy.Module):
    """DSPy module for visitor qualification with ICP fit scoring."""

    def __init__(self):
        super().__init__()
        self.qualify = dspy.ChainOfThought(VisitorQualificationSignature)

    def forward(
        self,
        company_name: str,
        company_domain: str,
        industry: Optional[str] = None,
        employee_count: Optional[str] = None,
        location: Optional[str] = None,
        contact_title: Optional[str] = None,
        source: Optional[str] = None,
        icp_criteria: Optional[str] = None
    ):
        """
        Qualify a visitor against ICP criteria.

        Args:
            company_name: Company name
            company_domain: Company domain
            industry: Industry/vertical (optional)
            employee_count: Employee count or range (optional)
            location: Company location (optional)
            contact_title: Contact job title (optional)
            source: Lead source (optional)
            icp_criteria: JSON string with ICP criteria (optional, uses default if not provided)

        Returns:
            dspy.Prediction with fit_score, qualification_status, reasoning, etc.
        """
        # Default ICP criteria if not provided
        if not icp_criteria:
            import json
            icp_criteria = json.dumps({
                "target_industries": ["SaaS", "Technology", "Financial Services", "Healthcare", "E-commerce"],
                "min_employees": 50,
                "max_employees": 5000,
                "target_locations": ["US", "CA", "UK", "EU"],
                "target_titles": ["VP", "Director", "Head", "C-level", "Manager", "Lead"],
                "disqualifiers": ["agency", "consultancy", "freelancer", "student"]
            })

        return self.qualify(
            company_name=company_name or "Unknown",
            company_domain=company_domain or "Unknown",
            industry=industry or "Unknown",
            employee_count=employee_count or "Unknown",
            location=location or "Unknown",
            contact_title=contact_title or "Unknown",
            source=source or "Unknown",
            icp_criteria=icp_criteria
        )


# Example usage for testing
if __name__ == "__main__":
    import dspy

    # Configure DSPy (use appropriate LM)
    lm = dspy.OpenAI(model="gpt-4", max_tokens=500)
    dspy.settings.configure(lm=lm)

    # Initialize module
    module = VisitorQualificationModule()

    # Test qualification
    result = module(
        company_name="Acme Corp",
        company_domain="acme.com",
        industry="SaaS",
        employee_count="250",
        location="San Francisco, US",
        contact_title="VP of Sales",
        source="linkedin"
    )

    print(f"Fit Score: {result.fit_score}")
    print(f"Status: {result.qualification_status}")
    print(f"Reasoning: {result.reasoning}")
    print(f"Recommended Action: {result.recommended_action}")
    print(f"Red Flags: {result.red_flags}")
    print(f"Strengths: {result.strengths}")
