from unittest.mock import MagicMock, patch, Mock
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
    mock_request.headers = {
        "X-Chargify-Webhook-Id": "webhook_123",
        "X-Chargify-Webhook-Signature-Hmac-Sha-256": "test_signature",
    }
    mock_request.form.to_dict.return_value = {
        "event": "payment_failure",
        "payload[subscription][id]": "sub_12345",
        "payload[subscription][state]": "past_due",
        "payload[subscription][customer][id]": "cust_456",
        "payload[subscription][customer][email]": "test@example.com",
        "payload[subscription][customer][first_name]": "Test",
        "payload[subscription][customer][last_name]": "User",
        "payload[subscription][customer][organization]": "Test Company",
        "payload[subscription][product][id]": "prod_789",
        "payload[subscription][product][name]": "Enterprise Plan",
        "payload[subscription][product][handle]": "enterprise",
        "payload[transaction][id]": "tr_123",
        "payload[transaction][amount_in_cents]": "2999",
        "payload[transaction][type]": "payment",
        "payload[transaction][memo]": "Payment failed: Card declined",
        "payload[transaction][failure_message]": "Card was declined",
        "created_at": "2024-03-15T10:00:00Z",
    }

    event = provider.parse_webhook(mock_request)
    assert event["type"] == "payment_failure"
    assert event["customer_id"] == "cust_456"
    assert event["amount"] == 29.99
    assert event["status"] == "failed"
    assert event["metadata"]["failure_reason"] == "Card was declined"
    assert event["metadata"]["subscription_id"] == "sub_12345"
    assert event["customer_data"]["company_name"] == "Test Company"
    assert event["customer_data"]["plan_name"] == "Enterprise Plan"


def test_shopify_order_parsing():
    """Test that Shopify order webhooks are properly parsed"""
    provider = ShopifyProvider(webhook_secret="test_secret")

    # Create a mock Flask request
    mock_request = MagicMock(spec=Request)
    mock_request.content_type = "application/json"
    mock_request.headers = {
        "X-Shopify-Topic": "orders/paid",
        "X-Shopify-Shop-Domain": "test.myshopify.com",
        "X-Shopify-Hmac-SHA256": "test_signature",
        "X-Shopify-Order-Id": "123456789",
    }
    mock_request.get_json.return_value = {
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

    event = provider.parse_webhook(mock_request)
    assert event["type"] == "orders_paid"
    assert event["customer_id"] == "456"
    assert event["amount"] == 29.99
    assert event["status"] == "success"
    assert event["metadata"]["order_number"] == 1001
    assert event["customer_data"]["company_name"] == "Test Company"
    assert event["customer_data"]["team_size"] == 25
    assert event["customer_data"]["plan_name"] == "Enterprise Plan"


def test_chargify_webhook_validation():
    """Test Chargify webhook signature validation"""
    provider = ChargifyProvider(webhook_secret="test_secret")

    # Create a mock Flask request with realistic headers
    mock_request = MagicMock(spec=Request)
    mock_request.headers = {
        "X-Chargify-Webhook-Signature-Hmac-Sha-256": "1234567890abcdef",
        "X-Chargify-Webhook-Id": "webhook_123",
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "Chargify Webhooks",
    }
    mock_request.get_data.return_value = (
        b"payload[event]=payment_failure&payload[subscription][id]=sub_12345"
    )

    with patch("hmac.compare_digest", return_value=True):
        assert provider.validate_webhook(mock_request) is True


def test_shopify_webhook_validation():
    """Test Shopify webhook signature validation"""
    provider = ShopifyProvider("test_secret")

    # Create mock request with valid signature
    mock_request = Mock()
    mock_request.headers = {
        "X-Shopify-Hmac-SHA256": "crxL3PMfBMvgMYyppPUPjAooPtjS7fh0dOiGPTYm3QU=",
        "X-Shopify-Topic": "orders/paid",
        "X-Shopify-Shop-Domain": "test.myshopify.com",
        "X-Shopify-Test": "true",
    }
    mock_request.content_type = "application/json"
    mock_request.get_data.return_value = b'{"test": "data"}'

    # Test valid signature
    with patch("hmac.new") as mock_hmac:
        mock_hmac.return_value.digest.return_value = b"test_digest"
        mock_b64encode = Mock(
            return_value=b"crxL3PMfBMvgMYyppPUPjAooPtjS7fh0dOiGPTYm3QU="
        )
        with patch("base64.b64encode", mock_b64encode):
            assert provider.validate_webhook(mock_request)

    # Test missing signature
    mock_request.headers.pop("X-Shopify-Hmac-SHA256")
    assert not provider.validate_webhook(mock_request)

    # Test missing topic
    mock_request.headers["X-Shopify-Hmac-SHA256"] = "test_signature"
    mock_request.headers.pop("X-Shopify-Topic")
    assert not provider.validate_webhook(mock_request)

    # Test missing shop domain
    mock_request.headers["X-Shopify-Topic"] = "orders/paid"
    mock_request.headers.pop("X-Shopify-Shop-Domain")
    assert not provider.validate_webhook(mock_request)

    # Test invalid signature
    mock_request.headers.update(
        {
            "X-Shopify-Hmac-SHA256": "invalid_signature",
            "X-Shopify-Topic": "orders/paid",
            "X-Shopify-Shop-Domain": "test.myshopify.com",
        }
    )
    assert not provider.validate_webhook(mock_request)


def test_shopify_test_webhook():
    """Test handling of Shopify test webhooks"""
    provider = ShopifyProvider("test_secret")

    # Create mock request with test webhook
    mock_request = Mock()
    mock_request.headers = {
        "X-Shopify-Hmac-SHA256": "test_signature",
        "X-Shopify-Topic": "orders/paid",
        "X-Shopify-Shop-Domain": "test.myshopify.com",
        "X-Shopify-Test": "true",
        "X-Shopify-Triggered-At": "2024-01-01T00:00:00Z",
    }
    mock_request.content_type = "application/json"

    # Mock the webhook data
    test_data = {
        "id": "test_order_123",
        "customer": {
            "id": "test_customer_456",
            "email": "test@example.com",
            "first_name": "Test",
            "last_name": "User",
            "company": "Test Company",
            "metafields": [{"key": "team_size", "value": "10"}],
        },
        "total_price": "100.00",
        "currency": "USD",
        "line_items": [{"title": "Test Plan"}],
    }
    mock_request.get_json.return_value = test_data

    # Test parsing test webhook
    event = provider.parse_webhook(mock_request)
    assert event is not None
    assert event["type"] == "orders_paid"
    assert event["customer_id"] == "test_customer_456"
    assert event["amount"] == 100.0
    assert event["currency"] == "USD"
    assert event["status"] == "success"
    assert event["metadata"]["source"] == "shopify"
    assert event["metadata"]["shop_domain"] == "test.myshopify.com"
    assert event["customer_data"]["company_name"] == "Test Company"
    assert event["customer_data"]["team_size"] == 10
    assert event["customer_data"]["plan_name"] == "Test Plan"


def test_shopify_invalid_webhook_data():
    """Test handling of invalid Shopify webhook data"""
    provider = ShopifyProvider("test_secret")

    # Create mock request
    mock_request = Mock()
    mock_request.headers = {
        "X-Shopify-Hmac-SHA256": "test_signature",
        "X-Shopify-Topic": "orders/paid",
        "X-Shopify-Shop-Domain": "test.myshopify.com",
    }
    mock_request.content_type = "application/json"

    # Test wrong content type
    mock_request.content_type = "application/x-www-form-urlencoded"
    with pytest.raises(InvalidDataError, match="Invalid content type"):
        provider.parse_webhook(mock_request)

    # Test empty data
    mock_request.content_type = "application/json"
    mock_request.get_json.return_value = None
    with pytest.raises(InvalidDataError, match="Empty webhook data"):
        provider.parse_webhook(mock_request)

    # Test missing customer ID
    mock_request.get_json.return_value = {"test": "data"}
    with pytest.raises(InvalidDataError, match="Missing required fields"):
        provider.parse_webhook(mock_request)

    # Test invalid amount format
    mock_request.get_json.return_value = {
        "id": "test_123",
        "total_price": "invalid",
    }
    event = provider.parse_webhook(mock_request)
    assert event["amount"] == 0.0  # Should default to 0 for invalid amount

    # Test invalid team size
    mock_request.get_json.return_value = {
        "id": "test_123",
        "customer": {"metafields": [{"key": "team_size", "value": "invalid"}]},
    }
    event = provider.parse_webhook(mock_request)
    assert (
        event["customer_data"]["team_size"] == 0
    )  # Should default to 0 for invalid team size


def test_invalid_webhook_data():
    """Test handling of invalid webhook data"""
    chargify = ChargifyProvider(webhook_secret="test_secret")
    shopify = ShopifyProvider(webhook_secret="test_secret")

    # Test Chargify with invalid data
    mock_chargify_request = MagicMock(spec=Request)
    mock_chargify_request.content_type = "application/x-www-form-urlencoded"
    mock_chargify_request.form = MagicMock()
    mock_chargify_request.form.to_dict.return_value = {}
    mock_chargify_request.headers = {
        "X-Chargify-Webhook-Id": "webhook_123",
        "X-Chargify-Webhook-Signature-Hmac-Sha-256": "test_signature",
    }

    with pytest.raises(InvalidDataError, match="Empty webhook data"):
        chargify.parse_webhook(mock_chargify_request)

    # Test Shopify with invalid data
    mock_shopify_request = MagicMock(spec=Request)
    mock_shopify_request.content_type = "application/json"
    mock_shopify_request.get_json.return_value = {}
    mock_shopify_request.headers = {
        "X-Shopify-Topic": "orders/paid",
        "X-Shopify-Shop-Domain": "test.myshopify.com",
        "X-Shopify-Hmac-SHA256": "test_signature",
        "X-Shopify-Order-Id": "123456789",
    }

    with pytest.raises(InvalidDataError, match="Missing required fields"):
        shopify.parse_webhook(mock_shopify_request)


def test_chargify_subscription_state_change():
    """Test parsing of Chargify subscription state change webhook"""
    provider = ChargifyProvider(webhook_secret="test_secret")

    mock_request = MagicMock(spec=Request)
    mock_request.content_type = "application/x-www-form-urlencoded"
    mock_request.form = MagicMock()
    mock_request.headers = {
        "X-Chargify-Webhook-Id": "webhook_123",
        "X-Chargify-Webhook-Signature-Hmac-Sha-256": "test_signature",
    }
    mock_request.form.to_dict.return_value = {
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

    event = provider.parse_webhook(mock_request)
    assert event["type"] == "subscription_state_change"
    assert event["customer_id"] == "cust_456"
    assert event["status"] == "canceled"
    assert event["metadata"]["subscription_id"] == "sub_12345"
    assert event["metadata"]["cancel_at_period_end"]
    assert event["customer_data"]["company_name"] == "Test Company"
    assert event["customer_data"]["plan_name"] == "Enterprise Plan"


def test_shopify_customer_data_update():
    """Test parsing of Shopify customers/update webhook"""
    provider = ShopifyProvider(webhook_secret="test_secret")

    mock_request = MagicMock(spec=Request)
    mock_request.content_type = "application/json"
    mock_request.headers = {
        "X-Shopify-Topic": "customers/update",
        "X-Shopify-Shop-Domain": "test.myshopify.com",
        "X-Shopify-Hmac-SHA256": "test_signature",
    }
    mock_request.get_json.return_value = {
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

    event = provider.parse_webhook(mock_request)
    assert event["type"] == "customers_update"
    assert event["customer_id"] == "456"
    assert event["customer_data"]["company_name"] == "Updated Company Name"
    assert event["customer_data"]["team_size"] == 50
    assert "enterprise_annual" in str(event["metadata"])


def test_chargify_webhook_deduplication():
    """Test Chargify webhook deduplication logic"""
    provider = ChargifyProvider("")

    # Create a mock request with payment_success event
    mock_request = Mock()
    mock_request.content_type = "application/x-www-form-urlencoded"
    mock_request.headers = {
        "X-Chargify-Webhook-Id": "test_webhook_1",
    }
    form_data = {
        "event": "payment_success",
        "id": "12345",
        "payload[subscription][id]": "sub_789",
        "payload[subscription][customer][id]": "cust_123",
        "payload[transaction][amount_in_cents]": "10000",
        "payload[subscription][customer][organization]": "Test Co",
        "payload[subscription][product][name]": "Enterprise Plan",
    }
    mock_form = MagicMock()
    mock_form.to_dict.return_value = form_data
    mock_request.form = mock_form

    # First event should be processed
    event1 = provider.parse_webhook(mock_request)
    assert event1 is not None
    assert event1["type"] == "payment_success"
    assert event1["customer_id"] == "cust_123"

    # Same event within dedup window should be marked as duplicate
    with pytest.raises(InvalidDataError, match="Duplicate webhook"):
        provider.parse_webhook(mock_request)

    # Different event type for same customer should be processed
    mock_request.headers["X-Chargify-Webhook-Id"] = "test_webhook_2"
    form_data["event"] = "renewal_success"
    mock_form.to_dict.return_value = form_data
    event2 = provider.parse_webhook(mock_request)
    assert event2 is not None
    assert event2["type"] == "renewal_success"
    assert event2["customer_id"] == "cust_123"

    # Different customer should be processed
    mock_request.headers["X-Chargify-Webhook-Id"] = "test_webhook_3"
    form_data["event"] = "payment_success"
    form_data["payload[subscription][customer][id]"] = "cust_456"
    mock_form.to_dict.return_value = form_data
    event3 = provider.parse_webhook(mock_request)
    assert event3 is not None
    assert event3["type"] == "payment_success"
    assert event3["customer_id"] == "cust_456"

    # Test cache cleanup - events outside dedup window
    provider._DEDUP_WINDOW_SECONDS = 0  # Set window to 0 to force cleanup
    mock_request.headers["X-Chargify-Webhook-Id"] = "test_webhook_4"
    event4 = provider.parse_webhook(mock_request)
    assert event4 is not None
    assert event4["type"] == "payment_success"
    assert event4["customer_id"] == "cust_456"
