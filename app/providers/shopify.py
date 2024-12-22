from typing import Dict, Any, Optional
from flask import Request
import hmac
import hashlib

from .base import PaymentProvider, InvalidDataError


class ShopifyProvider(PaymentProvider):
    """Shopify payment provider implementation"""

    def validate_webhook(self, request: Request) -> bool:
        """Validate webhook signature"""
        try:
            signature = request.headers.get("X-Shopify-Hmac-SHA256")
            topic = request.headers.get("X-Shopify-Topic")
            shop_domain = request.headers.get("X-Shopify-Shop-Domain")

            if not signature or not topic or not shop_domain:
                return False

            body = request.get_data()
            expected_signature = hmac.new(
                self.webhook_secret.encode(),
                body,
                hashlib.sha256,
            ).hexdigest()

            return hmac.compare_digest(signature, expected_signature)
        except Exception as e:
            print(f"Error validating Shopify webhook: {e}")
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

            # Get and validate data
            data = request.get_json()
            if not data:
                raise InvalidDataError("Empty webhook data")

            # Map topic to event type
            event_type = webhook_topic.replace("/", "_")
            customer = data.get("customer", {})
            if not customer:
                raise InvalidDataError("Missing customer data")

            customer_id = customer.get("id")
            if not customer_id:
                raise InvalidDataError("Missing customer ID")

            # Extract amount and validate
            amount = 0.0
            if webhook_topic in ["orders/create", "orders/paid"]:
                try:
                    amount = float(data.get("total_price", "0"))
                    if amount < 0:
                        raise InvalidDataError("Amount cannot be negative")
                except ValueError:
                    raise InvalidDataError("Invalid amount format")

            # Validate currency
            currency = data.get("currency", "USD")
            if not currency or len(currency) != 3:
                raise InvalidDataError("Invalid currency code")

            return {
                "id": str(data.get("id", "")),
                "type": event_type,
                "customer_id": str(customer_id),
                "amount": amount,
                "currency": currency,
                "status": "success"
                if data.get("financial_status") == "paid"
                else "failed",
                "timestamp": data.get("created_at"),
                "metadata": {
                    "source": "shopify",
                    "order_id": data.get("id"),
                    "shop_domain": shop_domain,
                    "customer_email": customer.get("email"),
                    "customer_name": f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip(),
                },
                "customer_data": {
                    "company_name": customer.get("company", "Unknown"),
                    "team_size": int(customer.get("team_size", 0)),
                    "plan_name": data.get("plan_name", "Unknown"),
                    "created_at": customer.get("created_at"),
                },
            }

        except (InvalidDataError, ValueError) as e:
            print(f"Error parsing Shopify webhook: {e}")
            raise
        except Exception as e:
            print(f"Error parsing Shopify webhook: {e}")
            return None
