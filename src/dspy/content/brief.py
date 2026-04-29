"""
Content Brief Generator — DSPy Module

Generates a structured content brief for a given topic before passing it
to the full 5-stage generation pipeline (OutlineCreator → ContentWriter → Editor → SEOOptimizer).

Use this when pitching a topic manually via the Pitched Blog Topics UI — run it
first to validate the topic has enough search intent and depth to justify 1,500 words.

Run standalone:  python -m src.dspy.content.brief
"""
import dspy


class ContentBriefSignature(dspy.Signature):
    """Generate a structured content brief for a blog post topic."""

    # Input fields
    topic_title = dspy.InputField(desc="Proposed blog post title or topic idea")
    primary_keyword = dspy.InputField(desc="Target SEO keyword")
    target_audience = dspy.InputField(desc="Intended reader: role, company type, pain point")
    funnel_stage = dspy.InputField(desc="awareness | discovery | consideration — where in the buyer journey this post sits")

    # Output fields
    approved = dspy.OutputField(desc="true | false — is this topic worth writing 1,500 words on for the given audience?")
    rejection_reason = dspy.OutputField(desc="If approved is false: one sentence explaining why. Empty string otherwise.")
    refined_title = dspy.OutputField(desc="Improved title optimised for the primary keyword and audience intent")
    angle = dspy.OutputField(desc="The specific editorial angle: e.g. 'comparison', 'how-to', 'case study', 'listicle'")
    key_sections = dspy.OutputField(desc="Newline-separated list of H2 section titles the post should cover (4-6 sections)")
    unique_value = dspy.OutputField(desc="One sentence: what will a reader learn that they can't get from the top 3 Google results?")
    cta = dspy.OutputField(desc="Recommended call-to-action at the end of the post, tied to InboxIQ's trial offer")


class ContentBriefModule(dspy.Module):
    """DSPy module for generating and validating a blog content brief."""

    def __init__(self):
        super().__init__()
        self.brief = dspy.ChainOfThought(ContentBriefSignature)

    def forward(
        self,
        topic_title: str,
        primary_keyword: str,
        target_audience: str = "B2B SaaS founder, 10-50 employees, UK or US",
        funnel_stage: str = "awareness",
    ):
        return self.brief(
            topic_title=topic_title,
            primary_keyword=primary_keyword,
            target_audience=target_audience,
            funnel_stage=funnel_stage,
        )


if __name__ == "__main__":
    from src.dspy import _configure_dspy
    _configure_dspy()

    module = ContentBriefModule()

    result = module(
        topic_title="How to Automate Customer Support Without Losing the Human Touch",
        primary_keyword="customer support automation saas",
        funnel_stage="awareness",
    )

    print(f"Approved:        {result.approved}")
    print(f"Rejection:       {result.rejection_reason}")
    print(f"Refined Title:   {result.refined_title}")
    print(f"Angle:           {result.angle}")
    print(f"Unique Value:    {result.unique_value}")
    print(f"CTA:             {result.cta}")
    print(f"\nKey Sections:\n{result.key_sections}")
