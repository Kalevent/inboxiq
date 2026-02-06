"""
Outline Creator DSPy Module

Creates detailed, SEO-optimized outlines for blog posts.
Outputs structured outline with sections, headings, and key points.

Training data: High-performing blog posts with extracted outlines.
"""
import dspy
from typing import Optional


class OutlineCreatorSignature(dspy.Signature):
    """Create detailed, SEO-optimized outline for a blog post."""

    # Input fields
    topic = dspy.InputField(desc="Blog topic object with title, keywords, angle")
    target_word_count = dspy.InputField(desc="Target word count (default 1500)")
    content_depth = dspy.InputField(desc="Content depth: beginner | intermediate | expert")
    competitor_examples = dspy.InputField(desc="Optional: JSON array of top-ranking competitor post URLs")

    # Output fields
    outline = dspy.OutputField(desc="""JSON structured outline:
    {
      "working_title": "How to Automate Lead Routing: 7 Steps for RevOps Teams",
      "meta_description": "Learn how to automate lead routing...",
      "introduction": {
        "hook": "Opening sentence to grab attention",
        "problem_statement": "What pain point are we addressing",
        "solution_preview": "What the reader will learn"
      },
      "sections": [
        {
          "h2_heading": "Why Manual Lead Routing Fails",
          "subpoints": ["Reason 1", "Reason 2"],
          "key_facts": ["Stat 1", "Stat 2"],
          "examples": ["Example scenario"],
          "target_keywords": ["manual lead routing", "lead routing challenges"]
        }
      ],
      "conclusion": {
        "summary": "Recap of key points",
        "cta": "Next step for the reader",
        "cta_type": "demo_booking | gated_content | newsletter_signup"
      }
    }""")
    estimated_word_count = dspy.OutputField(desc="Estimated word count based on outline depth (int)")
    research_sources = dspy.OutputField(desc="Suggested sources to cite (URLs, reports, studies)")


class OutlineCreatorModule(dspy.Module):
    """DSPy module for blog post outline creation."""

    def __init__(self):
        super().__init__()
        self.create = dspy.ChainOfThought(OutlineCreatorSignature)

    def forward(
        self,
        topic: str,  # JSON string
        target_word_count: int = 1500,
        content_depth: str = "intermediate",
        competitor_examples: Optional[str] = None
    ):
        """
        Create blog post outline.

        Args:
            topic: JSON topic object
            target_word_count: Target word count
            content_depth: Content depth level
            competitor_examples: JSON array of competitor URLs (optional)

        Returns:
            dspy.Prediction with outline, estimated_word_count, research_sources
        """
        return self.create(
            topic=topic,
            target_word_count=str(target_word_count),
            content_depth=content_depth,
            competitor_examples=competitor_examples or "[]"
        )


# Example usage
if __name__ == "__main__":
    import dspy
    import json

    from src.dspy import _configure_dspy
    _configure_dspy()

    module = OutlineCreatorModule()

    topic = json.dumps({
        "title": "How to Automate Lead Routing for RevOps Teams",
        "target_keyword": "automate lead routing",
        "angle": "practical_guide"
    })

    result = module(
        topic=topic,
        target_word_count=2000,
        content_depth="intermediate"
    )

    print(f"Outline: {result.outline}")
    print(f"Estimated Words: {result.estimated_word_count}")
    print(f"Research Sources: {result.research_sources}")
