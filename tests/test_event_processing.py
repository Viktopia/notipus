from datetime import datetime
from app.event_processor import EventProcessor
from app.models import PaymentEvent
import pytest


def test_notification_formatting():
    """Test that notifications are properly formatted"""
    processor = EventProcessor()

    # Test payment failure notification
    payment_event = PaymentEvent(
        id="evt_123",
        event_type="payment_failure",
        customer_id="cust_123",
        amount=49.99,
        currency="USD",
        status="failed",
        timestamp=datetime.now(),
        metadata={
            "failure_reason": "card_declined",
            "retry_count": 2,
        },
    )

    customer_data = {
        "company_name": "Acme Corp",
        "team_size": 50,
        "plan_name": "enterprise",
    }

    notification = processor.format_notification(payment_event, customer_data)
    message = notification.to_slack_message()

    # Check header formatting
    assert "🚨" in message["blocks"][0]["text"]["text"]
    assert "Payment Failed" in message["blocks"][0]["text"]["text"]
    assert "$49.99" in message["blocks"][0]["text"]["text"]

    # Check color
    assert message["color"] == "#dc3545"  # Red for failures

    # Check sections
    assert len(message["blocks"]) >= 3
    assert any(
        "Failed to process payment" in b["text"]["text"]
        for b in message["blocks"]
        if b["type"] == "section"
    )
    assert any(
        "Customer Details" in b["text"]["text"]
        for b in message["blocks"]
        if b["type"] == "section"
    )

    # Check action buttons
    actions = next(b for b in message["blocks"] if b["type"] == "actions")
    assert len(actions["elements"]) == 3
    assert actions["elements"][0]["text"]["text"] == "Update Payment Method"
    assert actions["elements"][1]["text"]["text"] == "Contact Support"
    assert actions["elements"][2]["text"]["text"] == "View Recommendations"

    # Test trial end notification
    trial_event = PaymentEvent(
        id="evt_456",
        event_type="trial_end",
        customer_id="cust_123",
        amount=0,
        currency="USD",
        status="active",
        timestamp=datetime.now(),
        metadata={
            "days_remaining": 7,
        },
    )

    notification = processor.format_notification(trial_event, customer_data)
    message = notification.to_slack_message()

    # Check header formatting
    assert "📢" in message["blocks"][0]["text"]["text"]
    assert "Trial Ending" in message["blocks"][0]["text"]["text"]
    assert "7 Days" in message["blocks"][0]["text"]["text"]

    # Check color
    assert message["color"] == "#ffc107"  # Yellow for trial end

    # Check sections
    assert len(message["blocks"]) >= 3
    assert any(
        "Trial period ending" in b["text"]["text"]
        for b in message["blocks"]
        if b["type"] == "section"
    )
    assert any(
        "Customer Details" in b["text"]["text"]
        for b in message["blocks"]
        if b["type"] == "section"
    )

    # Check action buttons
    actions = next(b for b in message["blocks"] if b["type"] == "actions")
    assert len(actions["elements"]) == 3
    assert actions["elements"][0]["text"]["text"] == "Upgrade Now"
    assert actions["elements"][1]["text"]["text"] == "Schedule Demo"
    assert actions["elements"][2]["text"]["text"] == "View Recommendations"


def test_invalid_event_type():
    """Test handling of invalid event types"""
    processor = EventProcessor()

    with pytest.raises(ValueError, match="Invalid event type"):
        payment_event = PaymentEvent(
            id="evt_123",
            event_type="invalid_type",
            customer_id="cust_123",
            amount=49.99,
            currency="USD",
            status="unknown",
            timestamp=datetime.now(),
            metadata={},
        )
        processor.format_notification(payment_event, {})


def test_missing_required_customer_data():
    """Test handling of missing required customer data"""
    processor = EventProcessor()
    payment_event = PaymentEvent(
        id="evt_123",
        event_type="payment_failure",
        customer_id="cust_123",
        amount=49.99,
        currency="USD",
        status="failed",
        timestamp=datetime.now(),
        metadata={
            "failure_reason": "card_declined",
            "retry_count": 1,
        },
    )

    # Test with empty customer data
    with pytest.raises(ValueError, match="Missing required customer data"):
        processor.format_notification(payment_event, {})

    # Test with partial customer data
    with pytest.raises(ValueError, match="Missing required customer data"):
        processor.format_notification(payment_event, {"company_name": "Acme Corp"})


def test_invalid_currency():
    """Test handling of invalid currency"""
    processor = EventProcessor()

    with pytest.raises(ValueError, match="Invalid currency"):
        payment_event = PaymentEvent(
            id="evt_123",
            event_type="payment_success",
            customer_id="cust_123",
            amount=49.99,
            currency="INVALID",
            status="success",
            timestamp=datetime.now(),
            metadata={},
        )
        processor.format_notification(
            payment_event,
            {"company_name": "Acme Corp", "team_size": 50, "plan_name": "enterprise"},
        )


def test_invalid_amount():
    """Test handling of invalid amount"""
    processor = EventProcessor()

    with pytest.raises(ValueError, match="Amount cannot be negative"):
        payment_event = PaymentEvent(
            id="evt_123",
            event_type="payment_success",
            customer_id="cust_123",
            amount=-49.99,  # Negative amount
            currency="USD",
            status="success",
            timestamp=datetime.now(),
            metadata={},
        )
        processor.format_notification(
            payment_event,
            {"company_name": "Acme Corp", "team_size": 50, "plan_name": "enterprise"},
        )
