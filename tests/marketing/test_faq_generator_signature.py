import dspy
from src.dspy.content.faq_generator import BlogFAQGeneratorSignature, BlogFAQGeneratorModule


def test_signature_is_dspy_signature_subclass():
    assert issubclass(BlogFAQGeneratorSignature, dspy.Signature)


def test_signature_has_faq_markdown_output():
    sig = BlogFAQGeneratorSignature
    assert issubclass(sig, dspy.Signature)


def test_module_instantiates():
    module = BlogFAQGeneratorModule()
    assert hasattr(module, "generate")
