from typing import Dict, Any, Optional
from flask import Request, current_app
import hmac
import hashlib
import logging

from .base import PaymentProvider, InvalidDataError

logger = logging.getLogger(__name__)


class ChargifyProvider(PaymentProvider):
    """Chargify payment provider implementation"""

    def validate_webhook(self, request: Request) -> bool:
        """Validate webhook signature"""
        try:
            signature = request.headers.get("X-Chargify-Webhook-Signature-Hmac-Sha-256")
            webhook_id = request.headers.get("X-Chargify-Webhook-Id")

            logger.info(
                "Validating Chargify webhook",
                extra={
                    "webhook_id": webhook_id,
                    "has_signature": bool(signature),
                    "content_type": request.content_type,
                    "headers": dict(request.headers),
                },
            )

            if not signature or not webhook_id:
                logger.warning(
                    "Missing required headers",
                    extra={
                        "webhook_id": webhook_id,
                        "has_signature": bool(signature),
                    },
                )
                return False

            body = request.get_data()
            expected_signature = hmac.new(
                self.webhook_secret.encode(),
                body,
                hashlib.sha256,
            ).hexdigest()

            is_valid = hmac.compare_digest(signature, expected_signature)
            if not is_valid:
                logger.warning(
                    "Invalid webhook signature",
                    extra={
                        "webhook_id": webhook_id,
                        "expected_signature": expected_signature,
                        "received_signature": signature,
                    },
                )

            return is_valid

        except Exception as e:
            logger.error(
                "Error validating Chargify webhook",
                extra={
                    "error": str(e),
                    "webhook_id": request.headers.get("X-Chargify-Webhook-Id"),
                },
                exc_info=True,
            )
            return False

    def parse_webhook(self, request: Request) -> Optional[Dict[str, Any]]:
        """Parse webhook data based on event type"""
        # Handle form-encoded data only
        if request.content_type != "application/x-www-form-urlencoded":
            raise InvalidDataError("Invalid content type")

        try:
            data = request.form.to_dict()
            if not data:
                raise InvalidDataError("Empty webhook data")

            event_type = data.get("event")
            if not event_type:
                raise InvalidDataError("Missing event type")

            # Extract customer data from form fields
            customer_id = data.get("payload[subscription][customer][id]")
            if not customer_id:
                raise InvalidDataError("Missing customer ID")

            # Extract and validate amount
            amount_in_cents = data.get("payload[transaction][amount_in_cents]", "0")
            try:
                amount = float(amount_in_cents) / 100 if amount_in_cents else 0.0
                if amount < 0:
                    raise InvalidDataError("Amount cannot be negative")
            except ValueError:
                raise InvalidDataError("Invalid amount format")

            # Extract customer info
            subscription_id = data.get("payload[subscription][id]")
            customer_email = data.get("payload[subscription][customer][email]")
            customer_name = f"{data.get('payload[subscription][customer][first_name]', '')} {data.get('payload[subscription][customer][last_name]', '')}".strip()
            organization = data.get("payload[subscription][customer][organization]")
            plan_name = data.get("payload[subscription][product][name]")

            return {
                "id": f"evt_{customer_id}",
                "type": event_type,
                "customer_id": str(customer_id),
                "amount": amount,
                "currency": "USD",  # Chargify always uses USD
                "status": "success" if "success" in event_type else "failed",
                "timestamp": data.get("created_at"),
                "metadata": {
                    "source": "chargify",
                    "subscription_id": subscription_id,
                    "customer_email": customer_email,
                    "customer_name": customer_name,
                },
                "customer_data": {
                    "company_name": organization or "Unknown",
                    "team_size": 0,  # Not provided in webhook
                    "plan_name": plan_name or "Unknown",
                },
            }

        except InvalidDataError:
            raise
        except Exception as e:
            logger.error(
                "Error parsing Chargify webhook",
                extra={"error": str(e)},
                exc_info=True,
            )
            raise InvalidDataError(f"Failed to parse webhook data: {str(e)}")
