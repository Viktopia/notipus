"""Tests for Stripe webhook provider.

This module contains comprehensive tests for the StripeSourcePlugin class,
which handles incoming webhook requests from Stripe using the official Stripe SDK.
The tests cover:

- Webhook signature validation using Stripe's built-in verification
- Event data extraction and parsing from Stripe webhook payloads
- Billing service integration for subscription and payment events
- Error handling for various failure scenarios (invalid signatures, malformed data)
- Event data transformation and normalization
- Edge cases and security validation
- Customer data retrieval from Stripe API

The StripeSourcePlugin is responsible for validating webhook authenticity,
parsing event data, and triggering appropriate billing service handlers
for subscription management and payment processing.
"""

from unittest.mock import Mock, patch

from django.test import TestCase
from plugins.sources.base import InvalidDataError
from plugins.sources.stripe import StripeSourcePlugin


class StripeProviderTest(TestCase):
    """Test StripeSourcePlugin webhook handling."""

    def setUp(self) -> None:
        """Set up test data."""
        self.webhook_secret = "test_webhook_secret"
        self.provider = StripeSourcePlugin(self.webhook_secret)

    def _create_mock_request(self, body: str, signature: str | None = None) -> Mock:
        """Create a mock HTTP request for testing."""
        request = Mock()
        request.body = body.encode() if isinstance(body, str) else body
        request.headers = {}
        if signature:
            request.headers["Stripe-Signature"] = signature
        return request

    @patch("plugins.sources.stripe.stripe.Customer.retrieve")
    def test_get_customer_data_success(self, mock_retrieve: Mock) -> None:
        """Test getting customer data from Stripe API."""
        mock_retrieve.return_value = {
            "id": "cus_123",
            "email": "john@acme.com",
            "name": "John Doe",
            "metadata": {"company": "Acme Inc"},
            "deleted": False,
        }

        result = self.provider.get_customer_data("cus_123")

        expected = {
            "company_name": "Acme Inc",
            "email": "john@acme.com",
            "first_name": "John",
            "last_name": "Doe",
        }
        self.assertEqual(result, expected)
        mock_retrieve.assert_called_once_with("cus_123")

    @patch("plugins.sources.stripe.stripe.Customer.retrieve")
    def test_get_customer_data_no_company(self, mock_retrieve: Mock) -> None:
        """Test getting customer data without company metadata."""
        mock_retrieve.return_value = {
            "id": "cus_123",
            "email": "jane@example.com",
            "name": "Jane Smith",
            "metadata": {},
        }

        result = self.provider.get_customer_data("cus_123")

        self.assertEqual(result["company_name"], "")
        self.assertEqual(result["email"], "jane@example.com")
        self.assertEqual(result["first_name"], "Jane")
        self.assertEqual(result["last_name"], "Smith")

    @patch("plugins.sources.stripe.stripe.Customer.retrieve")
    def test_get_customer_data_single_name(self, mock_retrieve: Mock) -> None:
        """Test getting customer data with single name."""
        mock_retrieve.return_value = {
            "id": "cus_123",
            "email": "prince@example.com",
            "name": "Prince",
            "metadata": {},
        }

        result = self.provider.get_customer_data("cus_123")

        self.assertEqual(result["first_name"], "Prince")
        self.assertEqual(result["last_name"], "")

    @patch("plugins.sources.stripe.stripe.Customer.retrieve")
    def test_get_customer_data_deleted_customer(self, mock_retrieve: Mock) -> None:
        """Test getting data for deleted customer."""
        mock_customer = Mock()
        mock_customer.deleted = True
        mock_retrieve.return_value = mock_customer

        result = self.provider.get_customer_data("cus_deleted")

        expected = {
            "company_name": "",
            "email": "",
            "first_name": "",
            "last_name": "",
        }
        self.assertEqual(result, expected)

    @patch("plugins.sources.stripe.stripe.Customer.retrieve")
    def test_get_customer_data_api_error(self, mock_retrieve: Mock) -> None:
        """Test handling Stripe API errors."""
        import stripe.error

        mock_retrieve.side_effect = stripe.error.InvalidRequestError(
            "No such customer", "customer"
        )

        result = self.provider.get_customer_data("cus_invalid")

        expected = {
            "company_name": "",
            "email": "",
            "first_name": "",
            "last_name": "",
        }
        self.assertEqual(result, expected)

    def test_get_customer_data_empty_id(self) -> None:
        """Test getting customer data with empty ID."""
        result = self.provider.get_customer_data("")

        expected = {
            "company_name": "",
            "email": "",
            "first_name": "",
            "last_name": "",
        }
        self.assertEqual(result, expected)

    def test_build_stripe_event_data(self) -> None:
        """Test building Stripe event data structure."""
        data = {
            "id": "in_123",
            "status": "succeeded",
            "created": 1234567890,
            "currency": "usd",
        }

        result = self.provider._build_stripe_event_data(
            "payment_success", "cus_123", data, 20.00
        )

        expected = {
            "type": "payment_success",
            "customer_id": "cus_123",
            "provider": "stripe",
            "external_id": "in_123",
            "status": "succeeded",
            "created_at": 1234567890,
            "currency": "USD",
            "amount": 20.00,
            "metadata": {},
        }

        self.assertEqual(result, expected)

    def test_build_stripe_event_data_default_currency(self) -> None:
        """Test building event data with missing currency."""
        data = {"id": "in_123", "status": "succeeded", "created": 1234567890}

        result = self.provider._build_stripe_event_data(
            "payment_success", "cus_123", data, 20.00
        )

        self.assertEqual(result["currency"], "USD")
        self.assertEqual(result["external_id"], "in_123")

    def test_handle_stripe_billing_unknown_event(self) -> None:
        """Test handling unknown billing event returns 0."""
        data = {"amount_due": 1500}

        amount = self.provider._handle_stripe_billing("unknown_event", data)

        self.assertEqual(amount, 0.0)

    def test_handle_stripe_billing_missing_amount(self) -> None:
        """Test handling payment events with missing amount returns 0."""
        data = {}  # Missing amount_paid

        amount = self.provider._handle_stripe_billing("payment_success", data)

        self.assertEqual(amount, 0.0)

    def test_handle_stripe_billing_missing_plan_amount(self) -> None:
        """Test handling subscription created with missing plan amount."""
        data = {"plan": {}}  # Missing amount

        amount = self.provider._handle_stripe_billing("subscription_created", data)

        self.assertEqual(amount, 0.0)

    def test_handle_stripe_billing_converts_cents_to_dollars(self) -> None:
        """Test that billing amounts are converted from cents to dollars."""
        data = {"amount_paid": 2500}  # 2500 cents = $25.00

        amount = self.provider._handle_stripe_billing("payment_success", data)

        self.assertEqual(amount, 25.00)

    def test_handle_stripe_billing_payment_success_uses_amount_paid(self) -> None:
        """Test that payment_success uses amount_paid, not amount_due."""
        data = {
            "amount_due": 0,  # After payment, amount_due is 0
            "amount_paid": 5000,  # $50.00
        }

        amount = self.provider._handle_stripe_billing("payment_success", data)

        self.assertEqual(amount, 50.00)

    def test_extract_stripe_event_info_subscription_created(self) -> None:
        """Test extracting event info for subscription created."""
        mock_event = Mock()
        mock_event.type = "customer.subscription.created"
        mock_event.data.object = {"id": "sub_123", "customer": "cus_123"}

        event_type, data = self.provider._extract_stripe_event_info(mock_event)

        self.assertEqual(event_type, "subscription_created")
        self.assertEqual(data["id"], "sub_123")

    def test_extract_stripe_event_info_payment_success(self) -> None:
        """Test extracting event info for payment success."""
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

    def test_extract_stripe_event_info_payment_failure(self) -> None:
        """Test extracting event info for payment failure."""
        mock_event = Mock()
        mock_event.type = "invoice.payment_failed"
        mock_event.data.object = {
            "id": "in_123",
            "customer": "cus_123",
            "amount_due": 2000,
        }

        event_type, data = self.provider._extract_stripe_event_info(mock_event)

        self.assertEqual(event_type, "payment_failure")

    def test_extract_stripe_event_info_unsupported_event(self) -> None:
        """Test extracting info for unsupported event type returns None.

        Unsupported events should be acknowledged but not processed,
        so the method returns (None, None) instead of raising an error.
        """
        mock_event = Mock()
        mock_event.type = "unsupported.event.type"

        event_type, data = self.provider._extract_stripe_event_info(mock_event)

        self.assertIsNone(event_type)
        self.assertIsNone(data)

    def test_extract_stripe_event_info_customer_updated_returns_none(self) -> None:
        """Test that customer.updated event type is acknowledged but not processed.

        The customer.updated event is informational and doesn't require
        notification processing, so it should return (None, None).
        """
        mock_event = Mock()
        mock_event.type = "customer.updated"

        event_type, data = self.provider._extract_stripe_event_info(mock_event)

        self.assertIsNone(event_type)
        self.assertIsNone(data)

    def test_extract_stripe_event_info_missing_event_type(self) -> None:
        """Test extracting info with missing event type."""
        mock_event = Mock()
        mock_event.type = None

        with self.assertRaises(InvalidDataError):
            self.provider._extract_stripe_event_info(mock_event)

    def test_extract_stripe_event_info_missing_data(self) -> None:
        """Test extracting info with missing data."""
        mock_event = Mock()
        mock_event.type = "invoice.payment_succeeded"
        mock_event.data.object = None

        with self.assertRaises(InvalidDataError):
            self.provider._extract_stripe_event_info(mock_event)

    @patch("plugins.sources.stripe.settings.DISABLE_BILLING", True)
    def test_validate_webhook_billing_disabled(self) -> None:
        """Test webhook validation when billing is disabled."""
        request = self._create_mock_request(
            '{"type": "invoice.payment_succeeded"}', "t=123456789,v1=test_signature"
        )

        result = self.provider.validate_webhook(request)

        self.assertFalse(result)

    @patch("plugins.sources.stripe.stripe.Webhook.construct_event")
    def test_validate_webhook_success(self, mock_construct_event: Mock) -> None:
        """Test successful webhook validation."""
        # Mock successful validation
        mock_construct_event.return_value = Mock()

        request = self._create_mock_request(
            '{"type": "invoice.payment_succeeded"}', "t=123456789,v1=test_signature"
        )

        # Mock the billing settings to be enabled
        with patch("plugins.sources.stripe.settings.DISABLE_BILLING", False):
            result = self.provider.validate_webhook(request)

        self.assertTrue(result)
        mock_construct_event.assert_called_once_with(
            request.body, "t=123456789,v1=test_signature", self.webhook_secret
        )

    @patch("plugins.sources.stripe.stripe.Webhook.construct_event")
    def test_validate_webhook_invalid_signature(
        self, mock_construct_event: Mock
    ) -> None:
        """Test webhook validation with invalid signature."""
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

    def test_validate_webhook_missing_signature(self) -> None:
        """Test webhook validation with missing signature."""
        request = self._create_mock_request('{"type": "invoice.payment_succeeded"}')

        result = self.provider.validate_webhook(request)

        self.assertFalse(result)

    @patch("plugins.sources.stripe.stripe.Webhook.construct_event")
    def test_parse_webhook_success(self, mock_construct_event: Mock) -> None:
        """Test successful webhook parsing."""
        # Mock Stripe event
        mock_event = Mock()
        mock_event.type = "invoice.payment_succeeded"
        mock_event.data.object = Mock()
        mock_event.data.object.to_dict.return_value = {
            "id": "in_123",
            "customer": "cus_123",
            "amount_paid": 2000,  # 2000 cents = $20.00
            "currency": "usd",
            "status": "succeeded",
            "created": 1234567890,
        }
        # Set previous_attributes to None to avoid item assignment error
        mock_event.data.previous_attributes = None
        mock_construct_event.return_value = mock_event

        request = self._create_mock_request(
            '{"type": "invoice.payment_succeeded"}', "t=123456789,v1=test_signature"
        )

        with patch.object(self.provider, "_handle_stripe_billing", return_value=20.00):
            result = self.provider.parse_webhook(request)

        expected = {
            "type": "payment_success",
            "customer_id": "cus_123",
            "provider": "stripe",
            "external_id": "in_123",
            "status": "succeeded",
            "created_at": 1234567890,
            "currency": "USD",
            "amount": 20.00,
            "metadata": {},
        }

        self.assertEqual(result, expected)

    def test_parse_webhook_missing_signature(self) -> None:
        """Test parsing webhook without signature."""
        request = self._create_mock_request('{"type": "invoice.payment_succeeded"}')

        with self.assertRaises(InvalidDataError) as context:
            self.provider.parse_webhook(request)

        self.assertIn("Missing Stripe signature", str(context.exception))

    @patch("plugins.sources.stripe.stripe.Webhook.construct_event")
    def test_parse_webhook_invalid_signature(self, mock_construct_event: Mock) -> None:
        """Test parsing webhook with invalid signature."""
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

    @patch("plugins.sources.stripe.stripe.Webhook.construct_event")
    def test_parse_webhook_unsupported_event_returns_none(
        self, mock_construct_event: Mock
    ) -> None:
        """Test that parsing unsupported event types returns None.

        Unsupported event types (like customer.updated) should be acknowledged
        with a success response but not processed further.
        """
        mock_event = Mock()
        mock_event.type = "customer.updated"
        mock_construct_event.return_value = mock_event

        request = self._create_mock_request(
            '{"type": "customer.updated"}', "t=123456789,v1=test_signature"
        )

        result = self.provider.parse_webhook(request)

        self.assertIsNone(result)

    def test_handle_stripe_billing_trial_conversion_detected(self) -> None:
        """Test that trial conversion is detected for subscription_cycle payments."""
        data = {
            "amount_paid": 2660,  # $26.60
            "billing_reason": "subscription_cycle",
        }

        self.provider._handle_stripe_billing("payment_success", data)

        self.assertTrue(data.get("_is_trial_conversion"))

    def test_handle_stripe_billing_no_trial_conversion_for_zero_amount(self) -> None:
        """Test that trial conversion is not set for $0 payments."""
        data = {
            "amount_paid": 0,
            "billing_reason": "subscription_cycle",
        }

        self.provider._handle_stripe_billing("payment_success", data)

        self.assertIsNone(data.get("_is_trial_conversion"))

    def test_handle_stripe_billing_no_trial_conversion_for_manual_payment(self) -> None:
        """Test that trial conversion is not set for manual billing."""
        data = {
            "amount_paid": 2660,
            "billing_reason": "manual",
        }

        self.provider._handle_stripe_billing("payment_success", data)

        self.assertIsNone(data.get("_is_trial_conversion"))

    def test_handle_stripe_billing_upgrade_detected(self) -> None:
        """Test that subscription upgrade is detected from plan amount change."""
        data = {
            "plan": {"amount": 5000},  # $50/mo current
            "_previous_attributes": {
                "plan": {"amount": 2500},  # $25/mo previous
            },
        }

        self.provider._handle_stripe_billing("subscription_updated", data)

        self.assertEqual(data.get("_change_direction"), "upgrade")

    def test_handle_stripe_billing_downgrade_detected(self) -> None:
        """Test that subscription downgrade is detected from plan amount change."""
        data = {
            "plan": {"amount": 2500},  # $25/mo current
            "_previous_attributes": {
                "plan": {"amount": 5000},  # $50/mo previous
            },
        }

        self.provider._handle_stripe_billing("subscription_updated", data)

        self.assertEqual(data.get("_change_direction"), "downgrade")

    def test_handle_stripe_billing_same_amount_is_other(self) -> None:
        """Test that same plan amount results in 'other' change direction."""
        data = {
            "plan": {"amount": 2500},
            "_previous_attributes": {
                "plan": {"amount": 2500},
            },
        }

        self.provider._handle_stripe_billing("subscription_updated", data)

        self.assertEqual(data.get("_change_direction"), "other")

    def test_handle_stripe_billing_no_previous_attributes_no_direction(self) -> None:
        """Test that missing previous_attributes doesn't set change direction."""
        data = {
            "plan": {"amount": 2500},
        }

        self.provider._handle_stripe_billing("subscription_updated", data)

        self.assertIsNone(data.get("_change_direction"))

    def test_build_stripe_event_data_includes_trial_conversion_metadata(self) -> None:
        """Test that trial conversion flag is included in event metadata."""
        data = {
            "id": "in_123",
            "status": "succeeded",
            "created": 1234567890,
            "currency": "usd",
            "_is_trial_conversion": True,
        }

        result = self.provider._build_stripe_event_data(
            "payment_success", "cus_123", data, 26.60
        )

        self.assertTrue(result["metadata"]["is_trial_conversion"])

    def test_build_stripe_event_data_includes_change_direction_metadata(self) -> None:
        """Test that change direction is included in event metadata."""
        data = {
            "id": "sub_123",
            "status": "active",
            "created": 1234567890,
            "_change_direction": "upgrade",
        }

        result = self.provider._build_stripe_event_data(
            "subscription_updated", "cus_123", data, 50.00
        )

        self.assertEqual(result["metadata"]["change_direction"], "upgrade")

    def test_extract_stripe_event_info_captures_previous_attributes(self) -> None:
        """Test that previous_attributes are captured from Stripe events."""
        mock_event = Mock()
        mock_event.type = "customer.subscription.updated"
        mock_event.data.object = {"id": "sub_123", "plan": {"amount": 5000}}
        mock_event.data.previous_attributes = {"plan": {"amount": 2500}}

        event_type, data = self.provider._extract_stripe_event_info(mock_event)

        self.assertEqual(event_type, "subscription_updated")
        self.assertEqual(data["_previous_attributes"]["plan"]["amount"], 2500)
