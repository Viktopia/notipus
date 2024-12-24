import json
from unittest.mock import patch, MagicMock

import pytest
import requests
from app import create_app
from app.models import Notification, Section
from app.event_processor import EventProcessor
from app.providers import ChargifyProvider, ShopifyProvider


@pytest.fixture
def mock_webhook_validation(monkeypatch):
    """Mock webhook validation and parsing"""

    def mock_format_notification(event_data, customer_data):
        """Mock notification formatting"""
        if not event_data or not customer_data:
            raise ValueError("Missing required data")

        # Map event types
        event_type = event_data.get("type")
        if event_type == "subscription_state_change":
            event_type = "subscription_canceled"
        elif event_type == "customers/update":
            event_type = "customer_updated"

        if event_type not in EventProcessor.VALID_EVENT_TYPES:
            raise ValueError("Invalid event type")

        title = "Test Notification"
        sections = []

        if event_type == "payment_failure":
            title = "Payment Failed"
            sections = [
                Section(
                    title="Payment Details",
                    fields={
                        "Status": "Failed",
                        "Amount": f"${event_data.get('amount', 0):.2f}",
                    },
                )
            ]
        elif event_data.get("type") == "payment_success":
            title = "Payment Received"
            sections = [
                Section(
                    title="Payment Details",
                    fields={
                        "Status": "Success",
                        "Amount": f"${event_data.get('amount', 0):.2f}",
                    },
                )
            ]
        elif event_data.get("type") == "subscription_cancelled":
            title = "Subscription Cancelled"
            sections = [
                Section(
                    title="Subscription Details",
                    fields={
                        "Status": "Cancelled",
                        "Plan": event_data.get("plan_name", "Unknown"),
                    },
                )
            ]
        else:
            sections = [
                Section(
                    title="Event Details",
                    fields={
                        "Type": event_data.get("type", "Unknown"),
                        "Status": event_data.get("status", "Unknown"),
                    },
                )
            ]

        sections.append(
            Section(
                title="Customer Details",
                fields={
                    "Company": customer_data.get("company_name", "Unknown"),
                    "Email": customer_data.get("email", "Unknown"),
                },
            )
        )

        notification = Notification(
            title=title,
            sections=sections,
            color="#36a64f",  # Green for success
            emoji="🎉",
        )
        notification.status = event_data.get("status", "info")
        return notification

    monkeypatch.setattr(
        "app.event_processor.EventProcessor.format_notification",
        mock_format_notification,
    )

    return mock_format_notification


@pytest.fixture
def app(mock_webhook_validation):
    """Create a test Flask app"""
    test_config = {
        "TESTING": True,
        "SLACK_WEBHOOK_URL": "https://hooks.slack.com/test",
        "CHARGIFY_WEBHOOK_SECRET": "test_secret",
        "SHOPIFY_WEBHOOK_SECRET": "test_secret",
        "SHOPIFY_SHOP_URL": "test.myshopify.com",
        "SHOPIFY_ACCESS_TOKEN": "test_token",
    }
    app = create_app(test_config)

    # Initialize providers with mocked validation
    app.chargify_provider = ChargifyProvider(webhook_secret="test_secret")
    app.shopify_provider = ShopifyProvider(webhook_secret="test_secret")

    # Mock validate_webhook for both providers
    app.chargify_provider.validate_webhook = lambda x: True
    app.shopify_provider.validate_webhook = lambda x: True

    # Mock the event processor
    processor = MagicMock()
    processor.format_notification = mock_webhook_validation
    app.event_processor = processor

    return app


@pytest.fixture
def client(app):
    """Create a test client for the Flask app"""
    return app.test_client()


@pytest.fixture
def mock_slack_response():
    """Mock a successful Slack API response"""
    mock = MagicMock()
    mock.status_code = 200
    mock.ok = True
    mock.raise_for_status.return_value = None
    return mock


@pytest.fixture
def mock_failed_slack_response():
    """Mock a failed Slack API response"""
    mock = MagicMock()
    mock.ok = False
    mock.status_code = 500
    mock.text = "Slack API error"
    mock.raise_for_status.side_effect = requests.exceptions.RequestException(
        "Failed to send notification"
    )
    return mock


def test_shopify_webhook_success(client, mock_slack_response, mock_webhook_validation):
    """Test successful Shopify webhook processing"""
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
            "note": "Enterprise customer",
            "tags": ["enterprise", "priority"],
            "default_address": {
                "company": "Test Company",
                "country": "United States",
                "country_code": "US",
            },
            "metafields": [
                {
                    "key": "team_size",
                    "value": "25",
                    "namespace": "customer",
                },
                {
                    "key": "plan_type",
                    "value": "enterprise_annual",
                    "namespace": "subscription",
                },
            ],
        },
        "total_price": "29.99",
        "subtotal_price": "24.99",
        "total_tax": "5.00",
        "currency": "USD",
        "financial_status": "paid",
        "fulfillment_status": "fulfilled",
        "created_at": "2024-03-15T10:00:00Z",
        "updated_at": "2024-03-15T10:05:00Z",
        "line_items": [
            {
                "id": 789,
                "title": "Enterprise Plan",
                "quantity": 1,
                "price": "29.99",
                "sku": "ENT-PLAN-1",
                "properties": [
                    {"name": "team_size", "value": "25"},
                    {"name": "plan_type", "value": "annual"},
                ],
            }
        ],
    }

    with patch("requests.post", return_value=mock_slack_response):
        response = client.post(
            "/webhook/shopify",
            data=json.dumps(data),
            content_type="application/json",
            headers={
                "X-Shopify-Topic": "orders/paid",
                "X-Shopify-Shop-Domain": "test.myshopify.com",
                "X-Shopify-Hmac-SHA256": "test_signature",
                "X-Shopify-Order-Id": "123456789",
                "X-Shopify-Api-Version": "2024-01",
                "User-Agent": "Shopify Webhooks/v1.0",
            },
        )

        assert response.status_code == 200
        assert response.json["status"] == "success"


def test_shopify_webhook_missing_topic(client):
    """Test Shopify webhook without topic header"""
    response = client.post(
        "/webhook/shopify",
        data=json.dumps({}),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "Missing webhook topic" in response.json["error"]


def test_chargify_webhook_success(client, mock_slack_response, mock_webhook_validation):
    """Test successful Chargify webhook processing"""
    data = {
        "event": "payment_success",
        "payload[subscription][id]": "sub_12345",
        "payload[subscription][state]": "active",
        "payload[subscription][customer][id]": "cust_456",
        "payload[subscription][customer][email]": "test@example.com",
        "payload[subscription][customer][first_name]": "Test",
        "payload[subscription][customer][last_name]": "User",
        "payload[subscription][customer][organization]": "Test Company",
        "payload[subscription][product][id]": "prod_789",
        "payload[subscription][product][name]": "Enterprise Plan",
        "payload[subscription][product][handle]": "enterprise",
        "payload[transaction][id]": "tr_123",
        "payload[transaction][amount_in_cents]": "4999",
        "payload[transaction][type]": "payment",
        "payload[transaction][success]": "true",
        "created_at": "2024-03-15T10:00:00Z",
    }

    with patch("requests.post", return_value=mock_slack_response):
        response = client.post(
            "/webhook/chargify",
            data=data,
            content_type="application/x-www-form-urlencoded",
            headers={
                "X-Chargify-Webhook-Signature-Hmac-Sha-256": "test_signature",
                "X-Chargify-Webhook-Id": "webhook_123",
                "User-Agent": "Chargify Webhooks",
            },
        )

        assert response.status_code == 200
        assert response.json["status"] == "success"


def test_chargify_webhook_wrong_content_type(client, mock_webhook_validation):
    """Test Chargify webhook with wrong content type"""
    response = client.post(
        "/webhook/chargify",
        data=json.dumps({}),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "Invalid content type" in response.json["error"]


def test_shopify_webhook_slack_failure(client, mock_failed_slack_response):
    """Test Shopify webhook with Slack API failure"""
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
            "note": "Enterprise customer",
            "tags": ["enterprise", "priority"],
        },
        "total_price": "29.99",
        "subtotal_price": "24.99",
        "total_tax": "5.00",
        "currency": "USD",
        "financial_status": "paid",
        "fulfillment_status": "fulfilled",
        "created_at": "2024-03-15T10:00:00Z",
        "updated_at": "2024-03-15T10:05:00Z",
        "line_items": [
            {
                "id": 789,
                "title": "Enterprise Plan",
                "quantity": 1,
                "price": "29.99",
                "sku": "ENT-PLAN-1",
                "properties": [
                    {"name": "team_size", "value": "25"},
                    {"name": "plan_type", "value": "annual"},
                ],
            }
        ],
    }

    with patch("requests.post", return_value=mock_failed_slack_response):
        response = client.post(
            "/webhook/shopify",
            data=json.dumps(data),
            content_type="application/json",
            headers={
                "X-Shopify-Topic": "orders/paid",
                "X-Shopify-Shop-Domain": "test.myshopify.com",
                "X-Shopify-Hmac-SHA256": "test_signature",
                "X-Shopify-Order-Id": "123456789",
                "X-Shopify-Api-Version": "2024-01",
                "User-Agent": "Shopify Webhooks/v1.0",
            },
        )

        assert response.status_code == 500
        assert "Failed to send notification" in response.json["error"]


def test_chargify_subscription_cancel(
    client, mock_slack_response, mock_webhook_validation
):
    """Test Chargify subscription cancellation webhook"""
    data = {
        "event": "subscription_state_change",
        "payload[subscription][id]": "sub_12345",
        "payload[subscription][state]": "canceled",
        "payload[subscription][cancel_at_end_of_period]": "true",
        "payload[subscription][customer][id]": "cust_456",
        "payload[subscription][customer][email]": "test@example.com",
        "payload[subscription][customer][organization]": "Test Company",
        "payload[subscription][product][name]": "Enterprise Plan",
        "payload[subscription][product][handle]": "enterprise",
        "payload[subscription][total_revenue_in_cents]": "299900",
        "created_at": "2024-03-15T10:00:00Z",
    }

    with patch("requests.post", return_value=mock_slack_response):
        response = client.post(
            "/webhook/chargify",
            data=data,
            content_type="application/x-www-form-urlencoded",
            headers={
                "X-Chargify-Webhook-Signature-Hmac-Sha-256": "test_signature",
                "X-Chargify-Webhook-Id": "webhook_123",
                "User-Agent": "Chargify Webhooks",
            },
        )

        assert response.status_code == 200
        assert response.json["status"] == "success"


def test_shopify_customer_update(client, mock_slack_response, mock_webhook_validation):
    """Test Shopify customer update webhook"""
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

    with patch("requests.post", return_value=mock_slack_response):
        response = client.post(
            "/webhook/shopify",
            data=json.dumps(data),
            content_type="application/json",
            headers={
                "X-Shopify-Topic": "customers/update",
                "X-Shopify-Shop-Domain": "test.myshopify.com",
                "X-Shopify-Hmac-SHA256": "test_signature",
                "X-Shopify-Api-Version": "2024-01",
                "User-Agent": "Shopify Webhooks/v1.0",
            },
        )

        assert response.status_code == 200
        assert response.json["status"] == "success"


def test_health_check(client):
    """Test health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json["status"] == "healthy"
