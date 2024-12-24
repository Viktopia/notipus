from typing import Dict, Any, Optional
from flask import Request, current_app
import hmac
import hashlib
import logging
import base64
import json

from .base import PaymentProvider, InvalidDataError, CustomerNotFoundError

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

    def parse_webhook(self, request: Request) -> Optional[Dict[str, Any]]:
        """Parse Shopify webhook data"""
        # Validate content type
        if request.content_type != "application/json":
            raise InvalidDataError("Invalid content type")

        # Get webhook topic first
        topic = request.headers.get("X-Shopify-Topic")
        if not topic:
            raise InvalidDataError("Missing webhook topic")

        # Parse JSON data
        try:
            data = (
                request.get_json()
                if hasattr(request, "get_json")
                else json.loads(request.data.decode("utf-8"))
            )
        except (json.JSONDecodeError, AttributeError):
            raise InvalidDataError("Invalid JSON data")

        # Store webhook data for later use
        self._current_webhook_data = data

        # Check for empty data
        if not isinstance(data, dict):
            raise InvalidDataError("Invalid JSON data")
        if not data:
            raise InvalidDataError("Missing required fields")

        # Check for test webhook
        if (
            topic == "test"
            or request.headers.get("X-Shopify-Test", "").lower() == "true"
        ):
            return None

        # Map webhook topic to event type
        event_type = self.EVENT_TYPE_MAPPING.get(topic)
        if not event_type:
            raise InvalidDataError(f"Unsupported webhook topic: {topic}")

        # Extract customer ID and other required fields
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

            # Build event data
            event_data = {
                "type": event_type,
                "customer_id": customer_id,
                "provider": "shopify",
                "created_at": data.get("created_at"),
                "status": "success",  # Default status
                "metadata": {
                    "order_number": data.get("order_number"),
                    "order_ref": str(data.get("order_number")) if data.get("order_number") else None,
                    "financial_status": data.get("financial_status"),
                    "fulfillment_status": data.get("fulfillment_status"),
                },
            }

            # Add amount if present
            if "total_price" in data:
                try:
                    event_data["amount"] = float(data["total_price"])
                except (ValueError, TypeError):
                    raise InvalidDataError("Missing required fields")

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

        except (KeyError, ValueError):
            raise InvalidDataError("Missing required fields")

    def get_customer_data(self, customer_id: str) -> Dict[str, Any]:
        """Get customer data from stored webhook data"""
        if not self._current_webhook_data:
            raise CustomerNotFoundError("No webhook data available")

        data = self._current_webhook_data
        customer = data.get("customer", {})
        if not customer and "order" in data:
            customer = data["order"].get("customer", {})

        return {
            "company": customer.get("company", ""),
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

    def validate_webhook(self, request: Request) -> bool:
        """Validate the webhook signature"""
        hmac_header = request.headers.get("X-Shopify-Hmac-SHA256")
        if not hmac_header:
            return False

        message = request.get_data()
        digest = hmac.new(
            self.webhook_secret.encode("utf-8"), message, hashlib.sha256
        ).digest()
        computed_hmac = base64.b64encode(digest).decode("utf-8")

        return hmac.compare_digest(computed_hmac, hmac_header)
