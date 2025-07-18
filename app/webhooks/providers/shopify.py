# providers/shopify.py
import base64
import hashlib
import hmac
import json
import logging
from typing import Any, Dict, Optional

from django.http import HttpRequest

from .base import CustomerNotFoundError, InvalidDataError, PaymentProvider

logger = logging.getLogger(__name__)


class ShopifyProvider(PaymentProvider):
    """Handle Shopify webhooks and customer data"""

    EVENT_TYPE_MAPPING = {
        "orders/paid": "payment_success",
        "orders/cancelled": "payment_cancelled",
        "customers/update": "customers/update",
        "test": "test",
    }

    def __init__(self, webhook_secret: str):
        """Initialize provider with webhook secret"""

        super().__init__(webhook_secret)
        self._current_webhook_data = None

    def _validate_shopify_request(self, request: HttpRequest) -> str:
        """Validate Shopify webhook request and return topic"""
        if request.content_type != "application/json":
            raise InvalidDataError("Invalid content type")

        topic = request.headers.get("X-Shopify-Topic")
        if not topic:
            raise InvalidDataError("Missing webhook topic")

        return topic

    def _parse_shopify_json(self, request: HttpRequest) -> Dict[str, Any]:
        """Parse and validate Shopify JSON data"""
        try:
            data = json.loads(request.data)
        except (json.JSONDecodeError, AttributeError) as e:
            raise InvalidDataError("Invalid JSON data") from e

        if not isinstance(data, dict):
            raise InvalidDataError("Invalid JSON data")
        if not data:
            raise InvalidDataError("Missing required fields")

        return data

    def _is_test_webhook(self, topic: str, request: HttpRequest) -> bool:
        """Check if this is a test webhook"""
        return (
            topic == "test"
            or request.headers.get("X-Shopify-Test", "").lower() == "true"
        )

    def _extract_shopify_customer_id(self, data: Dict[str, Any]) -> str:
        """Extract customer ID from Shopify webhook data"""
        try:
            if "customer" in data:
                customer_id = str(data["customer"]["id"])
            elif "order" in data and "customer" in data["order"]:
                customer_id = str(data["order"]["customer"]["id"])
            else:
                customer_id = data.get("id")
                if not customer_id:
                    raise InvalidDataError("Missing required fields")
                customer_id = str(customer_id)

            if not customer_id:
                raise InvalidDataError("Missing required fields")

            return customer_id
        except (KeyError, ValueError) as e:
            raise InvalidDataError("Missing required fields") from e

    def _build_shopify_event_data(
        self,
        event_type: str,
        customer_id: str,
        data: Dict[str, Any],
        topic: str,
    ) -> Dict[str, Any]:
        """Build Shopify event data structure"""
        event_data = {
            "type": event_type,
            "customer_id": customer_id,
            "provider": "shopify",
            "created_at": data.get("created_at"),
            "status": "success",  # Default status
            "metadata": {
                "order_number": data.get("order_number"),
                "order_ref": (
                    str(data.get("order_number"))
                    if data.get("order_number")
                    else None
                ),
                "financial_status": data.get("financial_status"),
                "fulfillment_status": data.get("fulfillment_status"),
            },
        }

        # Add amount if present
        if "total_price" in data:
            try:
                event_data["amount"] = float(data["total_price"])
            except (ValueError, TypeError) as e:
                raise InvalidDataError("Missing required fields") from e

        # Add currency if present
        if "currency" in data:
            event_data["currency"] = data["currency"]

        # For customer updates, include customer data
        if topic == "customers/update":
            event_data["customer_data"] = {
                "company": data.get("company", ""),
                "email": data.get("email", ""),
                "first_name": data.get("first_name", ""),
                "last_name": data.get("last_name", ""),
                "orders_count": data.get("orders_count", 0),
                "total_spent": data.get("total_spent", "0.00"),
            }

        return event_data

    def parse_webhook(self, request: HttpRequest) -> Optional[Dict[str, Any]]:
        """Parse Shopify webhook data"""
        # Validate request
        topic = self._validate_shopify_request(request)

        # Parse JSON data
        data = self._parse_shopify_json(request)

        # Store webhook data for later use
        self._current_webhook_data = data

        # Check for test webhook
        if self._is_test_webhook(topic, request):
            return None

        # Map webhook topic to event type
        event_type = self.EVENT_TYPE_MAPPING.get(topic)
        if not event_type:
            raise InvalidDataError(f"Unsupported webhook topic: {topic}")

        # Extract customer ID
        customer_id = self._extract_shopify_customer_id(data)

        # Build and return event data
        return self._build_shopify_event_data(event_type, customer_id, data, topic)

    def get_customer_data(self, customer_id: str) -> Dict[str, Any]:
        """Get customer data from stored webhook data"""
        if not self._current_webhook_data:
            raise CustomerNotFoundError("No webhook data available")

        data = self._current_webhook_data
        customer = data.get("customer", {})
        if not customer and "order" in data:
            customer = data["order"].get("customer", {})

        return {
            "company": customer.get("company", "Individual"),
            "email": customer.get("email", ""),
            "first_name": customer.get("first_name", ""),
            "last_name": customer.get("last_name", ""),
            "orders_count": customer.get("orders_count", 0),
            "total_spent": customer.get("total_spent", "0.00"),
            "metadata": {
                "shop_domain": data.get("shop_domain", ""),
                "tags": customer.get("tags", []),
                "note": customer.get("note", ""),
            },
        }

    def validate_webhook(self, request):
        """Validate the webhook signature"""
        hmac_header = request.headers.get("X-Shopify-Hmac-SHA256")
        if not hmac_header:
            return False

        if not isinstance(request.body, (bytes, bytearray)):
            raise TypeError("Expected bytes or bytearray for request body")

        message = request.body
        secret = (
            self.webhook_secret.encode("utf-8")
            if isinstance(self.webhook_secret, str)
            else self.webhook_secret
        )

        digest = hmac.new(secret, message, hashlib.sha256).digest()
        calculated_hmac = base64.b64encode(digest).decode("utf-8")
        return hmac.compare_digest(hmac_header, calculated_hmac)
