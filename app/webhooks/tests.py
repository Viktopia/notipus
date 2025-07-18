from unittest.mock import Mock, patch

from django.test import Client, TestCase


class ChargifyWebhookTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.url = "/webhook/chargify/"  # Fixed: added leading slash
        self.headers = {
            "HTTP_X_Chargify_Webhook_Signature_Hmac_Sha_256": "test_signature",
            "HTTP_X_Chargify_Webhook_Id": "12345",
        }
        self.data = {
            "event": "payment_success",
            "payload[subscription][customer][id]": "123",
            "payload[transaction][amount_in_cents]": "1000",
        }

    @patch('django.conf.settings.CHARGIFY_PROVIDER')
    @patch('django.conf.settings.EVENT_PROCESSOR')
    @patch('django.conf.settings.SLACK_CLIENT')
    def test_valid_webhook(
        self, mock_slack_client, mock_event_processor, mock_provider
    ):
        # Mock the provider methods
        mock_provider.validate_webhook.return_value = True
        mock_provider.parse_webhook.return_value = {
            "customer_id": "123",
            "type": "payment_success"
        }
        mock_provider.get_customer_data.return_value = {"name": "Test Customer"}

        # Mock event processor
        mock_notification = Mock()
        mock_event_processor.format_notification.return_value = mock_notification

        # Mock slack client
        mock_slack_client.send_notification.return_value = True

        response = self.client.post(
            self.url,
            self.data,
            content_type="application/x-www-form-urlencoded",
            **self.headers,
        )
        self.assertEqual(response.status_code, 200)

        # Verify mocks were called
        mock_provider.validate_webhook.assert_called_once()
        mock_provider.parse_webhook.assert_called_once()

    @patch('django.conf.settings.CHARGIFY_PROVIDER')
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
        self.assertEqual(response.status_code, 401)  # Updated expected status code
