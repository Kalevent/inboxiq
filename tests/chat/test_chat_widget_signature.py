def test_build_chat_widget_reply_has_branch_field():
    import dspy
    from src.dspy.signatures import build_chat_widget_reply

    module = build_chat_widget_reply(dspy)
    sig = module.predict.signature
    assert 'branch' in sig.input_fields, "branch field missing from ChatWidgetReplySignature"

def test_build_chat_widget_reply_branch_is_input_not_output():
    import dspy
    from src.dspy.signatures import build_chat_widget_reply

    module = build_chat_widget_reply(dspy)
    sig = module.predict.signature
    assert 'branch' not in sig.output_fields, "branch should be an input field, not an output"
