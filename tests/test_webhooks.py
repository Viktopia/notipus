import json
from unittest.mock import patch, MagicMock

import pytest
from app import create_app
import requests
from app.models import Notification, NotificationSection
from app.providers.base import InvalidDataError


@pytest.fixture
def mock_webhook_validation(monkeypatch):
    """Mock webhook validation and notification formatting"""

    def mock_validate(self, request):
        return True

    def mock_parse_shopify_webhook(self, request, **kwargs):
        data = request.get_json()
        webhook_topic = request.headers.get("X-Shopify-Topic", "orders/create")
        return {
            "id": str(data["id"]),
            "type": webhook_topic.replace("/", "_"),
            "customer_id": str(data["customer"]["id"]),
            "amount": float(data["total_price"]),
            "currency": data["currency"],
            "status": "success" if data["financial_status"] == "paid" else "failed",
            "timestamp": data["created_at"],
            "metadata": {
                "source": "shopify",
                "order_id": data["id"],
                "customer_email": data["customer"].get("email"),
            },
            "customer_data": {
                "company_name": data["customer"].get("company", "Unknown"),
                "team_size": data["customer"].get("team_size", 0),
                "plan_name": "Unknown",
            },
        }

    def mock_parse_chargify_webhook(self, request):
        if request.content_type != "application/x-www-form-urlencoded":
            raise InvalidDataError("Invalid content type")

        data = request.form.to_dict()
        return {
            "id": f"evt_{data.get('payload[subscription][customer][id]', 'unknown')}",
            "type": data["event"],
            "customer_id": data["payload[subscription][customer][id]"],
            "amount": float(data["payload[transaction][amount_in_cents]"]) / 100,
            "currency": "USD",
            "status": "success" if "success" in data["event"] else "failed",
            "timestamp": data.get("created_at"),
            "metadata": {
                "source": "chargify",
                "customer_email": data["payload[subscription][customer][email]"],
            },
            "customer_data": {
                "company_name": data.get(
                    "payload[subscription][customer][organization]", "Unknown"
                ),
                "team_size": 0,
                "plan_name": data.get(
                    "payload[subscription][product][name]", "Unknown"
                ),
            },
        }

    def mock_format_notification(*args, **kwargs):
        """Mock notification formatting"""
        # Extract event from either positional or keyword args
        event = kwargs.get("event") if "event" in kwargs else args[0]
        return Notification(
            id=event.id,
            status=event.status,
            event=event,
            sections=[NotificationSection(text="Test notification")],
            action_buttons=[],
        )

    monkeypatch.setattr(
        "app.providers.chargify.ChargifyProvider.validate_webhook", mock_validate
    )
    monkeypatch.setattr(
        "app.providers.shopify.ShopifyProvider.validate_webhook", mock_validate
    )
    monkeypatch.setattr(
        "app.providers.chargify.ChargifyProvider.parse_webhook",
        mock_parse_chargify_webhook,
    )
    monkeypatch.setattr(
        "app.providers.shopify.ShopifyProvider.parse_webhook",
        mock_parse_shopify_webhook,
    )
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
    }
    app = create_app(test_config)

    # Initialize providers
    from app.providers import ChargifyProvider, ShopifyProvider

    app.chargify_provider = ChargifyProvider(webhook_secret="test_secret")
    app.shopify_provider = ShopifyProvider(webhook_secret="test_secret")

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
        "id": 123,
        "customer": {
            "id": "cust_123",
            "email": "test@example.com",
            "first_name": "Test",
            "last_name": "User",
            "company": "Test Co",
            "team_size": 5,
        },
        "total_price": "29.99",
        "currency": "USD",
        "financial_status": "paid",
        "created_at": "2024-03-15T10:00:00Z",
    }

    with patch("requests.post", return_value=mock_slack_response):
        response = client.post(
            "/webhooks/shopify",
            data=json.dumps(data),
            content_type="application/json",
            headers={
                "X-Shopify-Topic": "orders/create",
                "X-Shopify-Shop-Domain": "test.myshopify.com",
                "X-Shopify-Hmac-SHA256": "test_signature",
            },
        )

        assert response.status_code == 200
        assert response.json["status"] == "success"


def test_shopify_webhook_missing_topic(client):
    """Test Shopify webhook without topic header"""
    response = client.post(
        "/webhooks/shopify",
        data=json.dumps({}),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "Missing webhook topic" in response.json["error"]


def test_chargify_webhook_success(client, mock_slack_response, mock_webhook_validation):
    """Test successful Chargify webhook processing"""
    data = {
        "event": "payment_success",
        "payload[subscription][customer][id]": "cust_123",
        "payload[subscription][customer][email]": "test@example.com",
        "payload[subscription][customer][first_name]": "Test",
        "payload[subscription][customer][last_name]": "User",
        "payload[subscription][customer][organization]": "Test Co",
        "payload[subscription][product][name]": "Enterprise",
        "payload[transaction][amount_in_cents]": "4999",
        "created_at": "2024-03-15T10:00:00Z",
    }

    with patch("requests.post", return_value=mock_slack_response):
        response = client.post(
            "/webhooks/chargify",
            data=data,
            content_type="application/x-www-form-urlencoded",
            headers={
                "X-Chargify-Webhook-Signature-Hmac-Sha-256": "test_signature",
                "X-Chargify-Webhook-Id": "webhook_123",
            },
        )

        assert response.status_code == 200
        assert response.json["status"] == "success"


def test_chargify_webhook_wrong_content_type(client, mock_webhook_validation):
    """Test Chargify webhook with wrong content type"""
    response = client.post(
        "/webhooks/chargify",
        data=json.dumps({}),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "Invalid content type" in response.json["error"]


def test_slack_notification_failure(
    client, mock_failed_slack_response, mock_webhook_validation
):
    """Test handling of Slack API failures"""
    data = {
        "id": 123,
        "customer": {
            "id": "cust_123",
            "email": "test@example.com",
            "first_name": "Test",
            "last_name": "User",
            "company": "Test Co",
            "team_size": 5,
        },
        "total_price": "29.99",
        "currency": "USD",
        "financial_status": "paid",
        "created_at": "2024-03-15T10:00:00Z",
    }

    mock_failed_slack_response.ok = False
    mock_failed_slack_response.status_code = 500
    mock_failed_slack_response.text = "Slack API error"
    mock_failed_slack_response.raise_for_status.side_effect = (
        requests.exceptions.RequestException("Failed to send notification")
    )

    with patch("requests.post", return_value=mock_failed_slack_response):
        response = client.post(
            "/webhooks/shopify",
            data=json.dumps(data),
            content_type="application/json",
            headers={
                "X-Shopify-Topic": "orders/create",
                "X-Shopify-Shop-Domain": "test.myshopify.com",
                "X-Shopify-Hmac-SHA256": "test_signature",
            },
        )

        assert response.status_code == 500
        assert "Failed to send notification" in response.json["error"]


def test_health_check(client):
    """Test health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json["status"] == "healthy"
