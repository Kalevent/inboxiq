"""
Topic Generator DSPy Module

Generates blog topics for a given niche and target audience with SEO potential.
Outputs topic ideas with keywords, search intent, and difficulty estimates.

Training data: Historical blog posts with organic traffic data.
"""
import dspy
from typing import Optional


class TopicGeneratorSignature(dspy.Signature):
    """Generate blog topics for a given niche and target audience with SEO potential."""

    # Input fields
    blog_niche = dspy.InputField(desc="Blog niche/vertical (e.g., 'RevOps automation', 'Lead routing software')")
    target_audience = dspy.InputField(desc="Target audience persona (e.g., 'VP Revenue Operations, 50-300 employees, UK')")
    num_topics = dspy.InputField(desc="Number of topics to generate (default 10)")
    existing_topics = dspy.InputField(desc="Optional: JSON array of already covered topics to avoid duplicates")
    search_trends = dspy.InputField(desc="Optional: JSON array of trending keywords from SEO tools")

    # Output fields
    topics = dspy.OutputField(desc="""JSON array of topic objects with structure:
    [
      {
        "title": "How to Automate Lead Routing for RevOps Teams",
        "angle": "practical_guide",
        "search_intent": "commercial_investigation",
        "target_keyword": "automate lead routing",
        "secondary_keywords": ["lead routing software", "SDR automation"],
        "estimated_difficulty": 45,
        "estimated_monthly_searches": 1200,
        "target_stage": "discovery"
      }
    ]""")
    reasoning = dspy.OutputField(desc="Why these topics will resonate with the audience and rank well in search")


class TopicGeneratorModule(dspy.Module):
    """DSPy module for blog topic generation."""

    def __init__(self):
        super().__init__()
        self.generate = dspy.ChainOfThought(TopicGeneratorSignature)

    def forward(
        self,
        blog_niche: str,
        target_audience: str,
        num_topics: int = 10,
        existing_topics: Optional[str] = None,
        search_trends: Optional[str] = None
    ):
        """
        Generate blog topics.

        Args:
            blog_niche: Blog niche/vertical
            target_audience: Target audience persona
            num_topics: Number of topics (default: 10)
            existing_topics: JSON array of covered topics (optional)
            search_trends: JSON array of trending keywords (optional)

        Returns:
            dspy.Prediction with topics and reasoning
        """
        return self.generate(
            blog_niche=blog_niche,
            target_audience=target_audience,
            num_topics=str(num_topics),
            existing_topics=existing_topics or "[]",
            search_trends=search_trends or "[]"
        )


# Example usage for testing
if __name__ == "__main__":
    import dspy
    import json

    # Configure DSPy
    lm = dspy.OpenAI(model="gpt-4", max_tokens=1500)
    dspy.settings.configure(lm=lm)

    # Initialize module
    module = TopicGeneratorModule()

    # Test topic generation
    existing_topics = json.dumps([
        "The Ultimate Guide to Lead Scoring",
        "5 RevOps Metrics That Matter"
    ])

    search_trends = json.dumps([
        {"keyword": "revenue operations automation", "volume": 2400, "trend": "rising"},
        {"keyword": "lead routing best practices", "volume": 1800, "trend": "stable"}
    ])

    result = module(
        blog_niche="Revenue Operations Automation",
        target_audience="VP Revenue Operations, B2B SaaS companies, 100-500 employees",
        num_topics=5,
        existing_topics=existing_topics,
        search_trends=search_trends
    )

    print("Generated Topics:")
    topics = json.loads(result.topics)
    for i, topic in enumerate(topics, 1):
        print(f"\n{i}. {topic['title']}")
        print(f"   Keyword: {topic['target_keyword']}")
        print(f"   Difficulty: {topic['estimated_difficulty']}")
        print(f"   Searches: {topic['estimated_monthly_searches']}")

    print(f"\nReasoning: {result.reasoning}")
