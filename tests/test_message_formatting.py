from app import create_enriched_slack_message


def test_payment_failure_message_structure(sample_chargify_failure):
    """Test that payment failure messages contain all required components"""
    message_text = "Test payment failure message"
    result = create_enriched_slack_message(
        "payment_failure", sample_chargify_failure, message_text
    )

    assert "blocks" in result
    blocks = result["blocks"]

    # Check header
    assert blocks[0]["type"] == "header"
    assert "🚨" in blocks[0]["text"]["text"]

    # Check main message
    assert blocks[1]["type"] == "section"
    assert blocks[1]["text"]["text"] == message_text

    # Check failure details
    assert blocks[2]["type"] == "section"
    assert "$49.99" in blocks[2]["text"]["text"]  # Amount from sample data
    assert "2" in blocks[2]["text"]["text"]  # Retry count from sample data

    # Check action items
    assert blocks[3]["type"] == "section"
    assert "Actions Required" in blocks[3]["text"]["text"]

    # Check action buttons
    assert blocks[4]["type"] == "actions"
    assert len(blocks[4]["elements"]) > 0


def test_trial_end_message_structure(sample_chargify_trial_end):
    """Test that trial end messages contain all required components"""
    message_text = "Test trial end message"
    result = create_enriched_slack_message(
        "trial_end", sample_chargify_trial_end, message_text
    )

    assert "blocks" in result
    blocks = result["blocks"]

    # Check header
    assert blocks[0]["type"] == "header"
    assert "📢" in blocks[0]["text"]["text"]

    # Check main message
    assert blocks[1]["type"] == "section"
    assert blocks[1]["text"]["text"] == message_text

    # Check recommendations
    assert blocks[2]["type"] == "section"
    assert "Recommended Actions" in blocks[2]["text"]["text"]

    # Check action buttons
    assert blocks[3]["type"] == "actions"
    assert len(blocks[3]["elements"]) > 0


def test_message_color_by_type(sample_chargify_failure, sample_chargify_trial_end):
    """Test that message color is set based on event type"""
    failure_message = create_enriched_slack_message(
        "payment_failure", sample_chargify_failure, "Test message"
    )
    trial_message = create_enriched_slack_message(
        "trial_end", sample_chargify_trial_end, "Test message"
    )

    assert failure_message["color"] == "#FF0000"  # Red for failures
    assert trial_message["color"] == "#FFA500"  # Orange for other events


def test_message_text_preserved(sample_chargify_payment):
    """Test that the original message text is preserved in the enriched message"""
    message_text = "This is a test message with {special} characters!"
    result = create_enriched_slack_message(
        "any_type", sample_chargify_payment, message_text
    )

    blocks = result["blocks"]
    assert blocks[1]["text"]["text"] == message_text
