import pytest
import json
from unittest.mock import Mock, patch
from flask import Request


@pytest.fixture
def mock_webhook_validation():
    """Mock webhook validation for tests"""

    def mock_format_notification(*args, **kwargs):
        return {"blocks": [], "color": "#28a745"}

    with patch(
        "app.event_processor.EventProcessor.format_notification",
        mock_format_notification,
    ):
        yield mock_format_notification


@pytest.fixture
def app():
    """Create a test Flask app"""
    test_config = {
        "TESTING": True,
        "SLACK_WEBHOOK_URL": "https://hooks.slack.com/test",
        "CHARGIFY_WEBHOOK_SECRET": "test_secret",
        "SHOPIFY_WEBHOOK_SECRET": "test_secret",
        "SHOPIFY_SHOP_URL": "test.myshopify.com",
        "SHOPIFY_ACCESS_TOKEN": "test_token",
    }
    from app import create_app

    app = create_app(test_config)
    return app


@pytest.fixture
def client(app):
    """Create a test client"""
    return app.test_client()


@pytest.fixture
def mock_slack_response():
    """Mock successful Slack API response"""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"ok": True}
    return mock_response


@pytest.fixture
def mock_shopify_request():
    """Mock Shopify webhook request"""
    mock_request = Mock(spec=Request)
    mock_request.content_type = "application/json"
    mock_request.headers = {
        "X-Shopify-Topic": "orders/paid",
        "X-Shopify-Shop-Domain": "test.myshopify.com",
        "X-Shopify-Hmac-SHA256": "test_signature",
        "X-Shopify-Order-Id": "123456789",
        "X-Shopify-Api-Version": "2024-01",
    }
    mock_data = {
        "id": 123456789,
        "order_number": 1001,
        "customer": {
            "id": 456,
            "email": "test@example.com",
            "first_name": "Test",
            "last_name": "User",
            "company": "Test Company",
            "orders_count": 5,
            "total_spent": "299.95",
        },
        "total_price": "29.99",
        "currency": "USD",
        "financial_status": "paid",
    }
    mock_request.data = json.dumps(mock_data).encode("utf-8")
    mock_request.get_json.return_value = mock_data
    return mock_request


@pytest.fixture
def mock_shopify_customer_request():
    """Mock Shopify customer webhook request"""
    mock_request = Mock(spec=Request)
    mock_request.content_type = "application/json"
    mock_request.headers = {
        "X-Shopify-Topic": "customers/update",
        "X-Shopify-Shop-Domain": "test.myshopify.com",
        "X-Shopify-Hmac-SHA256": "test_signature",
    }
    mock_data = {
        "id": 456,
        "email": "test@example.com",
        "accepts_marketing": True,
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-03-15T10:00:00Z",
        "first_name": "Test",
        "last_name": "User",
        "company": "Updated Company Name",
        "orders_count": 10,
        "total_spent": "599.90",
        "note": "Enterprise customer, upgraded plan",
        "tags": ["enterprise", "priority", "annual"],
        "addresses": [
            {
                "id": 1,
                "company": "Updated Company Name",
                "country": "United States",
                "country_code": "US",
            }
        ],
        "metafields": [
            {
                "key": "team_size",
                "value": "50",
                "namespace": "customer",
            },
            {
                "key": "plan_type",
                "value": "enterprise_annual",
                "namespace": "subscription",
            },
        ],
    }
    mock_request.data = json.dumps(mock_data).encode("utf-8")
    mock_request.get_json.return_value = mock_data
    return mock_request


@pytest.fixture
def mock_chargify_request():
    """Mock Chargify webhook request"""
    mock_request = Mock(spec=Request)
    mock_request.content_type = "application/x-www-form-urlencoded"
    mock_request.headers = {
        "X-Chargify-Webhook-Id": "test_webhook_1",
        "X-Chargify-Webhook-Signature-Hmac-Sha-256": "test_signature",
    }
    mock_request.form = Mock()
    mock_request.form.to_dict.return_value = {
        "event": "payment_success",
        "id": "12345",
        "payload[subscription][id]": "sub_789",
        "payload[subscription][customer][id]": "cust_123",
        "payload[subscription][customer][email]": "test@example.com",
        "payload[subscription][customer][first_name]": "Test",
        "payload[subscription][customer][last_name]": "User",
        "payload[subscription][customer][organization]": "Test Co",
        "payload[subscription][product][name]": "Enterprise Plan",
        "payload[transaction][amount_in_cents]": "10000",
        "created_at": "2024-03-15T10:00:00Z",
    }
    return mock_request
