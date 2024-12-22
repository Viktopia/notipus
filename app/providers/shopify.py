import hashlib
import hmac
from datetime import datetime
from typing import Optional

from .base import (
    PaymentProvider,
    PaymentEvent,
    WebhookValidationError,
    InvalidDataError,
)

SUPPORTED_TOPICS = {
    "orders/create": "order_created",
    "orders/paid": "payment_success",
    "orders/cancelled": "order_cancelled",
    "subscriptions/create": "subscription_created",
    "subscriptions/update": "subscription_updated",
    "subscriptions/cancel": "subscription_cancelled",
}


class ShopifyProvider(PaymentProvider):
    def __init__(self, webhook_secret: str):
        self.webhook_secret = webhook_secret
        self._shop_domain: Optional[str] = None

    @property
    def shop_domain(self) -> Optional[str]:
        """Get the Shopify shop domain from the last webhook."""
        return self._shop_domain

    def validate_webhook(self, headers: dict, body: bytes) -> bool:
        """Validate the webhook signature and authenticity."""
        if "X-Shopify-Hmac-SHA256" not in headers:
            raise WebhookValidationError("Missing Shopify webhook signature")

        if "X-Shopify-Topic" not in headers:
            raise WebhookValidationError("Missing Shopify webhook topic")

        if "X-Shopify-Shop-Domain" not in headers:
            raise WebhookValidationError("Missing Shopify shop domain")

        # Store the shop domain for later use
        self._shop_domain = headers["X-Shopify-Shop-Domain"]

        # Verify the topic is supported
        topic = headers["X-Shopify-Topic"]
        if topic not in SUPPORTED_TOPICS:
            raise WebhookValidationError(f"Unsupported webhook topic: {topic}")

        # Validate the HMAC signature
        expected_signature = headers["X-Shopify-Hmac-SHA256"]
        computed_signature = hmac.new(
            self.webhook_secret.encode(), body, hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(computed_signature, expected_signature)

    def parse_webhook(self, data: dict, topic: Optional[str] = None) -> PaymentEvent:
        """Parse webhook data into a standardized PaymentEvent."""
        try:
            if not data:
                raise InvalidDataError("Empty webhook data")

            if not topic:
                raise InvalidDataError("Missing webhook topic")

            order = data
            customer = order.get("customer", {})
            customer_id = str(customer.get("id", ""))
            amount = float(order.get("total_price", "0"))
            currency = order.get("currency", "USD")
            created_at = order.get("created_at")
            financial_status = order.get("financial_status")

            if not all([customer_id, created_at]):
                raise InvalidDataError(
                    "Missing required fields: customer_id or created_at"
                )

            timestamp = datetime.fromisoformat(created_at.replace("Z", "+00:00"))

            # Map the webhook topic to our internal event type
            event_type = SUPPORTED_TOPICS.get(topic, "unknown")

            # Determine status based on financial_status
            status = "success" if financial_status == "paid" else "pending"

            return PaymentEvent(
                id=str(order.get("id", "")),
                event_type=event_type,
                customer_id=customer_id,
                amount=amount,
                currency=currency,
                status=status,
                timestamp=timestamp,
                subscription_id=order.get("subscription_contract_id"),
                error_message=None,
                retry_count=0,
            )
        except (KeyError, ValueError) as e:
            raise InvalidDataError(f"Failed to parse Shopify webhook: {str(e)}")
