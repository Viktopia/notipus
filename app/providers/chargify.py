from typing import Dict, Any, Optional
from flask import Request
import hmac
import hashlib
import logging
from datetime import datetime

from .base import PaymentProvider, InvalidDataError

logger = logging.getLogger(__name__)


class ChargifyProvider(PaymentProvider):
    """Chargify payment provider implementation"""

    def validate_webhook(self, request: Request) -> bool:
        """Validate webhook signature"""
        try:
            # If no webhook secret is configured, skip validation
            if not self.webhook_secret:
                logger.info("No webhook secret configured, skipping validation")
                return True

            # Try SHA-256 first, fall back to MD5
            signature = request.headers.get("X-Chargify-Webhook-Signature-Hmac-Sha-256")
            use_sha256 = bool(signature)

            if not signature:
                signature = request.headers.get("X-Chargify-Webhook-Signature")

            webhook_id = request.headers.get("X-Chargify-Webhook-Id")

            logger.info(
                "Validating Chargify webhook",
                extra={
                    "webhook_id": webhook_id,
                    "has_signature": bool(signature),
                    "signature_type": "sha256" if use_sha256 else "md5",
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
            if use_sha256:
                expected_signature = hmac.new(
                    self.webhook_secret.encode(),
                    body,
                    hashlib.sha256,
                ).hexdigest()
            else:
                expected_signature = hmac.new(
                    self.webhook_secret.encode(),
                    body,
                    hashlib.md5,
                ).hexdigest()

            # Log raw data for debugging
            logger.debug(
                "Webhook signature details",
                extra={
                    "webhook_id": webhook_id,
                    "body_length": len(body),
                    "secret_length": len(self.webhook_secret),
                    "signature_type": "sha256" if use_sha256 else "md5",
                    "expected_signature": expected_signature,
                    "received_signature": signature,
                },
            )

            is_valid = hmac.compare_digest(
                signature.lower(), expected_signature.lower()
            )
            if not is_valid:
                logger.warning(
                    "Invalid webhook signature",
                    extra={
                        "webhook_id": webhook_id,
                        "signature_type": "sha256" if use_sha256 else "md5",
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
            logger.error(
                "Invalid content type",
                extra={
                    "content_type": request.content_type,
                    "expected": "application/x-www-form-urlencoded",
                },
            )
            raise InvalidDataError("Invalid content type")

        try:
            data = request.form.to_dict()
            logger.info(
                "Parsing Chargify webhook data",
                extra={
                    "content_type": request.content_type,
                    "form_data": data,
                    "headers": dict(request.headers),
                },
            )

            if not data:
                logger.error("Empty webhook data")
                raise InvalidDataError("Empty webhook data")

            # Only event type is mandatory
            event_type = data.get("event")
            if not event_type:
                logger.error(
                    "Missing event type",
                    extra={"available_fields": list(data.keys())},
                )
                raise InvalidDataError("Missing event type")

            # Handle test webhooks
            if event_type == "test":
                return {
                    "id": f"evt_test_{data.get('id', '')}",
                    "type": "test",
                    "customer_id": "test",
                    "amount": 0.0,
                    "currency": "USD",
                    "status": "test",
                    "timestamp": datetime.utcnow().isoformat(),
                    "metadata": {
                        "source": "chargify",
                        "webhook_id": request.headers.get("X-Chargify-Webhook-Id"),
                        "is_test": True,
                    },
                    "customer_data": {
                        "company_name": "Test Company",
                        "team_size": 0,
                        "plan_name": "Test Plan",
                    },
                }

            # Extract customer ID from various possible locations
            customer_id = (
                data.get("payload[subscription][customer][id]")
                or data.get("payload[customer][id]")
                or data.get("id", "unknown")
            )

            # Extract amount if available (not all events have amounts)
            amount = 0.0
            amount_in_cents = data.get("payload[transaction][amount_in_cents]")
            if amount_in_cents:
                try:
                    amount = float(amount_in_cents) / 100
                    if amount < 0:
                        logger.warning(
                            "Negative amount received",
                            extra={"amount_in_cents": amount_in_cents},
                        )
                except ValueError:
                    logger.warning(
                        "Invalid amount format",
                        extra={"amount_in_cents": amount_in_cents},
                    )

            # Extract customer info (might not be available in all webhooks)
            subscription_id = data.get("payload[subscription][id]")
            customer_email = data.get(
                "payload[subscription][customer][email]"
            ) or data.get("payload[customer][email]")
            customer_name = (
                f"{data.get('payload[subscription][customer][first_name]', '')} "
                f"{data.get('payload[subscription][customer][last_name]', '')}"
            ).strip() or (
                f"{data.get('payload[customer][first_name]', '')} "
                f"{data.get('payload[customer][last_name]', '')}"
            ).strip()

            organization = data.get(
                "payload[subscription][customer][organization]"
            ) or data.get("payload[customer][organization]")
            plan_name = data.get("payload[subscription][product][name]") or data.get(
                "payload[product][name]"
            )

            # Get timestamp from various possible fields
            timestamp = (
                data.get("created_at")
                or data.get("timestamp")
                or data.get("occurred_at")
                or datetime.utcnow().isoformat()
            )

            # Determine status based on event type and data
            status = "success"
            if "failure" in event_type:
                status = "failed"
            elif event_type == "subscription_state_change":
                status = data.get("payload[subscription][state]", "unknown")

            # Build metadata
            metadata = {
                "source": "chargify",
                "subscription_id": subscription_id,
                "customer_email": customer_email,
                "customer_name": customer_name,
                "webhook_id": request.headers.get("X-Chargify-Webhook-Id"),
            }

            # Add failure reason if available
            if status == "failed":
                failure_reason = (
                    data.get("payload[transaction][failure_message]")
                    or data.get("payload[transaction][memo]")
                    or "Unknown error"
                )
                metadata["failure_reason"] = failure_reason

            # Add subscription state change metadata
            if event_type == "subscription_state_change":
                metadata["cancel_at_period_end"] = (
                    data.get("payload[subscription][cancel_at_end_of_period]") == "true"
                )

            return {
                "id": f"evt_{customer_id}_{data.get('id', '')}",
                "type": event_type,
                "customer_id": str(customer_id),
                "amount": amount,
                "currency": "USD",  # Chargify always uses USD
                "status": status,
                "timestamp": timestamp,
                "metadata": metadata,
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
