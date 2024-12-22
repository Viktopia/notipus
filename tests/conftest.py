import pytest
from unittest.mock import MagicMock


@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    """Mock environment variables for testing."""
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/test")
    monkeypatch.setenv("CHARGIFY_WEBHOOK_SECRET", "test_secret")
    monkeypatch.setenv("SHOPIFY_WEBHOOK_SECRET", "test_secret")


@pytest.fixture
def mock_slack_response():
    """Mock successful Slack API response."""
    response = MagicMock()
    response.status_code = 200
    response.raise_for_status.return_value = None
    return response


@pytest.fixture
def mock_failed_slack_response():
    """Mock failed Slack API response."""
    response = MagicMock()
    response.status_code = 500
    response.raise_for_status.side_effect = Exception("Slack API error")
    return response


@pytest.fixture
def sample_shopify_order():
    """Sample Shopify order data."""
    return {
        "id": "123",
        "contact_email": "john.doe@example.com",
        "created_at": "2024-03-15T10:00:00Z",
        "currency": "USD",
        "customer": {
            "id": "456",
            "first_name": "John",
            "last_name": "Doe",
            "email": "john.doe@example.com",
        },
        "total_price": "29.99",
        "financial_status": "paid",
    }


@pytest.fixture
def sample_chargify_payment():
    """Sample Chargify payment data."""
    return {
        "id": "67890",
        "event": "payment_success",
        "payload[subscription][customer][id]": "cust_123",
        "payload[subscription][customer][email]": "jane.smith@example.com",
        "payload[subscription][customer][first_name]": "Jane",
        "payload[subscription][customer][last_name]": "Smith",
        "payload[transaction][amount_in_cents]": "2999",
        "created_at": "2024-03-15T10:00:00Z",
    }


@pytest.fixture
def sample_chargify_failure():
    """Sample Chargify payment failure data."""
    return {
        "id": "67891",
        "event": "payment_failure",
        "payload[subscription][customer][id]": "cust_456",
        "payload[subscription][customer][email]": "alice.j@example.com",
        "payload[subscription][customer][first_name]": "Alice",
        "payload[subscription][customer][last_name]": "Johnson",
        "payload[transaction][amount_in_cents]": "4999",
        "retry_count": "2",
        "created_at": "2024-03-15T10:00:00Z",
    }


@pytest.fixture
def sample_chargify_trial_end():
    """Sample Chargify trial end data."""
    return {
        "id": "67892",
        "event": "trial_end",
        "payload[subscription][customer][id]": "cust_789",
        "payload[subscription][customer][email]": "bob.w@example.com",
        "payload[subscription][customer][first_name]": "Bob",
        "payload[subscription][customer][last_name]": "Wilson",
        "created_at": "2024-03-15T10:00:00Z",
    }
