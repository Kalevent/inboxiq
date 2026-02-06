"""
Content Writer DSPy Module

Writes full blog posts from outlines with engaging, professional tone.
Outputs complete markdown blog post with proper structure.

Training data: High-quality published blog posts.
"""
import dspy
from typing import Optional


class ContentWriterSignature(dspy.Signature):
    """Write full blog post from outline with engaging, professional tone."""

    # Input fields
    outline = dspy.InputField(desc="Blog post outline (JSON)")
    tone = dspy.InputField(desc="Writing tone: professional | conversational | technical | storytelling")
    brand_voice = dspy.InputField(desc="Brand voice guidelines (e.g., 'helpful but not salesy, data-driven')")
    include_examples = dspy.InputField(desc="Boolean: include real-world examples and case studies")
    include_stats = dspy.InputField(desc="Boolean: include industry statistics and data")

    # Output fields
    blog_post_draft = dspy.OutputField(desc="Full blog post in markdown format with H2/H3 headings, paragraphs, lists, bold/italic emphasis")
    word_count = dspy.OutputField(desc="Actual word count (int)")
    readability_score = dspy.OutputField(desc="Flesch reading ease score estimate (0-100, target >60)")
    sections_written = dspy.OutputField(desc="Number of sections completed (int)")


class ContentWriterModule(dspy.Module):
    """DSPy module for blog post writing."""

    def __init__(self):
        super().__init__()
        self.write = dspy.ChainOfThought(ContentWriterSignature)

    def forward(
        self,
        outline: str,  # JSON string
        tone: str = "professional",
        brand_voice: str = "",
        include_examples: bool = True,
        include_stats: bool = True
    ):
        """
        Write full blog post.

        Args:
            outline: JSON outline
            tone: Writing tone
            brand_voice: Brand voice guidelines
            include_examples: Include examples flag
            include_stats: Include stats flag

        Returns:
            dspy.Prediction with blog_post_draft, word_count, readability_score, sections_written
        """
        return self.write(
            outline=outline,
            tone=tone,
            brand_voice=brand_voice or "Helpful, data-driven, professional but approachable",
            include_examples=str(include_examples).lower(),
            include_stats=str(include_stats).lower()
        )


# Example usage
if __name__ == "__main__":
    import dspy
    import json

    lm = dspy.OpenAI(model="gpt-4", max_tokens=3000)
    dspy.settings.configure(lm=lm)

    module = ContentWriterModule()

    outline = json.dumps({
        "working_title": "5 Ways to Automate Lead Routing",
        "introduction": {"hook": "Manual lead routing is costing you deals."},
        "sections": [{"h2_heading": "Why Automation Matters", "subpoints": ["Speed", "Accuracy"]}]
    })

    result = module(
        outline=outline,
        tone="conversational",
        include_examples=True,
        include_stats=True
    )

    print(f"Word Count: {result.word_count}")
    print(f"Readability: {result.readability_score}")
    print(f"\nDraft:\n{result.blog_post_draft[:500]}...")
