"""Tests for event processing and notification formatting.

This module tests the EventProcessor class for handling various
webhook events and generating properly formatted notifications.
"""

from typing import Any

import pytest
from webhooks.models.notification import Notification
from webhooks.services.event_processor import EventProcessor


def test_notification_formatting() -> None:
    """Test that notifications are properly formatted.

    Verifies a payment success event generates a valid notification
    with correct title, color, and sections.
    """
    processor = EventProcessor()

    event_data: dict[str, Any] = {
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

    customer_data: dict[str, Any] = {
        "company_name": "Acme Corp",
        "team_size": "50",
        "plan_name": "Enterprise",
    }

    notification = processor.format_notification(event_data, customer_data)
    assert isinstance(notification, Notification)
    assert notification.title == "💰 Payment received from Acme Corp"
    assert notification.color == "#28a745"  # Green
    assert len(notification.sections) == 2  # Main event details + customer info


def test_missing_required_customer_data() -> None:
    """Test handling of missing required customer data.

    Verifies company name defaults to 'Individual' when not provided.
    """
    processor = EventProcessor()

    event_data: dict[str, Any] = {
        "type": "payment_success",
        "customer_id": "cust_123",
        "amount": 29.99,
        "currency": "USD",
        "status": "success",
    }

    customer_data: dict[str, Any] = {
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


def test_invalid_event_type() -> None:
    """Test handling of invalid event type.

    Verifies ValueError is raised for unrecognized event types.
    """
    processor = EventProcessor()

    event_data: dict[str, Any] = {
        "type": "invalid_event",
        "customer_id": "cust_123",
        "amount": 29.99,
    }

    customer_data: dict[str, Any] = {
        "company_name": "Acme Corp",
        "team_size": "50",
        "plan_name": "Enterprise",
    }

    with pytest.raises(ValueError, match="Invalid event type"):
        processor.process_event(event_data, customer_data)


def test_missing_event_data() -> None:
    """Test handling of missing event data.

    Verifies ValueError is raised when event_data is None.
    """
    processor = EventProcessor()

    customer_data: dict[str, Any] = {
        "company_name": "Acme Corp",
        "team_size": "50",
        "plan_name": "Enterprise",
    }

    with pytest.raises(ValueError, match="Missing event data"):
        processor.format_notification(None, customer_data)


def test_missing_customer_data() -> None:
    """Test handling of missing customer data.

    Verifies ValueError is raised when customer_data is None.
    """
    processor = EventProcessor()

    event_data: dict[str, Any] = {
        "type": "payment_success",
        "customer_id": "cust_123",
        "amount": 29.99,
    }

    with pytest.raises(ValueError, match="Missing customer data"):
        processor.format_notification(event_data, None)


def test_negative_amount() -> None:
    """Test handling of negative amount.

    Verifies ValueError is raised for negative payment amounts.
    """
    processor = EventProcessor()

    event_data: dict[str, Any] = {
        "type": "payment_success",
        "customer_id": "cust_123",
        "amount": -29.99,
        "currency": "USD",
        "status": "success",
    }

    customer_data: dict[str, Any] = {
        "company_name": "Acme Corp",
        "team_size": "50",
        "plan_name": "Enterprise",
    }

    with pytest.raises(ValueError, match="Amount cannot be negative"):
        processor.format_notification(event_data, customer_data)


def test_invalid_currency() -> None:
    """Test handling of invalid currency.

    Verifies ValueError is raised for unsupported currency codes.
    """
    processor = EventProcessor()

    event_data: dict[str, Any] = {
        "type": "payment_success",
        "customer_id": "cust_123",
        "amount": 29.99,
        "currency": "XXX",  # Invalid currency
        "status": "success",
    }

    customer_data: dict[str, Any] = {
        "company_name": "Acme Corp",
        "team_size": "50",
        "plan_name": "Enterprise",
    }

    with pytest.raises(ValueError, match="Invalid currency"):
        processor.format_notification(event_data, customer_data)
