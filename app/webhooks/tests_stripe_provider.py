"""
Tests for Stripe webhook provider.
"""
from typing import Optional
from unittest.mock import Mock, patch

from django.test import TestCase

from .providers.base import InvalidDataError
from .providers.stripe import StripeProvider


class StripeProviderTest(TestCase):
    """Test StripeProvider webhook handling"""

    def setUp(self):
        """Set up test data"""
        self.webhook_secret = "test_webhook_secret"
        self.provider = StripeProvider(self.webhook_secret)

    def _create_mock_request(self, body: str, signature: Optional[str] = None):
        """Create a mock HTTP request for testing"""
        request = Mock()
        request.body = body.encode() if isinstance(body, str) else body
        request.headers = {}
        if signature:
            request.headers["Stripe-Signature"] = signature
        return request

    def test_get_customer_data(self):
        """Test getting customer data"""
        result = self.provider.get_customer_data("cus_123")

        expected = {
            "company_name": "<COMPANY_NAME>",
            "email": "<EMAIL>",
            "first_name": "<FIRST_NAME>",
            "last_name": "<LAST_NAME>",
        }

        self.assertEqual(result, expected)

    def test_build_stripe_event_data(self):
        """Test building Stripe event data structure"""
        data = {"status": "succeeded", "created": 1234567890, "currency": "usd"}

        result = self.provider._build_stripe_event_data(
            "payment_success", "cus_123", data, "2000"
        )

        expected = {
            "type": "payment_success",
            "customer_id": "cus_123",
            "status": "succeeded",
            "created_at": 1234567890,
            "currency": "USD",
            "amount": 2000.0,
        }

        self.assertEqual(result, expected)

    def test_build_stripe_event_data_default_currency(self):
        """Test building event data with missing currency"""
        data = {"status": "succeeded", "created": 1234567890}

        result = self.provider._build_stripe_event_data(
            "payment_success", "cus_123", data, "2000"
        )

        self.assertEqual(result["currency"], "USD")

    def test_handle_stripe_billing_unknown_event(self):
        """Test handling unknown billing event"""
        data = {"amount_due": 1500}

        amount = self.provider._handle_stripe_billing("unknown_event", data)

        self.assertEqual(amount, "0")

    def test_handle_stripe_billing_missing_amount_due(self):
        """Test handling payment events with missing amount_due"""
        data = {}  # Missing amount_due

        amount = self.provider._handle_stripe_billing("payment_success", data)

        self.assertEqual(amount, "0")

    def test_handle_stripe_billing_missing_plan_amount(self):
        """Test handling subscription created with missing plan amount"""
        data = {"plan": {}}  # Missing amount

        amount = self.provider._handle_stripe_billing("subscription_created", data)

        self.assertEqual(amount, "0")

    def test_extract_stripe_event_info_subscription_created(self):
        """Test extracting event info for subscription created"""
        mock_event = Mock()
        mock_event.type = "customer.subscription.created"
        mock_event.data.object = {"id": "sub_123", "customer": "cus_123"}

        event_type, data = self.provider._extract_stripe_event_info(mock_event)

        self.assertEqual(event_type, "subscription_created")
        self.assertEqual(data["id"], "sub_123")

    def test_extract_stripe_event_info_payment_success(self):
        """Test extracting event info for payment success"""
        mock_event = Mock()
        mock_event.type = "invoice.payment_succeeded"
        mock_event.data.object = {
            "id": "in_123",
            "customer": "cus_123",
            "amount_due": 2000,
        }

        event_type, data = self.provider._extract_stripe_event_info(mock_event)

        self.assertEqual(event_type, "payment_success")
        self.assertEqual(data["amount_due"], 2000)

    def test_extract_stripe_event_info_payment_failure(self):
        """Test extracting event info for payment failure"""
        mock_event = Mock()
        mock_event.type = "invoice.payment_failed"
        mock_event.data.object = {
            "id": "in_123",
            "customer": "cus_123",
            "amount_due": 2000,
        }

        event_type, data = self.provider._extract_stripe_event_info(mock_event)

        self.assertEqual(event_type, "payment_failure")

    def test_extract_stripe_event_info_unsupported_event(self):
        """Test extracting info for unsupported event type"""
        mock_event = Mock()
        mock_event.type = "unsupported.event.type"

        with self.assertRaises(InvalidDataError):
            self.provider._extract_stripe_event_info(mock_event)

    def test_extract_stripe_event_info_missing_event_type(self):
        """Test extracting info with missing event type"""
        mock_event = Mock()
        mock_event.type = None

        with self.assertRaises(InvalidDataError):
            self.provider._extract_stripe_event_info(mock_event)

    def test_extract_stripe_event_info_missing_data(self):
        """Test extracting info with missing data"""
        mock_event = Mock()
        mock_event.type = "invoice.payment_succeeded"
        mock_event.data.object = None

        with self.assertRaises(InvalidDataError):
            self.provider._extract_stripe_event_info(mock_event)

    @patch("webhooks.providers.stripe.settings.DISABLE_BILLING", True)
    def test_validate_webhook_billing_disabled(self):
        """Test webhook validation when billing is disabled"""
        request = self._create_mock_request(
            '{"type": "invoice.payment_succeeded"}', "t=123456789,v1=test_signature"
        )

        result = self.provider.validate_webhook(request)

        self.assertFalse(result)

    @patch("webhooks.providers.stripe.stripe.Webhook.construct_event")
    def test_validate_webhook_success(self, mock_construct_event):
        """Test successful webhook validation"""
        # Mock successful validation
        mock_construct_event.return_value = Mock()

        request = self._create_mock_request(
            '{"type": "invoice.payment_succeeded"}', "t=123456789,v1=test_signature"
        )

        # Mock the billing settings to be enabled
        with patch("webhooks.providers.stripe.settings.DISABLE_BILLING", False):
            result = self.provider.validate_webhook(request)

        self.assertTrue(result)
        mock_construct_event.assert_called_once_with(
            request.body, "t=123456789,v1=test_signature", self.webhook_secret
        )

    @patch("webhooks.providers.stripe.stripe.Webhook.construct_event")
    def test_validate_webhook_invalid_signature(self, mock_construct_event):
        """Test webhook validation with invalid signature"""
        import stripe.error

        # Mock signature verification error
        mock_construct_event.side_effect = stripe.error.SignatureVerificationError(
            "Invalid signature", "sig_header"
        )

        request = self._create_mock_request(
            '{"type": "invoice.payment_succeeded"}', "t=123456789,v1=invalid_signature"
        )

        result = self.provider.validate_webhook(request)

        self.assertFalse(result)

    def test_validate_webhook_missing_signature(self):
        """Test webhook validation with missing signature"""
        request = self._create_mock_request('{"type": "invoice.payment_succeeded"}')

        result = self.provider.validate_webhook(request)

        self.assertFalse(result)

    @patch("webhooks.providers.stripe.stripe.Webhook.construct_event")
    def test_parse_webhook_success(self, mock_construct_event):
        """Test successful webhook parsing"""
        # Mock Stripe event
        mock_event = Mock()
        mock_event.type = "invoice.payment_succeeded"
        mock_event.data.object = Mock()
        mock_event.data.object.to_dict.return_value = {
            "customer": "cus_123",
            "amount_due": 2000,
            "currency": "usd",
            "status": "succeeded",
            "created": 1234567890,
        }
        mock_construct_event.return_value = mock_event

        request = self._create_mock_request(
            '{"type": "invoice.payment_succeeded"}', "t=123456789,v1=test_signature"
        )

        with patch.object(
            self.provider, "_handle_stripe_billing", return_value="2000"
        ):
            result = self.provider.parse_webhook(request)

        expected = {
            "type": "payment_success",
            "customer_id": "cus_123",
            "status": "succeeded",
            "created_at": 1234567890,
            "currency": "USD",
            "amount": 2000.0,
        }

        self.assertEqual(result, expected)

    def test_parse_webhook_missing_signature(self):
        """Test parsing webhook without signature"""
        request = self._create_mock_request('{"type": "invoice.payment_succeeded"}')

        with self.assertRaises(InvalidDataError) as context:
            self.provider.parse_webhook(request)

        self.assertIn("Missing Stripe signature", str(context.exception))

    @patch("webhooks.providers.stripe.stripe.Webhook.construct_event")
    def test_parse_webhook_invalid_signature(self, mock_construct_event):
        """Test parsing webhook with invalid signature"""
        import stripe.error

        mock_construct_event.side_effect = stripe.error.SignatureVerificationError(
            "Invalid signature", "sig_header"
        )

        request = self._create_mock_request(
            '{"type": "invoice.payment_succeeded"}', "t=123456789,v1=invalid_signature"
        )

        with self.assertRaises(InvalidDataError) as context:
            self.provider.parse_webhook(request)

        self.assertIn("Invalid webhook signature", str(context.exception))
