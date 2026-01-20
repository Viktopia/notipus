"""
Comprehensive tests for Shopify modules to achieve 80%+ test coverage
"""

import json
from unittest.mock import Mock, patch

import pytest
from core.services.shopify import ShopifyAPI
from webhooks.providers.base import CustomerNotFoundError, InvalidDataError
from webhooks.providers.shopify import ShopifyProvider


class TestShopifyProvider:
    """Comprehensive tests for ShopifyProvider"""

    @pytest.fixture
    def provider(self):
        return ShopifyProvider(webhook_secret="test_secret")

    def test_init(self, provider):
        """Test provider initialization"""
        assert provider.webhook_secret == "test_secret"
        assert provider._current_webhook_data is None

    def test_validate_shopify_request_invalid_content_type(self, provider):
        """Test validation with invalid content type"""
        mock_request = Mock()
        mock_request.content_type = "text/plain"

        with pytest.raises(InvalidDataError, match="Invalid content type"):
            provider._validate_shopify_request(mock_request)

    def test_validate_shopify_request_missing_topic(self, provider):
        """Test validation with missing topic header"""
        mock_request = Mock()
        mock_request.content_type = "application/json"
        mock_request.headers = {}

        with pytest.raises(InvalidDataError, match="Missing webhook topic"):
            provider._validate_shopify_request(mock_request)

    def test_validate_shopify_request_success(self, provider):
        """Test successful request validation"""
        mock_request = Mock()
        mock_request.content_type = "application/json"
        mock_request.headers = {"X-Shopify-Topic": "orders/paid"}

        topic = provider._validate_shopify_request(mock_request)
        assert topic == "orders/paid"

    def test_parse_shopify_json_invalid_json(self, provider):
        """Test parsing invalid JSON data"""
        mock_request = Mock()
        mock_request.data = b"invalid json"

        with pytest.raises(InvalidDataError, match="Invalid JSON data"):
            provider._parse_shopify_json(mock_request)

    def test_parse_shopify_json_attribute_error(self, provider):
        """Test parsing when request.data doesn't exist"""
        mock_request = Mock()
        del mock_request.data  # Remove data attribute

        with pytest.raises(InvalidDataError, match="Invalid JSON data"):
            provider._parse_shopify_json(mock_request)

    def test_parse_shopify_json_non_dict(self, provider):
        """Test parsing when JSON is not a dictionary"""
        mock_request = Mock()
        mock_request.data = b'"just a string"'

        with pytest.raises(InvalidDataError, match="Invalid JSON data"):
            provider._parse_shopify_json(mock_request)

    def test_parse_shopify_json_empty_dict(self, provider):
        """Test parsing empty dictionary"""
        mock_request = Mock()
        mock_request.data = b"{}"

        with pytest.raises(InvalidDataError, match="Missing required fields"):
            provider._parse_shopify_json(mock_request)

    def test_parse_shopify_json_success(self, provider):
        """Test successful JSON parsing"""
        mock_request = Mock()
        test_data = {"test": "data"}
        mock_request.data = json.dumps(test_data).encode()

        result = provider._parse_shopify_json(mock_request)
        assert result == test_data

    def test_is_test_webhook_test_topic(self, provider):
        """Test test webhook detection with test topic"""
        mock_request = Mock()

        result = provider._is_test_webhook("test", mock_request)
        assert result is True

    def test_is_test_webhook_test_header(self, provider):
        """Test test webhook detection with test header"""
        mock_request = Mock()
        mock_request.headers = {"X-Shopify-Test": "true"}

        result = provider._is_test_webhook("orders/paid", mock_request)
        assert result is True

    def test_is_test_webhook_false(self, provider):
        """Test normal webhook detection"""
        mock_request = Mock()
        mock_request.headers = {}

        result = provider._is_test_webhook("orders/paid", mock_request)
        assert result is False

    def test_extract_shopify_customer_id_from_customer(self, provider):
        """Test customer ID extraction from customer field"""
        data = {"customer": {"id": 12345}}

        customer_id = provider._extract_shopify_customer_id(data)
        assert customer_id == "12345"

    def test_extract_shopify_customer_id_from_order_customer(self, provider):
        """Test customer ID extraction from order.customer field"""
        data = {"order": {"customer": {"id": 67890}}}

        customer_id = provider._extract_shopify_customer_id(data)
        assert customer_id == "67890"

    def test_extract_shopify_customer_id_from_id_field(self, provider):
        """Test customer ID extraction from id field"""
        data = {"id": 11111}

        customer_id = provider._extract_shopify_customer_id(data)
        assert customer_id == "11111"

    def test_extract_shopify_customer_id_missing_id(self, provider):
        """Test customer ID extraction when id is missing"""
        data = {"some_field": "value"}

        with pytest.raises(InvalidDataError, match="Missing required fields"):
            provider._extract_shopify_customer_id(data)

    def test_extract_shopify_customer_id_none_id(self, provider):
        """Test customer ID extraction when id is None"""
        data = {"id": None}

        with pytest.raises(InvalidDataError, match="Missing required fields"):
            provider._extract_shopify_customer_id(data)

    def test_extract_shopify_customer_id_empty_string(self, provider):
        """Test customer ID extraction when id is empty string"""
        data = {"id": ""}

        with pytest.raises(InvalidDataError, match="Missing required fields"):
            provider._extract_shopify_customer_id(data)

    def test_extract_shopify_customer_id_key_error(self, provider):
        """Test customer ID extraction with KeyError"""
        data = {"customer": {"name": "test"}}  # Missing id field

        with pytest.raises(InvalidDataError, match="Missing required fields"):
            provider._extract_shopify_customer_id(data)

    def test_extract_shopify_customer_id_normal_behavior(self, provider):
        """Test customer ID extraction normal behavior"""
        data = {"customer": {"id": 12345}}

        customer_id = provider._extract_shopify_customer_id(data)
        assert customer_id == "12345"

    def test_build_shopify_event_data_basic(self, provider):
        """Test basic event data building"""
        event_type = "payment_success"
        customer_id = "12345"
        data = {"created_at": "2024-01-01T00:00:00Z"}
        topic = "orders/paid"

        result = provider._build_shopify_event_data(
            event_type, customer_id, data, topic
        )

        assert result["type"] == event_type
        assert result["customer_id"] == customer_id
        assert result["provider"] == "shopify"
        assert result["status"] == "success"
        assert result["created_at"] == "2024-01-01T00:00:00Z"

    def test_build_shopify_event_data_with_amount(self, provider):
        """Test event data building with amount"""
        data = {"total_price": "29.99", "created_at": "2024-01-01T00:00:00Z"}

        result = provider._build_shopify_event_data(
            "payment_success", "12345", data, "orders/paid"
        )
        assert result["amount"] == 29.99

    def test_build_shopify_event_data_invalid_amount_value_error(self, provider):
        """Test event data building with amount causing ValueError"""
        data = {"total_price": "invalid", "created_at": "2024-01-01T00:00:00Z"}

        with pytest.raises(InvalidDataError, match="Missing required fields"):
            provider._build_shopify_event_data(
                "payment_success", "12345", data, "orders/paid"
            )

    def test_build_shopify_event_data_invalid_amount_type_error(self, provider):
        """Test event data building with amount causing TypeError"""
        data = {"total_price": None, "created_at": "2024-01-01T00:00:00Z"}

        with pytest.raises(InvalidDataError, match="Missing required fields"):
            provider._build_shopify_event_data(
                "payment_success", "12345", data, "orders/paid"
            )

    def test_build_shopify_event_data_with_currency(self, provider):
        """Test event data building with currency"""
        data = {"currency": "USD", "created_at": "2024-01-01T00:00:00Z"}

        result = provider._build_shopify_event_data(
            "payment_success", "12345", data, "orders/paid"
        )
        assert result["currency"] == "USD"

    def test_build_shopify_event_data_customer_update(self, provider):
        """Test event data building for customer update"""
        data = {
            "company": "Test Corp",
            "email": "test@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "orders_count": 5,
            "total_spent": "150.00",
            "created_at": "2024-01-01T00:00:00Z",
        }

        result = provider._build_shopify_event_data(
            "customers/update", "12345", data, "customers/update"
        )

        assert "customer_data" in result
        assert result["customer_data"]["company"] == "Test Corp"
        assert result["customer_data"]["email"] == "test@example.com"
        assert result["customer_data"]["first_name"] == "John"
        assert result["customer_data"]["last_name"] == "Doe"
        assert result["customer_data"]["orders_count"] == 5
        assert result["customer_data"]["total_spent"] == "150.00"

    def test_parse_webhook_unsupported_topic(self, provider):
        """Test parsing webhook with unsupported topic"""
        mock_request = Mock()
        mock_request.content_type = "application/json"
        mock_request.headers = {"X-Shopify-Topic": "unsupported/topic"}
        mock_request.data = json.dumps({"id": 123}).encode()

        with pytest.raises(
            InvalidDataError, match="Unsupported webhook topic: unsupported/topic"
        ):
            provider.parse_webhook(mock_request)

    def test_parse_webhook_test_webhook_with_x_shopify_test_true(self, provider):
        """Test parsing test webhook with X-Shopify-Test header set to true"""
        mock_request = Mock()
        mock_request.content_type = "application/json"
        mock_request.headers = {
            "X-Shopify-Topic": "orders/paid",
            "X-Shopify-Test": "true",
        }
        mock_request.data = json.dumps({"test": True}).encode()

        result = provider.parse_webhook(mock_request)
        assert result is None

    def test_get_customer_data_no_webhook_data(self, provider):
        """Test get_customer_data when no webhook data is available"""
        with pytest.raises(CustomerNotFoundError, match="No webhook data available"):
            provider.get_customer_data("12345")

    def test_get_customer_data_with_customer_field(self, provider):
        """Test get_customer_data with customer field"""
        provider._current_webhook_data = {
            "customer": {
                "company": "Test Corp",
                "email": "test@example.com",
                "first_name": "John",
                "last_name": "Doe",
                "orders_count": 5,
                "total_spent": "150.00",
                "tags": ["vip", "enterprise"],
                "note": "Important customer",
            },
            "shop_domain": "test.myshopify.com",
        }

        result = provider.get_customer_data("12345")

        assert result["company"] == "Test Corp"
        assert result["email"] == "test@example.com"
        assert result["first_name"] == "John"
        assert result["last_name"] == "Doe"
        assert result["orders_count"] == 5
        assert result["total_spent"] == "150.00"
        assert result["metadata"]["shop_domain"] == "test.myshopify.com"
        assert result["metadata"]["tags"] == ["vip", "enterprise"]
        assert result["metadata"]["note"] == "Important customer"

    def test_get_customer_data_with_order_customer(self, provider):
        """Test get_customer_data with order.customer field"""
        provider._current_webhook_data = {
            "order": {
                "customer": {
                    "company": "Order Corp",
                    "email": "order@example.com",
                    "first_name": "Jane",
                    "last_name": "Smith",
                    "orders_count": 10,
                    "total_spent": "300.00",
                }
            }
        }

        result = provider.get_customer_data("12345")

        assert result["company"] == "Order Corp"
        assert result["email"] == "order@example.com"
        assert result["first_name"] == "Jane"
        assert result["last_name"] == "Smith"

    def test_get_customer_data_defaults(self, provider):
        """Test get_customer_data with missing fields using defaults"""
        provider._current_webhook_data = {"customer": {}}

        result = provider.get_customer_data("12345")

        assert result["company"] == "Individual"
        assert result["email"] == ""
        assert result["first_name"] == ""
        assert result["last_name"] == ""
        assert result["orders_count"] == 0
        assert result["total_spent"] == "0.00"

    def test_validate_webhook_missing_hmac(self, provider):
        """Test webhook validation with missing HMAC header"""
        mock_request = Mock()
        mock_request.headers = {}

        result = provider.validate_webhook(mock_request)
        assert result is False

    def test_validate_webhook_invalid_body_type(self, provider):
        """Test webhook validation with invalid body type"""
        mock_request = Mock()
        mock_request.headers = {"X-Shopify-Hmac-SHA256": "test_hmac"}
        mock_request.body = "not bytes"  # Should be bytes

        with pytest.raises(
            TypeError, match="Expected bytes or bytearray for request body"
        ):
            provider.validate_webhook(mock_request)

    @patch("hmac.compare_digest")
    def test_validate_webhook_success(self, mock_compare_digest, provider):
        """Test webhook validation using manual method"""
        mock_request = Mock()
        mock_request.headers = {"X-Shopify-Hmac-SHA256": "test_hmac"}
        mock_request.body = b'{"test": "data"}'

        mock_compare_digest.return_value = True

        result = provider.validate_webhook(mock_request)
        assert result is True

    def test_validate_webhook_calls_manual_method(self, provider):
        """Test that validate_webhook calls the manual validation method"""
        mock_request = Mock()
        mock_request.headers = {"X-Shopify-Hmac-SHA256": "test_hmac"}
        mock_request.body = b'{"test": "data"}'

        with patch.object(
            provider, "_manual_validate_webhook", return_value=True
        ) as mock_manual:
            result = provider.validate_webhook(mock_request)
            assert result is True
            mock_manual.assert_called_once_with(mock_request)

    def test_manual_validate_webhook_missing_hmac(self, provider):
        """Test manual webhook validation with missing HMAC header"""
        mock_request = Mock()
        mock_request.headers = {}

        result = provider._manual_validate_webhook(mock_request)
        assert result is False

    def test_manual_validate_webhook_with_string_secret(self, provider):
        """Test manual webhook validation with string secret"""
        provider.webhook_secret = "string_secret"
        mock_request = Mock()
        mock_request.headers = {"X-Shopify-Hmac-SHA256": "dGVzdF9oYXNo"}
        mock_request.body = b'{"test": "data"}'

        with patch("hmac.compare_digest", return_value=True):
            result = provider._manual_validate_webhook(mock_request)
            assert result is True


class TestShopifyAPI:
    """Comprehensive tests for ShopifyAPI service"""

    @patch("core.services.shopify.shopify.Session")
    @patch("core.services.shopify.shopify.Session.temp")
    @patch("core.services.shopify.shopify.Shop.current")
    def test_get_shop_domain_success(self, mock_shop_current, mock_temp, mock_session):
        """Test successful shop domain retrieval using official library"""
        # Mock session creation
        mock_session_instance = Mock()
        mock_session_instance.domain = "test.myshopify.com"
        mock_session_instance.api_version = "2024-01"
        mock_session_instance.token = "test_token"
        mock_session.return_value = mock_session_instance

        # Mock shop object
        mock_shop = Mock()
        mock_shop.myshopify_domain = "test.myshopify.com"
        mock_shop_current.return_value = mock_shop

        result = ShopifyAPI.get_shop_domain("test.myshopify.com", "test_token")

        assert result == "test.myshopify.com"

    @patch("core.services.shopify.shopify.Session")
    def test_get_session_failure(self, mock_session):
        """Test session creation failure"""
        mock_session.side_effect = Exception("Session creation failed")

        with pytest.raises(Exception, match="Session creation failed"):
            ShopifyAPI._get_session("test.myshopify.com", "test_token")

    @patch("core.services.shopify.ShopifyAPI._get_session")
    @patch("core.services.shopify.shopify.Session.temp")
    def test_get_shop_domain_exception(self, mock_temp, mock_get_session):
        """Test shop domain retrieval with exception"""
        mock_get_session.side_effect = Exception("API error")

        result = ShopifyAPI.get_shop_domain("test.myshopify.com", "test_token")

        assert result is None

    def test_shopify_api_exists(self):
        """Test that ShopifyAPI class exists and can be instantiated"""
        api = ShopifyAPI()
        assert api is not None
