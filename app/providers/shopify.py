from typing import Dict, Any, Optional
from flask import Request
import hmac
import hashlib
import logging
import base64
from datetime import datetime

from .base import PaymentProvider, InvalidDataError

logger = logging.getLogger(__name__)


class ShopifyProvider(PaymentProvider):
    """Shopify payment provider implementation"""

    def validate_webhook(self, request: Request) -> bool:
        """Validate webhook signature"""
        try:
            # If no webhook secret is configured, skip validation
            if not self.webhook_secret:
                logger.info("No webhook secret configured, skipping validation")
                return True

            signature = request.headers.get("X-Shopify-Hmac-SHA256")
            topic = request.headers.get("X-Shopify-Topic")
            shop_domain = request.headers.get("X-Shopify-Shop-Domain")

            logger.debug(
                "Validating Shopify webhook",
                extra={
                    "topic": topic,
                    "shop_domain": shop_domain,
                    "has_signature": bool(signature),
                    "content_type": request.content_type,
                    "headers": dict(request.headers),
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

            # Log raw data for debugging
            logger.debug(
                "Webhook signature details",
                extra={
                    "topic": topic,
                    "shop_domain": shop_domain,
                    "body_length": len(body),
                    "secret_length": len(self.webhook_secret),
                    "expected_signature": expected_signature,
                    "received_signature": signature,
                },
            )

            is_valid = hmac.compare_digest(signature, expected_signature)
            if not is_valid:
                logger.warning(
                    "Invalid webhook signature",
                    extra={
                        "topic": topic,
                        "shop_domain": shop_domain,
                        "expected_signature": expected_signature,
                        "received_signature": signature,
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

    def parse_webhook(self, request: Request) -> Optional[Dict[str, Any]]:
        """Parse webhook data based on event type"""
        # Handle JSON data only
        if request.content_type != "application/json":
            logger.error(
                "Invalid content type",
                extra={
                    "content_type": request.content_type,
                    "expected": "application/json",
                },
            )
            raise InvalidDataError("Invalid content type")

        try:
            data = request.get_json()
            logger.debug(
                "Parsing Shopify webhook data",
                extra={
                    "content_type": request.content_type,
                    "json_data": data,
                    "headers": dict(request.headers),
                },
            )

            if data is None or not isinstance(data, dict):
                logger.error("Empty webhook data")
                raise InvalidDataError("Empty webhook data")

            if not data:  # Empty dict
                logger.error("Missing required fields")
                raise InvalidDataError("Missing required fields")

            # Extract required fields
            customer_id = data.get("customer", {}).get("id") or data.get("id")
            if not customer_id:
                logger.error(
                    "Missing required fields",
                    extra={"available_fields": list(data.keys())},
                )
                raise InvalidDataError("Missing required fields")
            customer_id = str(customer_id)

            # Get webhook topic from header
            topic = request.headers.get("X-Shopify-Topic", "unknown")
            event_type = topic.replace("/", "_")

            # Extract amount if available
            amount = 0.0
            if "total_price" in data:
                try:
                    amount = float(data["total_price"])
                except (ValueError, TypeError):
                    logger.warning(
                        "Invalid amount format",
                        extra={"total_price": data.get("total_price")},
                    )

            # Get customer info
            customer = data.get("customer", {})
            company = customer.get("company") or data.get("company")
            team_size = 0

            # Try to get team size from metafields
            metafields = customer.get("metafields", []) or data.get("metafields", [])
            for field in metafields:
                if field.get("key") == "team_size":
                    try:
                        team_size = int(field["value"])
                    except (ValueError, TypeError):
                        logger.warning(
                            "Invalid team size",
                            extra={"value": field.get("value")},
                        )

            # Try to get team size from line item properties if not found in metafields
            if team_size == 0 and "line_items" in data:
                for item in data["line_items"]:
                    for prop in item.get("properties", []):
                        if prop.get("name") == "team_size":
                            try:
                                team_size = int(prop["value"])
                                break
                            except (ValueError, TypeError):
                                logger.warning(
                                    "Invalid team size in line item",
                                    extra={"value": prop.get("value")},
                                )
                    if team_size > 0:
                        break

            # Get plan info from line items
            plan_name = None
            if "line_items" in data:
                for item in data["line_items"]:
                    if item.get("title"):
                        plan_name = item["title"]
                        break

            # Build metadata
            metadata = {
                "source": "shopify",
                "shop_domain": request.headers.get("X-Shopify-Shop-Domain"),
                "order_number": data.get("order_number"),
            }

            # Add customer tags if available
            if "tags" in customer:
                metadata["customer_tags"] = customer["tags"]

            # Add metafields to metadata
            if metafields:
                for field in metafields:
                    if field.get("key") and field.get("value"):
                        metadata[field["key"]] = field["value"]

            return {
                "id": f"evt_{customer_id}_{data.get('id', '')}",
                "type": event_type,
                "customer_id": customer_id,
                "amount": amount,
                "currency": data.get("currency", "USD"),
                "status": "success",  # Shopify only sends successful webhooks
                "timestamp": data.get("created_at") or datetime.utcnow().isoformat(),
                "metadata": metadata,
                "customer_data": {
                    "company_name": company or "Unknown",
                    "team_size": team_size,
                    "plan_name": plan_name or "Unknown",
                },
            }

        except InvalidDataError:
            raise
        except Exception as e:
            logger.error(
                "Error parsing Shopify webhook",
                extra={"error": str(e)},
                exc_info=True,
            )
            raise InvalidDataError(f"Failed to parse webhook data: {str(e)}")
