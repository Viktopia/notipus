from datetime import datetime
from app.models import PaymentEvent, Notification, NotificationSection


def test_payment_failure_message_structure():
    """Test that payment failure messages contain all required components"""
    event = PaymentEvent(
        id="evt_123",
        event_type="payment_failure",
        customer_id="cust_123",
        amount=29.99,
        currency="USD",
        status="failed",
        timestamp=datetime.now(),
        metadata={
            "failure_reason": "card_declined",
            "retry_count": 2,
        },
    )

    notification = Notification(
        id=event.id,
        status=event.status,
        event=event,
        sections=[
            NotificationSection(
                text="Failed to process payment for Acme Corp\nReason: Card declined"
            ),
            NotificationSection(
                text="*Customer Details:*\n• Company: Acme Corp\n• Team Size: 50\n• Plan: Enterprise"
            ),
        ],
        action_buttons=[
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Update Payment Method"},
                "style": "primary",
                "url": "/update-payment/cust_123",
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Contact Support"},
                "url": "/support/cust_123",
            },
        ],
    )

    message = notification.to_slack_message()
    assert len(message["blocks"]) >= 3  # Header + 2 sections
    assert message["color"] == "#dc3545"  # Red for failures
    assert "Failed to process payment" in message["blocks"][1]["text"]["text"]
    assert "Customer Details" in message["blocks"][2]["text"]["text"]


def test_trial_end_message_structure():
    """Test that trial end messages contain all required components"""
    event = PaymentEvent(
        id="evt_123",
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

    notification = Notification(
        id=event.id,
        status=event.status,
        event=event,
        sections=[
            NotificationSection(text="Trial period ending in 7 days\nPlan: Enterprise"),
            NotificationSection(
                text="*Customer Details:*\n• Company: Acme Corp\n• Team Size: 50\n• Plan: Enterprise"
            ),
        ],
        action_buttons=[
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Upgrade Now"},
                "style": "primary",
                "url": "/upgrade/cust_123",
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Schedule Demo"},
                "url": "/schedule-demo/cust_123",
            },
        ],
    )

    message = notification.to_slack_message()
    assert len(message["blocks"]) >= 3  # Header + 2 sections
    assert message["color"] == "#ffc107"  # Yellow for trial end
    assert "Trial period ending" in message["blocks"][1]["text"]["text"]
    assert "Customer Details" in message["blocks"][2]["text"]["text"]


def test_message_color_by_type():
    """Test that message color is set based on event type"""
    failure_event = PaymentEvent(
        id="evt_123",
        event_type="payment_failure",
        customer_id="cust_123",
        amount=29.99,
        currency="USD",
        status="failed",
        timestamp=datetime.now(),
        metadata={},
    )

    failure_notification = Notification(
        id=failure_event.id,
        status=failure_event.status,
        event=failure_event,
        sections=[],
        action_buttons=[],
    )

    success_event = PaymentEvent(
        id="evt_124",
        event_type="payment_success",
        customer_id="cust_123",
        amount=29.99,
        currency="USD",
        status="success",
        timestamp=datetime.now(),
        metadata={},
    )

    success_notification = Notification(
        id=success_event.id,
        status=success_event.status,
        event=success_event,
        sections=[],
        action_buttons=[],
    )

    trial_event = PaymentEvent(
        id="evt_125",
        event_type="trial_end",
        customer_id="cust_123",
        amount=0,
        currency="USD",
        status="active",
        timestamp=datetime.now(),
        metadata={},
    )

    trial_notification = Notification(
        id=trial_event.id,
        status=trial_event.status,
        event=trial_event,
        sections=[],
        action_buttons=[],
    )

    assert failure_notification.to_slack_message()["color"] == "#dc3545"  # Red
    assert success_notification.to_slack_message()["color"] == "#36a64f"  # Green
    assert trial_notification.to_slack_message()["color"] == "#ffc107"  # Yellow
