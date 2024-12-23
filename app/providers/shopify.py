from typing import Dict, Any, Optional
from flask import Request
import hmac
import hashlib
import logging
import base64

from .base import PaymentProvider, InvalidDataError

logger = logging.getLogger(__name__)


class ShopifyProvider(PaymentProvider):
    """Shopify payment provider implementation"""

    def validate_webhook(self, request: Request) -> bool:
        """Validate webhook signature"""
        try:
            signature = request.headers.get("X-Shopify-Hmac-SHA256")
            topic = request.headers.get("X-Shopify-Topic")
            shop_domain = request.headers.get("X-Shopify-Shop-Domain")

            logger.info(
                "Validating Shopify webhook",
                extra={
                    "topic": topic,
                    "shop_domain": shop_domain,
                    "has_signature": bool(signature),
                    "headers": dict(request.headers),
                    "content_type": request.content_type,
                },
            )

            if not signature or not topic or not shop_domain:
                logger.warning(
                    "Missing required headers",
                    extra={
                        "topic": topic,
                        "shop_domain": shop_domain,
                        "has_signature": bool(signature),
                    },
                )
                return False

            body = request.get_data()
            digest = hmac.new(
                self.webhook_secret.encode(),
                body,
                hashlib.sha256,
            ).digest()
            expected_signature = base64.b64encode(digest).decode()

            is_valid = hmac.compare_digest(signature, expected_signature)
            if not is_valid:
                logger.warning(
                    "Invalid webhook signature",
                    extra={
                        "topic": topic,
                        "shop_domain": shop_domain,
                        "received_signature": signature,
                        "expected_signature": expected_signature,
                        "body_length": len(body),
                    },
                )

            return is_valid

        except Exception as e:
            logger.error(
                "Error validating Shopify webhook",
                extra={
                    "error": str(e),
                    "topic": request.headers.get("X-Shopify-Topic"),
                    "shop_domain": request.headers.get("X-Shopify-Shop-Domain"),
                },
                exc_info=True,
            )
            return False

    def parse_webhook(self, request: Request, **kwargs) -> Optional[Dict[str, Any]]:
        """Parse webhook data based on topic"""
        try:
            # Get topic from request headers if not provided
            webhook_topic = request.headers.get("X-Shopify-Topic", "")
            if not webhook_topic:
                raise InvalidDataError("Missing webhook topic")

            # Get shop domain from headers
            shop_domain = request.headers.get("X-Shopify-Shop-Domain", "")
            if not shop_domain:
                raise InvalidDataError("Missing shop domain")

            # Check if this is a test webhook
            is_test = request.headers.get("X-Shopify-Test") == "true"
            if is_test:
                # For test webhooks, we still try to parse the data to validate format
                data = request.get_json()
                if not data:
                    raise InvalidDataError("Empty webhook data")

                return {
                    "id": str(data.get("id", "test_webhook")),
                    "type": webhook_topic.replace("/", "_"),
                    "customer_id": str(
                        data.get("customer", {}).get("id", "test_customer")
                    ),
                    "amount": float(data.get("total_price", 0)),
                    "currency": data.get("currency", "USD"),
                    "status": "test",
                    "timestamp": request.headers.get("X-Shopify-Triggered-At"),
                    "metadata": {
                        "source": "shopify",
                        "shop_domain": shop_domain,
                        "is_test": True,
                        "order_id": data.get("id"),
                        "customer_email": data.get("customer", {}).get("email"),
                        "customer_name": (
                            f"{data.get('customer', {}).get('first_name', '')} "
                            f"{data.get('customer', {}).get('last_name', '')}"
                        ).strip(),
                    },
                    "customer_data": {
                        "company_name": data.get("customer", {}).get(
                            "company", "Test Company"
                        ),
                        "team_size": int(data.get("customer", {}).get("team_size", 0)),
                        "plan_name": data.get("plan_name", "Test Plan"),
                    },
                }

            # Get and validate data
            data = request.get_json()
            if not data:
                raise InvalidDataError("Missing required fields")

            # Map topic to event type
            event_type = webhook_topic.replace("/", "_")

            # Handle different webhook topics
            if webhook_topic.startswith("orders/"):
                customer = data.get("customer", {})
                if not customer:
                    raise InvalidDataError("Missing required fields")

                # Extract team size from line items properties if available
                team_size = 0
                plan_name = "Unknown"
                for item in data.get("line_items", []):
                    for prop in item.get("properties", []):
                        if prop.get("name") == "team_size":
                            try:
                                team_size = int(prop.get("value", 0))
                            except ValueError:
                                pass
                        elif prop.get("name") == "plan_type":
                            plan_name = prop.get("value", "Unknown")

                return {
                    "id": str(data["id"]),
                    "type": event_type,
                    "customer_id": str(customer["id"]),
                    "amount": float(data["total_price"]),
                    "currency": data["currency"],
                    "status": "success"
                    if data["financial_status"] == "paid"
                    else "failed",
                    "timestamp": data["created_at"],
                    "metadata": {
                        "source": "shopify",
                        "shop_domain": shop_domain,
                        "order_number": data["order_number"],
                        "order_id": data["id"],
                        "customer_email": customer.get("email"),
                        "customer_name": (
                            f"{customer.get('first_name', '')} "
                            f"{customer.get('last_name', '')}"
                        ).strip(),
                        "plan_type": plan_name,
                    },
                    "customer_data": {
                        "company_name": customer.get("company", "Unknown"),
                        "team_size": team_size,
                        "plan_name": data.get("line_items", [{}])[0].get(
                            "title", "Unknown"
                        ),
                    },
                }

            elif webhook_topic.startswith("customers/"):
                if "id" not in data:
                    raise InvalidDataError("Missing required fields")

                # Extract team size and plan type from metafields if available
                team_size = 0
                plan_name = "Unknown"
                for metafield in data.get("metafields", []):
                    if (
                        metafield.get("namespace") == "customer"
                        and metafield.get("key") == "team_size"
                    ):
                        try:
                            team_size = int(metafield.get("value", 0))
                        except ValueError:
                            pass
                    elif (
                        metafield.get("namespace") == "subscription"
                        and metafield.get("key") == "plan_type"
                    ):
                        plan_name = metafield.get("value", "Unknown")

                return {
                    "id": str(data["id"]),
                    "type": event_type,
                    "customer_id": str(data["id"]),
                    "amount": float(data.get("total_spent", 0)),
                    "currency": "USD",
                    "status": "success",
                    "timestamp": data["updated_at"],
                    "metadata": {
                        "source": "shopify",
                        "shop_domain": shop_domain,
                        "customer_email": data.get("email"),
                        "customer_name": (
                            f"{data.get('first_name', '')} {data.get('last_name', '')}"
                        ).strip(),
                        "tags": data.get("tags", []),
                        "orders_count": data.get("orders_count", 0),
                        "plan_type": plan_name,
                    },
                    "customer_data": {
                        "company_name": data.get("company", "Unknown"),
                        "team_size": team_size,
                        "plan_name": plan_name,
                    },
                }

            else:
                raise InvalidDataError(f"Unsupported webhook topic: {webhook_topic}")

        except InvalidDataError:
            raise
        except Exception as e:
            logger.error(
                "Error parsing Shopify webhook",
                extra={"error": str(e)},
                exc_info=True,
            )
            raise InvalidDataError(f"Failed to parse webhook data: {str(e)}")
