"""
Editor DSPy Module

Edits and polishes blog post drafts for clarity, flow, grammar, and engagement.
Outputs edited version with improvements summary.

Training data: Draft vs final published versions.
"""
import dspy
from typing import Optional


class EditorSignature(dspy.Signature):
    """Edit and polish blog post draft for clarity, flow, grammar, and engagement."""

    # Input fields
    draft = dspy.InputField(desc="Blog post draft in markdown")
    style_guide = dspy.InputField(desc="Company style guide rules (optional): AP style, Oxford comma, etc.")
    target_audience = dspy.InputField(desc="Target audience to ensure appropriate complexity level")
    editing_focus = dspy.InputField(desc="Focus areas: grammar | clarity | engagement | all (default)")

    # Output fields
    edited_post = dspy.OutputField(desc="Edited blog post with improved clarity, flow, grammar, and transitions")
    changes_summary = dspy.OutputField(desc="Summary of edits made: e.g., 'Fixed 3 grammar errors, improved 5 transitions, shortened 2 paragraphs'")
    improvement_score = dspy.OutputField(desc="Estimated improvement score 0-10 (how much better is the edited version)")
    remaining_issues = dspy.OutputField(desc="Any issues that still need human review (e.g., 'factual claim needs verification')")


class EditorModule(dspy.Module):
    """DSPy module for blog post editing."""

    def __init__(self):
        super().__init__()
        self.edit = dspy.ChainOfThought(EditorSignature)

    def forward(
        self,
        draft: str,
        style_guide: str = "",
        target_audience: str = "",
        editing_focus: str = "all"
    ):
        """
        Edit blog post draft.

        Args:
            draft: Markdown draft
            style_guide: Style guide rules
            target_audience: Target audience
            editing_focus: Editing focus areas

        Returns:
            dspy.Prediction with edited_post, changes_summary, improvement_score, remaining_issues
        """
        return self.edit(
            draft=draft,
            style_guide=style_guide or "AP style, Oxford comma, active voice preferred",
            target_audience=target_audience or "Technical professionals, decision-makers",
            editing_focus=editing_focus
        )


# Example usage
if __name__ == "__main__":
    import dspy

    lm = dspy.OpenAI(model="gpt-4", max_tokens=3000)
    dspy.settings.configure(lm=lm)

    module = EditorModule()

    draft = """# Test Post\n\nThis is a sample draft with some grammer mistakes and unclear sentances."""

    result = module(
        draft=draft,
        editing_focus="all"
    )

    print(f"Improvement Score: {result.improvement_score}")
    print(f"Changes: {result.changes_summary}")
    print(f"Remaining Issues: {result.remaining_issues}")
    print(f"\nEdited:\n{result.edited_post}")
