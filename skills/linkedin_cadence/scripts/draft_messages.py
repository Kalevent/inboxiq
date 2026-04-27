"""
Message Drafter — DSPy Module

Drafts all three LinkedIn messages for a prospect in one ChainOfThought call.
Run standalone: python -m skills.linkedin_cadence.scripts.draft_messages
"""
import dspy


class MessageDrafterSignature(dspy.Signature):
    """Draft three LinkedIn messages for a B2B SaaS outreach sequence."""

    prospect_name = dspy.InputField(desc="Prospect's first name")
    job_title = dspy.InputField(desc="Prospect's job title")
    company_name = dspy.InputField(desc="Prospect's company name")
    industry = dspy.InputField(desc="Prospect's industry")
    product_name = dspy.InputField(desc="Your product name")

    msg_1 = dspy.OutputField(
        desc=(
            "LinkedIn connection request message. Max 300 characters. "
            "Mention shared context or relevant pain point. "
            "No pitch. No product mention. Warm and human."
        )
    )
    msg_2 = dspy.OutputField(
        desc=(
            "Follow-up message sent 3 days after connecting. Max 500 characters. "
            "Share a useful insight or blog post (placeholder: [POST_TITLE] at [POST_URL]). "
            "No ask. Pure value."
        )
    )
    msg_3 = dspy.OutputField(
        desc=(
            "Soft ask sent 5 days after message 2. Max 400 characters. "
            "One CTA only: would a 15-minute call make sense? "
            "Acknowledge they are busy. No pressure."
        )
    )


class MessageDrafterModule(dspy.Module):
    """Drafts all three LinkedIn outreach messages in a single DSPy call."""

    def __init__(self):
        super().__init__()
        self.draft = dspy.ChainOfThought(MessageDrafterSignature)

    def forward(
        self,
        prospect_name: str,
        job_title: str,
        company_name: str,
        industry: str,
        product_name: str = "InboxIQ",
    ):
        return self.draft(
            prospect_name=prospect_name,
            job_title=job_title,
            company_name=company_name,
            industry=industry,
            product_name=product_name,
        )


if __name__ == "__main__":
    from src.dspy import _configure_dspy
    _configure_dspy()

    module = MessageDrafterModule()
    result = module(
        prospect_name="Sarah",
        job_title="Head of Support",
        company_name="Acme SaaS",
        industry="B2B SaaS",
    )
    print(f"Message 1 ({len(result.msg_1)} chars):\n{result.msg_1}\n")
    print(f"Message 2 ({len(result.msg_2)} chars):\n{result.msg_2}\n")
    print(f"Message 3 ({len(result.msg_3)} chars):\n{result.msg_3}\n")
