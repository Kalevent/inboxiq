"""
Hero Image Prompt Generator — DSPy Module

Generates an optimized DALL-E 3 prompt for a blog post hero image.
The image API call itself stays in src/content/tasks.py — this module
only produces the prompt string passed to DALL-E.

Run standalone:  python -m src.dspy.content.hero_prompt
"""
import dspy


class HeroImagePromptSignature(dspy.Signature):
    """Generate a DALL-E 3 prompt for a professional blog post hero image."""

    # Input fields
    post_title = dspy.InputField(desc="Blog post title")
    primary_keyword = dspy.InputField(desc="Target SEO keyword")
    funnel_stage = dspy.InputField(desc="awareness | discovery | consideration — buyer journey stage")
    industry = dspy.InputField(desc="Target industry: e.g. 'B2B SaaS', 'E-commerce'")

    # Output fields
    dalle_prompt = dspy.OutputField(
        desc=(
            "Complete DALL-E 3 prompt for a professional landscape hero image (16:9). "
            "Must specify: visual subject, style (modern business illustration), mood, "
            "color palette (blue/purple/white tones), and explicitly state 'no text, no words, no letters'. "
            "80-120 words max."
        )
    )
    alt_text = dspy.OutputField(desc="SEO-friendly alt text for the image (under 125 characters)")


class HeroImagePromptModule(dspy.Module):
    """DSPy module for generating DALL-E hero image prompts."""

    def __init__(self):
        super().__init__()
        self.generate = dspy.ChainOfThought(HeroImagePromptSignature)

    def forward(
        self,
        post_title: str,
        primary_keyword: str,
        funnel_stage: str = "awareness",
        industry: str = "B2B SaaS",
    ):
        return self.generate(
            post_title=post_title,
            primary_keyword=primary_keyword,
            funnel_stage=funnel_stage,
            industry=industry,
        )


if __name__ == "__main__":
    from src.dspy import _configure_dspy
    _configure_dspy()

    module = HeroImagePromptModule()

    result = module(
        post_title="5 Key Benefits of Automating Customer Support in B2B SaaS",
        primary_keyword="customer support automation",
        funnel_stage="awareness",
        industry="B2B SaaS",
    )

    print(f"DALL-E Prompt:\n{result.dalle_prompt}")
    print(f"\nAlt Text: {result.alt_text}")
