"""
Hero Image Prompt Generator — DSPy Module

Generates an optimized DALL-E 3 prompt for a blog post hero image.
The image API call itself stays in src/content/tasks.py — this module
only produces the prompt string passed to DALL-E.

Run standalone:  python -m src.dspy.content.hero_prompt
"""
import dspy


class HeroImagePromptSignature(dspy.Signature):
    """Generate a DALL-E 3 prompt for a blog post hero image that looks like editorial photography or human-crafted illustration."""

    # Input fields
    post_title = dspy.InputField(desc="Blog post title")
    primary_keyword = dspy.InputField(desc="Target SEO keyword")
    funnel_stage = dspy.InputField(desc="awareness | discovery | consideration — buyer journey stage")
    industry = dspy.InputField(desc="Target industry: e.g. 'B2B SaaS', 'E-commerce'")

    # Output fields
    dalle_prompt = dspy.OutputField(
        desc=(
            "Complete DALL-E 3 prompt for a 16:9 landscape hero image. "
            "The image must look like editorial photography or a high-quality human-made illustration — "
            "natural, grounded, and specific to the post topic. "
            "\n\nSTYLE: Choose ONE that fits the topic: "
            "(1) editorial documentary photography — real people in real workplaces, natural lighting, candid moments; "
            "(2) flat editorial illustration — New Yorker / Economist style, hand-drawn feel, limited palette, purposeful composition; "
            "(3) environmental still life — real objects arranged with intention, soft natural light, shallow depth of field. "
            "\n\nCOLOR: Derive from the topic and industry — warm neutrals for human stories, muted greens/blues for operations/tech, "
            "terracotta/amber for growth/energy. Never default to blue-purple gradients. "
            "\n\nSUBJECT: Make it specific to the post title. A post about customer support automation → a person at a desk looking calm and in control, "
            "not floating gears. A post about lead generation → a confident conversation, not a funnel diagram. "
            "\n\nSTRICTLY AVOID: gears, cogs, circuit boards, globes, robotic arms, handshakes, neon glows, "
            "isometric 3D objects, generic business icons, floating UI elements, abstract blue swirls, "
            "anything that looks like stock art or AI-generated filler. "
            "\n\nEnd with: 'No text, no words, no letters, no logos.' "
            "80-120 words total."
        )
    )
    alt_text = dspy.OutputField(desc="SEO-friendly alt text describing the actual image content specifically (under 125 characters)")


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
