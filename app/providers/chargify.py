import hashlib
import hmac
from datetime import datetime
from typing import Set

from .base import (
    PaymentProvider,
    PaymentEvent,
    WebhookValidationError,
    InvalidDataError,
)

SUPPORTED_EVENTS = {
    "payment_success",
    "payment_failure",
    "subscription_state_change",
    "subscription_product_change",
    "subscription_billing_date_change",
    "payment_success_recurring",
    "payment_failure_recurring",
    "renewal_success",
    "renewal_failure",
    "trial_end",
    "trial_end_notice",
    "dunning_step_reached",
    "billing_date_change",
    "subscription_canceled",
}


class ChargifyProvider(PaymentProvider):
    def __init__(self, webhook_secret: str):
        self.webhook_secret = webhook_secret
        self._processed_webhook_ids: Set[str] = set()

    def validate_webhook(self, headers: dict, body: bytes) -> bool:
        """Validate the webhook signature and authenticity."""
        if "X-Chargify-Webhook-Signature-Hmac-Sha-256" not in headers:
            raise WebhookValidationError("Missing Chargify webhook signature")

        if "X-Chargify-Webhook-Id" not in headers:
            raise WebhookValidationError("Missing Chargify webhook ID")

        # Prevent replay attacks by checking webhook ID
        webhook_id = headers["X-Chargify-Webhook-Id"]
        if webhook_id in self._processed_webhook_ids:
            raise WebhookValidationError("Duplicate webhook ID detected")
        self._processed_webhook_ids.add(webhook_id)

        # Keep the set size manageable
        if len(self._processed_webhook_ids) > 1000:
            self._processed_webhook_ids.clear()

        # Validate the HMAC signature
        expected_signature = headers["X-Chargify-Webhook-Signature-Hmac-Sha-256"]
        computed_signature = hmac.new(
            self.webhook_secret.encode(), body, hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(computed_signature, expected_signature)

    def parse_webhook(self, data: dict) -> PaymentEvent:
        """Parse webhook data into a standardized PaymentEvent."""
        try:
            if not data:
                raise InvalidDataError("Empty webhook data")

            event_id = data.get("id")
            event_type = data.get("event")
            if event_type not in SUPPORTED_EVENTS:
                raise InvalidDataError(f"Unsupported event type: {event_type}")

            # Extract customer data from the payload
            customer_id = data.get("payload[subscription][customer][id]")
            if not customer_id:
                customer_id = data.get("payload[customer][id]")

            if not all([event_id, event_type, customer_id]):
                raise InvalidDataError(
                    "Missing required fields: id, event, or customer_id"
                )

            # Extract amount and currency
            amount_cents = data.get("payload[transaction][amount_in_cents]", "0")
            amount = float(amount_cents) / 100 if amount_cents.isdigit() else 0
            currency = data.get("payload[transaction][currency]", "USD")

            # Extract subscription data
            subscription_id = data.get("payload[subscription][id]")
            created_at = data.get("created_at")
            if not created_at:
                raise InvalidDataError("Missing created_at timestamp")

            timestamp = datetime.fromisoformat(created_at.replace("Z", "+00:00"))

            # Extract status and error information
            success = (
                data.get("payload[transaction][success]", "false").lower() == "true"
            )
            status = "success" if success else "failed"
            error_message = data.get("payload[transaction][message]")
            retry_count = int(data.get("retry_count", 0))

            return PaymentEvent(
                id=event_id,
                event_type=event_type,
                customer_id=customer_id,
                amount=amount,
                currency=currency,
                status=status,
                timestamp=timestamp,
                subscription_id=subscription_id,
                error_message=error_message,
                retry_count=retry_count,
            )
        except (KeyError, ValueError) as e:
            raise InvalidDataError(f"Failed to parse Chargify webhook: {str(e)}")
