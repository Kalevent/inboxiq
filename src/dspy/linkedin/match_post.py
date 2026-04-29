"""
Blog Post Matcher — DSPy Module

Selects the most relevant published blog post for a prospect's message 2.
Run standalone: python -m src.dspy.linkedin.match_post
"""
import dspy


class BlogPostMatcherSignature(dspy.Signature):
    """Select the most relevant blog post to share with a LinkedIn prospect."""

    prospect_industry = dspy.InputField(desc="Prospect's industry")
    job_title = dspy.InputField(desc="Prospect's job title")
    posts_json = dspy.InputField(
        desc='JSON array of published posts: [{"slug": "...", "title": "...", "primary_keyword": "..."}]'
    )

    selected_slug = dspy.OutputField(desc="Slug of the best matching post from the posts_json array")
    reason = dspy.OutputField(
        desc="One sentence explaining why this post is relevant to this prospect's role and industry"
    )


class BlogPostMatcherModule(dspy.Module):
    """Selects the best published blog post for a LinkedIn prospect."""

    def __init__(self):
        super().__init__()
        self.match = dspy.ChainOfThought(BlogPostMatcherSignature)

    def forward(self, prospect_industry: str, job_title: str, posts_json: str):
        return self.match(
            prospect_industry=prospect_industry,
            job_title=job_title,
            posts_json=posts_json,
        )


if __name__ == "__main__":
    import json
    from src.dspy import _configure_dspy
    _configure_dspy()

    module = BlogPostMatcherModule()
    posts = [
        {"slug": "customer-support-automation-benefits", "title": "Key Benefits of Customer Support Automation for B2B SaaS", "primary_keyword": "customer support automation"},
        {"slug": "post-purchase-strategies", "title": "Top 5 Post-Purchase Strategies for E-commerce Loyalty", "primary_keyword": "post-purchase strategies"},
    ]
    result = module(
        prospect_industry="B2B SaaS",
        job_title="Head of Support",
        posts_json=json.dumps(posts),
    )
    print(f"Selected: {result.selected_slug}")
    print(f"Reason:   {result.reason}")
