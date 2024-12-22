import pytest
from unittest.mock import MagicMock

@pytest.fixture
def mock_slack_response():
    """Mock successful Slack API response"""
    mock_response = MagicMock()
    mock_response.status_code = 200
    return mock_response

@pytest.fixture
def mock_failed_slack_response():
    """Mock failed Slack API response"""
    mock_response = MagicMock()
    mock_response.status_code = 500
    return mock_response

@pytest.fixture
def sample_shopify_order():
    """Sample Shopify order data"""
    return {
        "id": "12345",
        "customer": {
            "first_name": "John",
            "last_name": "Doe"
        },
        "contact_email": "john.doe@example.com",
        "total_price": "99.99",
        "currency": "USD",
        "created_at": "2024-03-15T10:00:00Z",
        "financial_status": "paid",
        "fulfillment_status": "unfulfilled"
    }

@pytest.fixture
def sample_chargify_payment():
    """Sample Chargify payment data"""
    return {
        "id": "67890",
        "event": "payment_success",
        "payload[subscription][id]": "sub_123",
        "payload[subscription][customer][first_name]": "Jane",
        "payload[subscription][customer][last_name]": "Smith",
        "payload[subscription][customer][email]": "jane.smith@example.com",
        "payload[transaction][amount_in_cents]": "19999",
        "payload[transaction][currency]": "USD",
        "payload[transaction][created_at]": "2024-03-15T10:00:00Z"
    }

@pytest.fixture
def sample_chargify_failure():
    """Sample Chargify payment failure data"""
    return {
        "id": "67891",
        "event": "payment_failure",
        "payload[subscription][id]": "sub_124",
        "payload[subscription][customer][first_name]": "Alice",
        "payload[subscription][customer][last_name]": "Johnson",
        "payload[subscription][customer][email]": "alice.j@example.com",
        "payload[transaction][amount_in_cents]": "29999",
        "payload[transaction][currency]": "USD",
        "payload[transaction][created_at]": "2024-03-15T10:00:00Z"
    }

@pytest.fixture
def sample_chargify_trial_end():
    """Sample Chargify trial end data"""
    return {
        "id": "67892",
        "event": "trial_end",
        "payload[subscription][id]": "sub_125",
        "payload[subscription][customer][first_name]": "Bob",
        "payload[subscription][customer][last_name]": "Wilson",
        "payload[subscription][customer][email]": "bob.w@example.com",
        "payload[transaction][created_at]": "2024-03-15T10:00:00Z"
    }
