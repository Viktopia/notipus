import pytest
from unittest.mock import Mock, patch
from django.test.client import RequestFactory
from django.urls import reverse


@pytest.fixture
def mock_webhook_validation():
    """Mock webhook validation for tests"""

    def mock_format_notification(*args, **kwargs):
        return {"blocks": [], "color": "#28a745"}

    with patch(
        "app.webhooks.event_processor.EventProcessor.format_notification",
        mock_format_notification,
    ):
        yield mock_format_notification


@pytest.fixture
def client():
    """Django test client"""
    from django.test import Client

    return Client()


@pytest.fixture
def request_factory():
    """Django RequestFactory for mocking requests"""
    return RequestFactory()


@pytest.fixture
def mock_slack_response():
    """Mock successful Slack API response"""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"ok": True}
    return mock_response


@pytest.fixture
def mock_shopify_request(request_factory):
    """Mock Shopify webhook request"""
    headers = {
        "X-Shopify-Topic": "orders/paid",
        "X-Shopify-Shop-Domain": "test.myshopify.com",
        "X-Shopify-Hmac-SHA256": "test_signature",
        "X-Shopify-Order-Id": "123456789",
        "X-Shopify-Api-Version": "2024-01",
    }
    data = {
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
    request = request_factory.post(
        reverse("shopify_webhook"),
        data=data,
        content_type="application/json",
        **headers,
    )
    return request


@pytest.fixture
def mock_shopify_customer_request(request_factory):
    """Mock Shopify customer webhook request"""
    headers = {
        "X-Shopify-Topic": "customers/update",
        "X-Shopify-Shop-Domain": "test.myshopify.com",
        "X-Shopify-Hmac-SHA256": "test_signature",
    }
    data = {
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
    request = request_factory.post(
        reverse("shopify_customer_webhook"),
        data=data,
        content_type="application/json",
        **headers,
    )
    return request


@pytest.fixture
def mock_chargify_request(request_factory):
    """Mock Chargify webhook request"""
    headers = {
        "X-Chargify-Webhook-Id": "test_webhook_1",
        "X-Chargify-Webhook-Signature-Hmac-Sha-256": "test_signature",
    }
    data = {
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
    request = request_factory.post(
        reverse("chargify_webhook"),
        data=data,
        content_type="application/x-www-form-urlencoded",
        **headers,
    )
    return request
