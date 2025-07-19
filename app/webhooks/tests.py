import json
from unittest.mock import Mock, patch

from django.test import TestCase

from .providers.stripe import StripeProvider


class ChargifyWebhookTest(TestCase):
    def setUp(self):
        self.url = "/webhook/chargify/"
        self.headers = {
            "HTTP_X_Chargify_Webhook_Id": "12345",
            "HTTP_X_Chargify_Webhook_Signature_Hmac_Sha_256": "test_signature",
        }
        self.data = {
            "event": "payment_success",
            "payload[subscription][customer][id]": "67890",
            "payload[subscription][customer][email]": "test@example.com",
            "payload[subscription][customer][first_name]": "Test",
            "payload[subscription][customer][last_name]": "User",
            "payload[subscription][id]": "11111",
            "payload[subscription][product][name]": "Premium Plan",
            "payload[transaction][id]": "22222",
            "payload[transaction][amount_in_cents]": "2999",
            "created_at": "2024-01-01T00:00:00Z",
        }

    @patch("django.conf.settings.EVENT_PROCESSOR")
    @patch("django.conf.settings.SLACK_CLIENT")
    @patch("django.conf.settings.CHARGIFY_PROVIDER")
    def test_valid_webhook(self, mock_provider, mock_slack, mock_processor):
        # Mock successful webhook processing
        mock_provider.validate_webhook.return_value = True
        mock_provider.parse_webhook.return_value = {
            "type": "payment_success",
            "customer_id": "67890",
        }
        mock_provider.get_customer_data.return_value = {
            "email": "test@example.com",
            "company": "Test Company",
        }
        mock_processor.format_notification.return_value = {"text": "Payment received"}

        response = self.client.post(
            self.url,
            self.data,
            content_type="application/x-www-form-urlencoded",
            **self.headers,
        )

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertEqual(response_data["status"], "success")

    @patch("django.conf.settings.CHARGIFY_PROVIDER")
    def test_invalid_signature(self, mock_provider):
        # Mock invalid signature
        mock_provider.validate_webhook.return_value = False

        headers = self.headers.copy()
        headers["HTTP_X_Chargify_Webhook_Signature_Hmac_Sha_256"] = "invalid_signature"
        response = self.client.post(
            self.url,
            self.data,
            content_type="application/x-www-form-urlencoded",
            **headers,
        )
        # Our improved error handling returns 400 for validation errors
        self.assertEqual(response.status_code, 400)
        response_data = json.loads(response.content)
        self.assertEqual(response_data["status"], "error")
        self.assertEqual(response_data["error"]["code"], "INVALID_SIGNATURE")


class StripeProviderTest(TestCase):
    """Test StripeProvider webhook handling"""

    def setUp(self):
        """Set up test data"""
        self.webhook_secret = "test_webhook_secret"
        self.provider = StripeProvider(self.webhook_secret)

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
        data = {
            "status": "succeeded",
            "created": 1234567890,
            "currency": "usd"
        }

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

    def test_extract_stripe_event_info_unsupported_event(self):
        """Test extracting info for unsupported event type"""
        from .providers.base import InvalidDataError

        mock_event = Mock()
        mock_event.type = "unsupported.event.type"

        with self.assertRaises(InvalidDataError):
            self.provider._extract_stripe_event_info(mock_event)

    def test_extract_stripe_event_info_missing_event_type(self):
        """Test extracting info with missing event type"""
        from .providers.base import InvalidDataError

        mock_event = Mock()
        mock_event.type = None

        with self.assertRaises(InvalidDataError):
            self.provider._extract_stripe_event_info(mock_event)
