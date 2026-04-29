"""
Blog Post Quality Evaluator — DSPy Module

Evaluates a blog post draft against publishing standards before it goes live.
Use this on posts sitting in 'draft' status to decide: publish, expand, or rewrite.

Run standalone:  python -m src.dspy.content.evaluate
"""
import dspy


class BlogQualityEvaluatorSignature(dspy.Signature):
    """Evaluate a blog post draft against SEO and content quality standards."""

    # Input fields
    post_markdown = dspy.InputField(desc="Blog post content in Markdown")
    primary_keyword = dspy.InputField(desc="Target SEO keyword this post is optimised for")
    word_count = dspy.InputField(desc="Actual word count of the post as an integer string")
    target_audience = dspy.InputField(desc="Intended reader: e.g. 'B2B SaaS founder, 10-50 employees'")

    # Output fields
    publish_verdict = dspy.OutputField(desc="One of: publish | expand | rewrite — what should happen next")
    quality_score = dspy.OutputField(desc="Overall quality score 0-100 combining SEO, depth, and readability")
    seo_issues = dspy.OutputField(desc="Comma-separated list of SEO problems: e.g. 'keyword missing from H1, no meta description hook, thin introduction'")
    content_issues = dspy.OutputField(desc="Comma-separated list of content problems: e.g. 'no examples, unsupported claims, abrupt ending, missing CTA'")
    expand_suggestions = dspy.OutputField(desc="If verdict is expand: specific sections to add or deepen. Empty string otherwise.")
    rewrite_reason = dspy.OutputField(desc="If verdict is rewrite: one sentence explaining why expansion alone won't fix it. Empty string otherwise.")


class BlogQualityEvaluatorModule(dspy.Module):
    """DSPy module for evaluating blog post quality before publishing."""

    def __init__(self):
        super().__init__()
        self.evaluate = dspy.ChainOfThought(BlogQualityEvaluatorSignature)

    def forward(
        self,
        post_markdown: str,
        primary_keyword: str,
        word_count: int,
        target_audience: str = "B2B SaaS founder, 10-50 employees, UK or US",
    ):
        return self.evaluate(
            post_markdown=post_markdown,
            primary_keyword=primary_keyword,
            word_count=str(word_count),
            target_audience=target_audience,
        )


if __name__ == "__main__":
    from src.dspy import _configure_dspy
    _configure_dspy()

    module = BlogQualityEvaluatorModule()

    sample = """# How Customer Support Automation Saves B2B SaaS Teams Time

    Customer support automation is changing how SaaS teams operate. In this post we cover the key benefits.

    ## Benefit 1: Faster Response Times
    Automated triage routes tickets instantly.

    ## Benefit 2: Reduced Workload
    Agents focus on complex issues while automation handles repetitive queries.
    """

    result = module(
        post_markdown=sample,
        primary_keyword="customer support automation b2b saas",
        word_count=len(sample.split()),
    )

    print(f"Verdict:          {result.publish_verdict}")
    print(f"Quality Score:    {result.quality_score}")
    print(f"SEO Issues:       {result.seo_issues}")
    print(f"Content Issues:   {result.content_issues}")
    print(f"Expand:           {result.expand_suggestions}")
    print(f"Rewrite Reason:   {result.rewrite_reason}")
