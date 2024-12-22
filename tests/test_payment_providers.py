from unittest.mock import MagicMock, patch
from flask import Request

import pytest
from app.providers import PaymentProvider, ChargifyProvider, ShopifyProvider
from app.providers.base import InvalidDataError


def test_payment_provider_interface():
    """Test that payment providers implement the required interface"""
    providers = [
        ChargifyProvider(webhook_secret="test_secret"),
        ShopifyProvider(webhook_secret="test_secret"),
    ]

    for provider in providers:
        assert isinstance(provider, PaymentProvider)


def test_chargify_payment_failure_parsing():
    """Test that Chargify payment failure webhooks are properly parsed"""
    provider = ChargifyProvider(webhook_secret="test_secret")

    # Create a mock Flask request
    mock_request = MagicMock(spec=Request)
    mock_request.content_type = "application/x-www-form-urlencoded"
    mock_request.form = MagicMock()
    mock_request.form.to_dict.return_value = {
        "event": "payment_failure",
        "payload[subscription][customer][id]": "cust_456",
        "payload[subscription][customer][email]": "test@example.com",
        "payload[subscription][customer][first_name]": "Test",
        "payload[subscription][customer][last_name]": "User",
        "payload[transaction][amount_in_cents]": "2999",
        "created_at": "2024-03-15T10:00:00Z",
    }

    event = provider.parse_webhook(mock_request)
    assert event["type"] == "payment_failure"
    assert event["customer_id"] == "cust_456"
    assert event["amount"] == 29.99


def test_shopify_order_parsing():
    """Test that Shopify order webhooks are properly parsed"""
    provider = ShopifyProvider(webhook_secret="test_secret")

    # Create a mock Flask request
    mock_request = MagicMock(spec=Request)
    mock_request.content_type = "application/json"
    mock_request.headers = {
        "X-Shopify-Topic": "orders/create",
        "X-Shopify-Shop-Domain": "test.myshopify.com",
    }
    mock_request.get_json.return_value = {
        "id": "123",
        "customer": {"id": "456", "email": "test@example.com"},
        "total_price": "29.99",
        "currency": "USD",
        "created_at": "2024-03-15T10:00:00Z",
        "financial_status": "paid",
    }

    event = provider.parse_webhook(mock_request, topic="orders/create")
    assert event["type"] == "orders_create"
    assert event["customer_id"] == "456"
    assert event["amount"] == 29.99


def test_chargify_webhook_validation():
    """Test Chargify webhook signature validation"""
    provider = ChargifyProvider(webhook_secret="test_secret")

    # Create a mock Flask request
    mock_request = MagicMock(spec=Request)
    mock_request.headers = {
        "X-Chargify-Webhook-Signature-Hmac-Sha-256": "1234567890abcdef",
        "X-Chargify-Webhook-Id": "webhook_123",
    }
    mock_request.get_data.return_value = b'{"test": "data"}'

    with patch("hmac.compare_digest", return_value=True):
        assert provider.validate_webhook(mock_request) is True


def test_shopify_webhook_validation():
    """Test Shopify webhook signature validation"""
    provider = ShopifyProvider(webhook_secret="test_secret")

    # Create a mock Flask request
    mock_request = MagicMock(spec=Request)
    mock_request.headers = {
        "X-Shopify-Hmac-SHA256": "1234567890abcdef",
        "X-Shopify-Topic": "orders/create",
        "X-Shopify-Shop-Domain": "test-shop.myshopify.com",
    }
    mock_request.get_data.return_value = b'{"test": "data"}'

    with patch("hmac.compare_digest", return_value=True):
        assert provider.validate_webhook(mock_request) is True


def test_invalid_webhook_data():
    """Test handling of invalid webhook data"""
    chargify = ChargifyProvider(webhook_secret="test_secret")
    shopify = ShopifyProvider(webhook_secret="test_secret")

    # Test Chargify with invalid data
    mock_chargify_request = MagicMock(spec=Request)
    mock_chargify_request.content_type = "application/x-www-form-urlencoded"
    mock_chargify_request.form = MagicMock()
    mock_chargify_request.form.to_dict.return_value = {}

    with pytest.raises(InvalidDataError, match="Empty webhook data"):
        chargify.parse_webhook(mock_chargify_request)

    # Test Shopify with invalid data
    mock_shopify_request = MagicMock(spec=Request)
    mock_shopify_request.content_type = "application/json"
    mock_shopify_request.headers = {
        "X-Shopify-Topic": "orders/create",
        "X-Shopify-Shop-Domain": "test.myshopify.com",
    }
    mock_shopify_request.get_json.return_value = {}

    with pytest.raises(InvalidDataError, match="Empty webhook data"):
        shopify.parse_webhook(mock_shopify_request)
