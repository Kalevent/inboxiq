"""
SEO Optimizer DSPy Module

Optimizes blog posts for search engines without sacrificing readability.
Outputs SEO-optimized version with meta tags and keyword analysis.

Training data: Posts with known search rankings.
"""
import dspy
from typing import Optional


class SEOOptimizerSignature(dspy.Signature):
    """Optimize blog post for search engines without sacrificing readability."""

    # Input fields
    edited_post = dspy.InputField(desc="Edited blog post in markdown")
    target_keywords = dspy.InputField(desc="JSON array of keywords: [{keyword, volume, difficulty, priority}]")
    competitor_analysis = dspy.InputField(desc="Optional: JSON with competitor insights (top-ranking posts, keyword density)")

    # Output fields
    optimized_post = dspy.OutputField(desc="SEO-optimized version with natural keyword placement, internal links, image alt text suggestions")
    meta_title = dspy.OutputField(desc="SEO meta title (50-60 chars, includes primary keyword)")
    meta_description = dspy.OutputField(desc="SEO meta description (150-160 chars, compelling + keyword-rich)")
    slug = dspy.OutputField(desc="URL slug (lowercase, hyphens, includes primary keyword)")
    seo_score = dspy.OutputField(desc="Estimated SEO score 0-100 based on: keyword usage, readability, structure, links")
    keyword_density = dspy.OutputField(desc="JSON object with keyword densities: {keyword: density_percentage}")
    optimization_notes = dspy.OutputField(desc="Notes on what was optimized: e.g., 'Added 3 internal links, optimized 2 headings, added keyword to first paragraph'")


class SEOOptimizerModule(dspy.Module):
    """DSPy module for SEO optimization."""

    def __init__(self):
        super().__init__()
        self.optimize = dspy.ChainOfThought(SEOOptimizerSignature)

    def forward(
        self,
        edited_post: str,
        target_keywords: str,  # JSON string
        competitor_analysis: Optional[str] = None
    ):
        """
        Optimize blog post for SEO.

        Args:
            edited_post: Edited markdown post
            target_keywords: JSON array of keywords
            competitor_analysis: JSON competitor insights (optional)

        Returns:
            dspy.Prediction with optimized_post, meta_title, meta_description, slug, etc.
        """
        return self.optimize(
            edited_post=edited_post,
            target_keywords=target_keywords,
            competitor_analysis=competitor_analysis or "{}"
        )


# Example usage
if __name__ == "__main__":
    import dspy
    import json

    lm = dspy.OpenAI(model="gpt-4", max_tokens=3000)
    dspy.settings.configure(lm=lm)

    module = SEOOptimizerModule()

    edited_post = "# Lead Routing Guide\n\nLead routing is important for sales teams..."

    target_keywords = json.dumps([
        {"keyword": "lead routing", "volume": 2400, "difficulty": 45, "priority": 1},
        {"keyword": "sales automation", "volume": 1800, "difficulty": 50, "priority": 2}
    ])

    result = module(
        edited_post=edited_post,
        target_keywords=target_keywords
    )

    print(f"Meta Title: {result.meta_title}")
    print(f"Meta Description: {result.meta_description}")
    print(f"Slug: {result.slug}")
    print(f"SEO Score: {result.seo_score}")
    print(f"Keyword Density: {result.keyword_density}")
    print(f"Optimization Notes: {result.optimization_notes}")
