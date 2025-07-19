import json
from unittest.mock import patch

from django.test import TestCase


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
