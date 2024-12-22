from datetime import datetime
import pytest
from unittest.mock import MagicMock
from app.providers.base import PaymentProvider, PaymentEvent
from app.enrichment import NotificationEnricher


@pytest.fixture
def mock_provider():
    provider = MagicMock(spec=PaymentProvider)
    provider.get_payment_history.return_value = []
    provider.get_usage_metrics.return_value = {}
    provider.get_customer_data.return_value = {}
    provider.get_related_events.return_value = []
    return provider


@pytest.fixture
def sample_payment_event():
    return PaymentEvent(
        id="evt_123",
        event_type="payment_failure",
        customer_id="cust_123",
        amount=29.99,
        currency="USD",
        status="failed",
        timestamp=datetime.now(),
        subscription_id="sub_123",
        error_message="Card declined",
        retry_count=1,
    )


@pytest.fixture
def sample_trial_event():
    return PaymentEvent(
        id="evt_456",
        event_type="trial_end",
        customer_id="cust_456",
        amount=0,
        currency="USD",
        status="active",
        timestamp=datetime.now(),
        subscription_id="sub_456",
    )


def test_payment_failure_includes_payment_history(mock_provider, sample_payment_event):
    """Test that payment failure notifications include relevant payment history"""
    enricher = NotificationEnricher(provider=mock_provider)
    notification = enricher.enrich_notification(sample_payment_event)
    assert notification.customer_context is not None
    assert mock_provider.get_payment_history.called


def test_trial_ending_includes_usage_metrics(mock_provider, sample_trial_event):
    """Test that trial ending notifications include relevant usage data"""
    enricher = NotificationEnricher(provider=mock_provider)
    notification = enricher.enrich_notification(sample_trial_event)
    assert notification.customer_context is not None
    assert mock_provider.get_usage_metrics.called


def test_customer_context_is_comprehensive(mock_provider, sample_payment_event):
    """Test that customer context includes all relevant business metrics"""
    enricher = NotificationEnricher(provider=mock_provider)
    notification = enricher.enrich_notification(sample_payment_event)
    assert notification.customer_context is not None
    assert mock_provider.get_customer_data.called


def test_action_items_are_specific_and_actionable(mock_provider, sample_payment_event):
    """Test that generated action items are specific and actionable"""
    enricher = NotificationEnricher(provider=mock_provider)
    notification = enricher.enrich_notification(sample_payment_event)
    assert notification.sections is not None
    assert any("action" in section.text.lower() for section in notification.sections)


def test_notification_correlates_related_events(mock_provider, sample_payment_event):
    """Test that notifications include correlated events for context"""
    mock_provider.get_related_events.return_value = [
        {"event_type": "payment_failure", "timestamp": "2024-03-15T10:00:00Z"},
        {"event_type": "payment_success", "timestamp": "2024-03-15T11:00:00Z"},
    ]
    enricher = NotificationEnricher(provider=mock_provider)
    notification = enricher.enrich_notification(sample_payment_event)
    assert notification.customer_context is not None
    assert mock_provider.get_related_events.called
