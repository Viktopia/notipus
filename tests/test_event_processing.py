import pytest

from app.webhooks.services.event_processor import EventProcessor
from app.webhooks.models.notification import Notification


def test_notification_formatting():
    """Test that notifications are properly formatted"""
    processor = EventProcessor()

    event_data = {
        "type": "payment_success",
        "customer_id": "cust_123",
        "amount": 29.99,
        "currency": "USD",
        "status": "success",
        "metadata": {
            "subscription_id": "sub_123",
            "plan": "enterprise",
        },
    }

    customer_data = {
        "company_name": "Acme Corp",
        "team_size": "50",
        "plan_name": "Enterprise",
    }

    notification = processor.format_notification(event_data, customer_data)
    assert isinstance(notification, Notification)
    assert notification.title == "Payment Received: $29.99"
    assert notification.status == "success"
    assert notification.color == "#28a745"  # Green
    assert (
        len(notification.sections) == 3
    )  # Event Details, Customer Details, Additional Details


def test_missing_required_customer_data():
    """Test handling of missing required customer data"""
    processor = EventProcessor()

    event_data = {
        "type": "payment_success",
        "customer_id": "cust_123",
        "amount": 29.99,
        "currency": "USD",
        "status": "success",
    }

    customer_data = {
        "team_size": "50",  # Missing company_name
        "plan_name": "Enterprise",
    }

    # No longer raises an error since company defaults to 'Individual'
    notification = processor.format_notification(event_data, customer_data)
    company_field = next(
        (field for field in notification.sections[1].fields if field[0] == "Company"),
        None,
    )
    assert company_field is not None
    assert company_field[1] == "Individual"


def test_invalid_event_type():
    """Test handling of invalid event type"""
    processor = EventProcessor()

    event_data = {
        "type": "invalid_event",
        "customer_id": "cust_123",
        "amount": 29.99,
    }

    customer_data = {
        "company_name": "Acme Corp",
        "team_size": "50",
        "plan_name": "Enterprise",
    }

    with pytest.raises(ValueError, match="Invalid event type"):
        processor.process_event(event_data, customer_data)


def test_missing_event_data():
    """Test handling of missing event data"""
    processor = EventProcessor()

    customer_data = {
        "company_name": "Acme Corp",
        "team_size": "50",
        "plan_name": "Enterprise",
    }

    with pytest.raises(ValueError, match="Missing event data"):
        processor.format_notification(None, customer_data)


def test_missing_customer_data():
    """Test handling of missing customer data"""
    processor = EventProcessor()

    event_data = {
        "type": "payment_success",
        "customer_id": "cust_123",
        "amount": 29.99,
    }

    with pytest.raises(ValueError, match="Missing customer data"):
        processor.format_notification(event_data, None)


def test_negative_amount():
    """Test handling of negative amount"""
    processor = EventProcessor()

    event_data = {
        "type": "payment_success",
        "customer_id": "cust_123",
        "amount": -29.99,
        "currency": "USD",
        "status": "success",
    }

    customer_data = {
        "company_name": "Acme Corp",
        "team_size": "50",
        "plan_name": "Enterprise",
    }

    with pytest.raises(ValueError, match="Amount cannot be negative"):
        processor.format_notification(event_data, customer_data)


def test_invalid_currency():
    """Test handling of invalid currency"""
    processor = EventProcessor()

    event_data = {
        "type": "payment_success",
        "customer_id": "cust_123",
        "amount": 29.99,
        "currency": "XXX",  # Invalid currency
        "status": "success",
    }

    customer_data = {
        "company_name": "Acme Corp",
        "team_size": "50",
        "plan_name": "Enterprise",
    }

    with pytest.raises(ValueError, match="Invalid currency"):
        processor.format_notification(event_data, customer_data)
