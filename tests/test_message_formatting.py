import pytest
from app import create_enriched_slack_message

def test_payment_failure_message_structure(sample_chargify_failure):
    """Test that payment failure messages contain all required components"""
    message_text = "Test payment failure message"
    result = create_enriched_slack_message("payment_failure", sample_chargify_failure, message_text)

    assert "blocks" in result
    blocks = result["blocks"]

    # Check main message
    assert blocks[0]["type"] == "section"
    assert blocks[0]["text"]["text"] == message_text

    # Check failure details
    assert len(blocks) >= 3  # Main message + failure details + actions
    failure_block = blocks[1]
    assert failure_block["type"] == "section"
    assert len(failure_block["fields"]) == 2  # Amount and retry count
    assert "Failed Amount" in failure_block["fields"][0]["text"]
    assert "Retry Count" in failure_block["fields"][1]["text"]

    # Check action items
    action_block = blocks[2]
    assert action_block["type"] == "section"
    assert "Immediate Actions Required" in action_block["text"]["text"]
    assert "Contact customer" in action_block["text"]["text"]

def test_trial_end_message_structure(sample_chargify_trial_end):
    """Test that trial end messages contain all required components"""
    message_text = "Test trial end message"
    result = create_enriched_slack_message("trial_end", sample_chargify_trial_end, message_text)

    assert "blocks" in result
    blocks = result["blocks"]

    # Check main message
    assert blocks[0]["type"] == "section"
    assert blocks[0]["text"]["text"] == message_text

    # Check recommended actions
    assert len(blocks) >= 2  # Main message + recommendations
    action_block = blocks[1]
    assert action_block["type"] == "section"
    assert "Recommended Actions" in action_block["text"]["text"]
    assert "follow-up email" in action_block["text"]["text"].lower()

def test_customer_profile_link_present(sample_chargify_payment):
    """Test that all messages include a customer profile link"""
    message_text = "Test message"
    result = create_enriched_slack_message("any_type", sample_chargify_payment, message_text)

    blocks = result["blocks"]

    # Find the actions block with the customer profile link
    actions_block = next(
        (block for block in blocks if block["type"] == "actions"),
        None
    )

    assert actions_block is not None
    assert len(actions_block["elements"]) > 0
    button = actions_block["elements"][0]
    assert button["type"] == "button"
    assert button["text"]["text"] == "View Customer Profile"
    assert "customers/" in button["url"]

def test_message_text_preserved(sample_chargify_payment):
    """Test that the original message text is preserved in the enriched message"""
    message_text = "This is a test message with {special} characters!"
    result = create_enriched_slack_message("any_type", sample_chargify_payment, message_text)

    blocks = result["blocks"]
    assert blocks[0]["text"]["text"] == message_text
