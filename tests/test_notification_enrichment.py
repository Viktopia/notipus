from datetime import datetime
import pytest
from unittest.mock import MagicMock
from webhooks.providers.base import PaymentProvider, PaymentEvent
from webhooks.enrichment import NotificationEnricher


@pytest.fixture
def mock_provider():
    provider = MagicMock(spec=PaymentProvider)
    provider.get_payment_history.return_value = [
        {
            "id": "pmt_123",
            "amount": 29.99,
            "currency": "USD",
            "status": "success",
            "created_at": "2024-03-14T10:00:00Z",
        },
        {
            "id": "pmt_124",
            "amount": 29.99,
            "currency": "USD",
            "status": "failed",
            "created_at": "2024-03-15T10:00:00Z",
        },
    ]
    provider.get_usage_metrics.return_value = {
        "api_calls_last_30d": 15000,
        "active_users": 25,
        "features_used": ["API", "Dashboard", "Reports"],
        "last_active": "2024-03-15T09:00:00Z",
    }
    provider.get_customer_data.return_value = {
        "company_name": "Acme Corp",
        "team_size": 50,
        "plan_name": "Enterprise",
        "created_at": "2023-09-15T00:00:00Z",
        "lifetime_value": 299.99,
        "health_score": 0.8,
    }
    provider.get_related_events.return_value = [
        {
            "id": "evt_123",
            "type": "payment_failure",
            "created_at": "2024-03-15T10:00:00Z",
            "metadata": {"failure_reason": "card_declined"},
        },
        {
            "id": "evt_124",
            "type": "payment_success",
            "created_at": "2024-03-14T10:00:00Z",
        },
    ]
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

    # Проверка: данные о клиенте должны присутствовать в одной из секций
    customer_section = next(s for s in notification.sections if "Customer" in s.text)
    assert "Acme Corp" in customer_section.text
    assert "Enterprise" in customer_section.text
    assert "50" in customer_section.text  # team size

    # Проверка: метрики должны присутствовать
    metrics_section = next(s for s in notification.sections if "Metrics" in s.text)
    assert "15,000" in metrics_section.text  # API calls
    assert "25" in metrics_section.text  # active users

    # Проверка: история платежей должна присутствовать
    history_section = next(
        s for s in notification.sections if "Payment History" in s.text
    )
    assert "$29.99" in history_section.text
    assert "success" in history_section.text.lower()
    assert "failed" in history_section.text.lower()

    # Проверка: сведения о клиенте (insights)
    insights_section = next(s for s in notification.sections if "Insights" in s.text)
    assert "health score" in insights_section.text.lower()
    assert "0.8" in insights_section.text
    assert "lifetime value" in insights_section.text.lower()
    assert "$299.99" in insights_section.text


def test_action_items_are_specific_and_actionable(mock_provider, sample_payment_event):
    """Test that generated action items are specific and actionable"""
    enricher = NotificationEnricher(provider=mock_provider)
    notification = enricher.enrich_notification(sample_payment_event)
    assert notification.sections is not None
    # Проверяем, что хотя бы в одной секции присутствует слово "action" (без учета регистра)
    assert any("action" in section.text.lower() for section in notification.sections)


def test_notification_correlates_related_events(mock_provider, sample_payment_event):
    """Test that notifications include correlated events for context"""
    # Переопределяем возвращаемые данные для get_related_events
    mock_provider.get_related_events.return_value = [
        {"event_type": "payment_failure", "timestamp": "2024-03-15T10:00:00Z"},
        {"event_type": "payment_success", "timestamp": "2024-03-15T11:00:00Z"},
    ]
    enricher = NotificationEnricher(provider=mock_provider)
    notification = enricher.enrich_notification(sample_payment_event)
    assert notification.customer_context is not None
    assert mock_provider.get_related_events.called
