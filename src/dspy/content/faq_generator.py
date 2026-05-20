import dspy


class BlogFAQGeneratorSignature(dspy.Signature):
    """Generate 5 FAQ pairs in markdown from an existing blog post."""

    post_content = dspy.InputField(
        desc="Full blog post markdown content (first 3000 characters)"
    )
    post_title = dspy.InputField(desc="Blog post title")
    primary_keyword = dspy.InputField(desc="Primary SEO keyword for the post")

    faq_markdown = dspy.OutputField(
        desc=(
            "A '## Frequently Asked Questions' section in markdown with exactly 5 Q&A pairs. "
            "Format each pair as:\n**Question text?**\n\nAnswer text.\n\n"
            "Questions must be specific to the post topic, answerable from the content, "
            "and useful to the target reader. Answers must be 2-4 sentences."
        )
    )


class BlogFAQGeneratorModule(dspy.Module):
    """DSPy module that generates a FAQ section for an existing blog post."""

    def __init__(self):
        super().__init__()
        self.generate = dspy.ChainOfThought(BlogFAQGeneratorSignature)

    def forward(self, post_content: str, post_title: str, primary_keyword: str = "") -> dspy.Prediction:
        return self.generate(
            post_content=post_content[:3000],
            post_title=post_title,
            primary_keyword=primary_keyword or "",
        )
