import json
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest
from app import create_app
import requests
from app.models import Notification, NotificationSection, PaymentEvent
from app.providers.base import InvalidDataError


@pytest.fixture
def mock_webhook_validation(monkeypatch):
    """Mock webhook validation and notification formatting"""

    def mock_validate(self, request):
        return True

    def mock_parse_shopify_webhook(self, request, **kwargs):
        data = request.get_json()
        webhook_topic = request.headers.get("X-Shopify-Topic", "orders/create")

        if not data:
            raise InvalidDataError("Missing required fields")

        if webhook_topic.startswith("orders/"):
            if "customer" not in data:
                raise InvalidDataError("Missing required fields")

            customer = data["customer"]
            # Extract team size from line items properties if available
            team_size = 0
            plan_name = "Unknown"
            for item in data.get("line_items", []):
                for prop in item.get("properties", []):
                    if prop.get("name") == "team_size":
                        try:
                            team_size = int(prop.get("value", 0))
                        except ValueError:
                            pass
                    elif prop.get("name") == "plan_type":
                        plan_name = prop.get("value", "Unknown")

            return {
                "id": str(data["id"]),
                "type": webhook_topic.replace("/", "_"),
                "customer_id": str(customer["id"]),
                "amount": float(data["total_price"]),
                "currency": data["currency"],
                "status": "success" if data["financial_status"] == "paid" else "failed",
                "timestamp": data["created_at"],
                "metadata": {
                    "source": "shopify",
                    "shop_domain": request.headers.get("X-Shopify-Shop-Domain"),
                    "order_number": data["order_number"],
                    "order_id": data["id"],
                    "customer_email": customer.get("email"),
                    "customer_name": (
                        f"{customer.get('first_name', '')} "
                        f"{customer.get('last_name', '')}"
                    ).strip(),
                    "plan_type": plan_name,
                },
                "customer_data": {
                    "company_name": customer.get("company", "Unknown"),
                    "team_size": team_size,
                    "plan_name": data.get("line_items", [{}])[0].get(
                        "title", "Unknown"
                    ),
                },
            }
        elif webhook_topic.startswith("customers/"):
            if "id" not in data:
                raise InvalidDataError("Missing required fields")

            # Extract team size and plan type from metafields if available
            team_size = 0
            plan_name = "Unknown"
            for metafield in data.get("metafields", []):
                if (
                    metafield.get("namespace") == "customer"
                    and metafield.get("key") == "team_size"
                ):
                    try:
                        team_size = int(metafield.get("value", 0))
                    except ValueError:
                        pass
                elif (
                    metafield.get("namespace") == "subscription"
                    and metafield.get("key") == "plan_type"
                ):
                    plan_name = metafield.get("value", "Unknown")

            return {
                "id": str(data["id"]),
                "type": webhook_topic.replace("/", "_"),
                "customer_id": str(data["id"]),
                "amount": float(data.get("total_spent", 0)),
                "currency": "USD",
                "status": "success",
                "timestamp": data["updated_at"],
                "metadata": {
                    "source": "shopify",
                    "shop_domain": request.headers.get("X-Shopify-Shop-Domain"),
                    "customer_email": data.get("email"),
                    "customer_name": (
                        f"{data.get('first_name', '')} {data.get('last_name', '')}"
                    ).strip(),
                    "tags": data.get("tags", []),
                    "orders_count": data.get("orders_count", 0),
                    "plan_type": plan_name,
                },
                "customer_data": {
                    "company_name": data.get("company", "Unknown"),
                    "team_size": team_size,
                    "plan_name": plan_name,
                },
            }

    def mock_parse_chargify_webhook(self, request):
        if request.content_type != "application/x-www-form-urlencoded":
            raise InvalidDataError("Invalid content type")

        data = request.form.to_dict()
        if not data:
            raise InvalidDataError("Empty webhook data")

        event_type = data.get("event")
        if not event_type:
            raise InvalidDataError("Missing required fields")

        customer_id = data.get("payload[subscription][customer][id]")
        if not customer_id:
            raise InvalidDataError("Missing required fields")

        status = "success"

        if "failure" in event_type:
            status = "failed"
        elif event_type == "subscription_state_change":
            status = data.get("payload[subscription][state]", "unknown")

        # Build metadata
        metadata = {
            "source": "chargify",
            "subscription_id": data.get("payload[subscription][id]"),
            "customer_email": data["payload[subscription][customer][email]"],
            "customer_name": (
                f"{data.get('payload[subscription][customer][first_name]', '')} "
                f"{data.get('payload[subscription][customer][last_name]', '')}"
            ).strip(),
        }

        # Add failure reason if available
        if status == "failed":
            failure_reason = (
                data.get("payload[transaction][failure_message]")
                or data.get("payload[transaction][memo]")
                or "Unknown error"
            )
            metadata["failure_reason"] = failure_reason

        # Add subscription state change metadata
        if event_type == "subscription_state_change":
            metadata["cancel_at_period_end"] = (
                data.get("payload[subscription][cancel_at_end_of_period]") == "true"
            )

        return {
            "id": f"evt_{customer_id}_{data.get('id', '')}",
            "type": event_type,
            "customer_id": str(customer_id),
            "amount": float(data.get("payload[transaction][amount_in_cents]", 0)) / 100,
            "currency": "USD",
            "status": status,
            "timestamp": data.get("created_at"),
            "metadata": metadata,
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
        # Extract event data from either positional or keyword args
        event_data = kwargs.get("event") if "event" in kwargs else args[0]

        # Create PaymentEvent object
        try:
            timestamp = datetime.fromisoformat(
                event_data["timestamp"].replace("Z", "+00:00")
            )
        except (ValueError, TypeError, KeyError):
            timestamp = datetime.now()

        payment_event = PaymentEvent(
            id=event_data["id"],
            event_type=event_data["type"],
            customer_id=event_data["customer_id"],
            amount=event_data["amount"],
            currency=event_data["currency"],
            status=event_data["status"],
            timestamp=timestamp,
            metadata=event_data["metadata"],
        )

        return Notification(
            id=payment_event.id,
            status=payment_event.status,
            event=payment_event,
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
