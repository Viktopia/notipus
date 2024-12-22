import pytest
from unittest.mock import patch
from app.providers.base import (
    PaymentProvider,
    PaymentEvent,
    WebhookValidationError,
    InvalidDataError,
)
from app.providers.chargify import ChargifyProvider
from app.providers.shopify import ShopifyProvider


def test_payment_provider_interface():
    """Test that payment providers implement the required interface"""
    providers = [
        ChargifyProvider(webhook_secret="test_secret"),
        ShopifyProvider(webhook_secret="test_secret"),
    ]

    for provider in providers:
        assert isinstance(provider, PaymentProvider)
        assert hasattr(provider, "validate_webhook")
        assert hasattr(provider, "parse_webhook")


def test_chargify_payment_failure_parsing():
    """Test that Chargify payment failure webhooks are properly parsed"""
    provider = ChargifyProvider(webhook_secret="test_secret")

    webhook_data = {
        "id": "evt_123",
        "event": "payment_failure",
        "payload[subscription][customer][id]": "cust_456",
        "payload[transaction][amount_in_cents]": "2999",
        "created_at": "2024-03-15T10:00:00Z",
    }

    event = provider.parse_webhook(webhook_data)
    assert isinstance(event, PaymentEvent)
    assert event.event_type == "payment_failure"
    assert event.customer_id == "cust_456"
    assert event.amount == 29.99


def test_shopify_order_parsing():
    """Test that Shopify order webhooks are properly parsed"""
    provider = ShopifyProvider(webhook_secret="test_secret")

    webhook_data = {
        "id": "123",
        "customer": {"id": "456", "email": "test@example.com"},
        "total_price": "29.99",
        "currency": "USD",
        "created_at": "2024-03-15T10:00:00Z",
        "financial_status": "paid",
    }

    event = provider.parse_webhook(webhook_data, topic="orders/create")
    assert isinstance(event, PaymentEvent)
    assert event.event_type == "order_created"
    assert event.customer_id == "456"
    assert event.amount == 29.99
    assert event.currency == "USD"


def test_chargify_webhook_validation():
    """Test Chargify webhook signature validation"""
    provider = ChargifyProvider(webhook_secret="test_secret")

    # Test valid signature
    body = b'{"test": "data"}'
    signature = "1234567890abcdef"  # This would be the actual HMAC-SHA256
    headers = {
        "X-Chargify-Webhook-Signature-Hmac-Sha-256": signature,
        "X-Chargify-Webhook-Id": "webhook_123",
    }

    with patch("hmac.compare_digest", return_value=True):
        assert provider.validate_webhook(headers, body) is True

    # Test missing signature
    with pytest.raises(WebhookValidationError):
        provider.validate_webhook({}, body)


def test_shopify_webhook_validation():
    """Test Shopify webhook signature validation"""
    provider = ShopifyProvider(webhook_secret="test_secret")

    # Test valid signature
    body = b'{"test": "data"}'
    signature = "1234567890abcdef"  # This would be the actual HMAC-SHA256
    headers = {
        "X-Shopify-Hmac-SHA256": signature,
        "X-Shopify-Topic": "orders/create",
        "X-Shopify-Shop-Domain": "test-shop.myshopify.com",
    }

    with patch("hmac.compare_digest", return_value=True):
        assert provider.validate_webhook(headers, body) is True

    # Test missing signature
    with pytest.raises(WebhookValidationError):
        provider.validate_webhook({}, body)


def test_invalid_webhook_data():
    """Test handling of invalid webhook data"""
    chargify = ChargifyProvider(webhook_secret="test_secret")
    shopify = ShopifyProvider(webhook_secret="test_secret")

    # Test missing required fields
    with pytest.raises(InvalidDataError):
        chargify.parse_webhook({})

    with pytest.raises(InvalidDataError):
        shopify.parse_webhook({})

    # Test invalid amount format
    with pytest.raises(InvalidDataError):
        chargify.parse_webhook(
            {
                "id": "123",
                "event": "payment_failure",
                "payload[transaction][amount_in_cents]": "invalid",
                "created_at": "2024-03-15T10:00:00Z",
            }
        )

    with pytest.raises(InvalidDataError):
        shopify.parse_webhook(
            {
                "id": "123",
                "total_price": "invalid",
                "created_at": "2024-03-15T10:00:00Z",
            },
            topic="orders/create",
        )
