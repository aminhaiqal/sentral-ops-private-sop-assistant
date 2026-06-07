from app.guardrails import evaluate_question


def categories(question: str) -> set[str]:
    return {warning.category for warning in evaluate_question(question)}


def test_public_ai_invoice_data_triggers_confidential_and_external_ai_boundaries():
    result = categories("Can staff paste invoice data into ChatGPT?")

    assert "confidential_data" in result
    assert "external_ai" in result


def test_payment_confirmation_is_live_boundary():
    result = categories("Is customer ABC's payment confirmed?")

    assert "payment_confirmation" in result
    assert "confidential_data" in result


def test_delivery_eta_boundary():
    result = categories("What is today's delivery ETA?")

    assert "live_delivery_status" in result


def test_large_refund_approval_boundary():
    result = categories("Can I approve a RM2,000 refund?")

    assert "approval_authority" in result


def test_substitution_without_customer_approval_boundary():
    result = categories("Can I substitute clinic gloves without customer approval?")

    assert "substitution_approval" in result


def test_plain_sop_question_has_no_boundary():
    assert categories("What should support check before escalating a missing item?") == set()


def test_refund_approval_process_question_is_not_final_authority_boundary():
    assert categories("What is the refund approval process for damaged goods?") == set()


def test_customer_approval_is_not_confidential_data_boundary():
    result = categories("Can I substitute clinic gloves without customer approval?")

    assert "confidential_data" not in result
    assert "substitution_approval" in result
