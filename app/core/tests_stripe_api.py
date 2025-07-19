"""
Tests for Stripe API service.

This module contains comprehensive tests for the StripeAPI class, which handles
Stripe customer creation using the official Stripe SDK. The tests cover:

- Successful customer creation scenarios
- All major Stripe error types (CardError, APIError, RateLimitError, etc.)
- Edge cases like empty data and missing fields
- Logging behavior verification
- API key configuration testing

Test coverage focuses on error handling, data validation, and integration
with the Stripe SDK to ensure robust payment processing.
"""

from unittest.mock import Mock, patch

from django.test import TestCase

from .services.stripe import StripeAPI


class StripeAPITest(TestCase):
    """Test StripeAPI service"""

    def setUp(self) -> None:
        """Set up test data"""
        self.api = StripeAPI()

    @patch("core.services.stripe.stripe.Customer.create")
    def test_create_stripe_customer_success(self, mock_create) -> None:
        """Test successful customer creation"""
        # Mock successful customer creation
        mock_customer = Mock()
        mock_customer.to_dict.return_value = {
            "id": "cus_test123",
            "email": "test@example.com",
            "name": "Test Customer",
        }
        mock_create.return_value = mock_customer

        customer_data = {
            "email": "test@example.com",
            "name": "Test Customer",
            "metadata": {"source": "test"},
        }

        result = StripeAPI.create_stripe_customer(customer_data)

        expected = {
            "id": "cus_test123",
            "email": "test@example.com",
            "name": "Test Customer",
        }

        self.assertEqual(result, expected)
        mock_create.assert_called_once_with(**customer_data)

    @patch("core.services.stripe.stripe.Customer.create")
    def test_create_stripe_customer_stripe_error(self, mock_create) -> None:
        """Test customer creation with Stripe error"""
        from stripe.error import StripeError

        # Mock Stripe error
        mock_create.side_effect = StripeError("Test Stripe error")

        customer_data = {"email": "test@example.com", "name": "Test Customer"}

        result = StripeAPI.create_stripe_customer(customer_data)

        self.assertIsNone(result)

    @patch("core.services.stripe.stripe.Customer.create")
    def test_create_stripe_customer_api_error(self, mock_create) -> None:
        """Test customer creation with API error"""
        from stripe.error import APIError

        # Mock API error
        mock_create.side_effect = APIError("API connection failed")

        customer_data = {"email": "test@example.com", "name": "Test Customer"}

        result = StripeAPI.create_stripe_customer(customer_data)

        self.assertIsNone(result)

    @patch("core.services.stripe.stripe.Customer.create")
    def test_create_stripe_customer_card_error(self, mock_create) -> None:
        """Test customer creation with card error"""
        from stripe.error import CardError

        # Mock card error
        mock_create.side_effect = CardError("Card declined", None, "card_declined")

        customer_data = {"email": "test@example.com", "name": "Test Customer"}

        result = StripeAPI.create_stripe_customer(customer_data)

        self.assertIsNone(result)

    @patch("core.services.stripe.stripe.Customer.create")
    def test_create_stripe_customer_rate_limit_error(self, mock_create) -> None:
        """Test customer creation with rate limit error"""
        from stripe.error import RateLimitError

        # Mock rate limit error
        mock_create.side_effect = RateLimitError("Rate limit exceeded")

        customer_data = {"email": "test@example.com", "name": "Test Customer"}

        result = StripeAPI.create_stripe_customer(customer_data)

        self.assertIsNone(result)

    @patch("core.services.stripe.stripe.Customer.create")
    def test_create_stripe_customer_authentication_error(self, mock_create) -> None:
        """Test customer creation with authentication error"""
        from stripe.error import AuthenticationError

        # Mock authentication error
        mock_create.side_effect = AuthenticationError("Invalid API key")

        customer_data = {"email": "test@example.com", "name": "Test Customer"}

        result = StripeAPI.create_stripe_customer(customer_data)

        self.assertIsNone(result)

    @patch("core.services.stripe.stripe.Customer.create")
    def test_create_stripe_customer_permission_error(self, mock_create) -> None:
        """Test customer creation with permission error"""
        from stripe.error import PermissionError

        # Mock permission error
        mock_create.side_effect = PermissionError("Insufficient permissions")

        customer_data = {"email": "test@example.com", "name": "Test Customer"}

        result = StripeAPI.create_stripe_customer(customer_data)

        self.assertIsNone(result)

    @patch("core.services.stripe.stripe.Customer.create")
    def test_create_stripe_customer_general_exception(self, mock_create) -> None:
        """Test customer creation with general exception"""
        # Mock general exception
        mock_create.side_effect = Exception("Unexpected error")

        customer_data = {"email": "test@example.com", "name": "Test Customer"}

        result = StripeAPI.create_stripe_customer(customer_data)

        self.assertIsNone(result)

    @patch("core.services.stripe.stripe.Customer.create")
    def test_create_stripe_customer_empty_data(self, mock_create) -> None:
        """Test customer creation with empty data"""
        # Mock successful creation with empty data
        mock_customer = Mock()
        mock_customer.to_dict.return_value = {"id": "cus_empty"}
        mock_create.return_value = mock_customer

        result = StripeAPI.create_stripe_customer({})

        self.assertEqual(result, {"id": "cus_empty"})
        mock_create.assert_called_once_with()

    @patch("core.services.stripe.stripe.Customer.create")
    def test_create_stripe_customer_with_metadata(self, mock_create) -> None:
        """Test customer creation with metadata"""
        # Mock successful creation
        mock_customer = Mock()
        mock_customer.to_dict.return_value = {
            "id": "cus_metadata",
            "email": "test@example.com",
            "metadata": {"user_id": "123", "source": "webapp"},
        }
        mock_create.return_value = mock_customer

        customer_data = {
            "email": "test@example.com",
            "metadata": {"user_id": "123", "source": "webapp"},
        }

        result = StripeAPI.create_stripe_customer(customer_data)

        self.assertEqual(result["metadata"]["user_id"], "123")
        self.assertEqual(result["metadata"]["source"], "webapp")

    @patch("core.services.stripe.stripe.Customer.create")
    def test_create_stripe_customer_with_address(self, mock_create) -> None:
        """Test customer creation with address"""
        # Mock successful creation
        mock_customer = Mock()
        mock_customer.to_dict.return_value = {
            "id": "cus_address",
            "email": "test@example.com",
            "address": {
                "line1": "123 Main St",
                "city": "San Francisco",
                "state": "CA",
                "postal_code": "94102",
                "country": "US",
            },
        }
        mock_create.return_value = mock_customer

        customer_data = {
            "email": "test@example.com",
            "address": {
                "line1": "123 Main St",
                "city": "San Francisco",
                "state": "CA",
                "postal_code": "94102",
                "country": "US",
            },
        }

        result = StripeAPI.create_stripe_customer(customer_data)

        self.assertEqual(result["address"]["line1"], "123 Main St")
        self.assertEqual(result["address"]["city"], "San Francisco")

    @patch("core.services.stripe.stripe.Customer.create")
    @patch("app.core.services.stripe.logger")
    def test_create_stripe_customer_logs_stripe_error(
        self, mock_logger, mock_create
    ) -> None:
        """Test that Stripe errors are properly logged"""
        from stripe.error import CardError

        # Mock card error
        error_msg = "Your card was declined"
        mock_create.side_effect = CardError(error_msg, None, "card_declined")

        customer_data = {"email": "test@example.com"}

        result = StripeAPI.create_stripe_customer(customer_data)

        self.assertIsNone(result)
        mock_logger.error.assert_called_once_with(
            f"Stripe error creating customer: {error_msg}"
        )

    @patch("core.services.stripe.stripe.Customer.create")
    @patch("app.core.services.stripe.logger")
    def test_create_stripe_customer_logs_general_error(
        self, mock_logger, mock_create
    ) -> None:
        """Test that general errors are properly logged"""
        # Mock general exception
        error_msg = "Network timeout"
        mock_create.side_effect = Exception(error_msg)

        customer_data = {"email": "test@example.com"}

        result = StripeAPI.create_stripe_customer(customer_data)

        self.assertIsNone(result)
        expected_msg = f"Unexpected error creating Stripe customer: {error_msg}"
        mock_logger.error.assert_called_once_with(expected_msg)

    @patch("core.services.stripe.settings.STRIPE_SECRET_KEY", "sk_test_new_key")
    @patch("core.services.stripe.stripe.Customer.create")
    def test_create_stripe_customer_uses_correct_api_key(self, mock_create) -> None:
        """Test that the correct API key is used"""
        import core.services.stripe as stripe_module

        # Mock successful creation
        mock_customer = Mock()
        mock_customer.to_dict.return_value = {"id": "cus_test"}
        mock_create.return_value = mock_customer

        customer_data = {"email": "test@example.com"}

        # Create new instance to trigger API key setting
        StripeAPI()
        result = StripeAPI.create_stripe_customer(customer_data)

        # Verify API key was set
        self.assertEqual(stripe_module.stripe.api_key, "sk_test_new_key")
        self.assertIsNotNone(result)
