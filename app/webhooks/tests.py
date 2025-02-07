from django.test import TestCase, Client


class ChargifyWebhookTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.url = "webhook/chargify/"
        self.headers = {
            "HTTP_X-Chargify-Webhook-Signature-Hmac-Sha-256": "your_signature",
            "HTTP_X-Chargify-Webhook-Id": "12345",
        }
        self.data = {
            "event": "payment_success",
            "payload[subscription][customer][id]": "123",
            "payload[transaction][amount_in_cents]": "1000",
        }

    def test_valid_webhook(self):
        response = self.client.post(
            self.url,
            self.data,
            content_type="application/x-www-form-urlencoded",
            **self.headers,
        )
        self.assertEqual(response.status_code, 200)

    def test_invalid_signature(self):
        headers = self.headers.copy()
        headers["HTTP_X-Chargify-Webhook-Signature-Hmac-Sha-256"] = "invalid_signature"
        response = self.client.post(
            self.url,
            self.data,
            content_type="application/x-www-form-urlencoded",
            **headers,
        )
        self.assertEqual(response.status_code, 400)
