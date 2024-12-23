from typing import Dict, Any, Optional
from flask import Request
import hmac
import hashlib
import logging
from collections import OrderedDict
import time

from .base import PaymentProvider, InvalidDataError

logger = logging.getLogger(__name__)


class ChargifyProvider(PaymentProvider):
    """Chargify payment provider implementation"""

    # Class-level cache for recently processed webhook IDs
    _webhook_cache = OrderedDict()
    _CACHE_MAX_SIZE = 1000
    _DEDUP_WINDOW_SECONDS = 60  # Only deduplicate within 60 seconds

    def __init__(self, webhook_secret: str):
        """Initialize provider with webhook secret"""
        super().__init__(webhook_secret)

    def _check_webhook_duplicate(self, customer_id: str) -> bool:
        """Check if a webhook for this customer has been processed recently"""
        now = time.time()

        # Clean up old entries
        cutoff = now - self._DEDUP_WINDOW_SECONDS
        self._webhook_cache = OrderedDict(
            (k, v) for k, v in self._webhook_cache.items()
            if v > cutoff
        )

        # Check if customer has recent webhook
        if customer_id in self._webhook_cache:
            return True

        # Add to cache
        self._webhook_cache[customer_id] = now
        if len(self._webhook_cache) > self._CACHE_MAX_SIZE:
            self._webhook_cache.popitem(last=False)  # Remove oldest

        return False

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

            logger.debug(
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
            logger.debug(
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

            event_type = data.get("event")
            if not event_type:
                logger.error("Missing required fields")
                raise InvalidDataError("Missing required fields")

            customer_id = data.get("payload[subscription][customer][id]")
            if not customer_id:
                logger.error("Missing required fields")
                raise InvalidDataError("Missing required fields")

            # Check for duplicate webhook for this customer
            if self._check_webhook_duplicate(customer_id):
                logger.warning(
                    "Duplicate webhook for customer",
                    extra={
                        "customer_id": customer_id,
                        "event_type": event_type,
                    },
                )
                raise InvalidDataError("Duplicate webhook for customer")

            status = "success"

            if "failure" in event_type:
                status = "failed"
            elif event_type == "subscription_state_change":
                status = data.get("payload[subscription][state]", "unknown")

            # Build metadata
            metadata = {
                "source": "chargify",
                "subscription_id": data.get("payload[subscription][id]"),
                "customer_email": data.get("payload[subscription][customer][email]", ""),
                "customer_name": (
                    f"{data.get('payload[subscription][customer][first_name]', '')} "
                    f"{data.get('payload[subscription][customer][last_name]', '')}"
                ).strip(),
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
                "amount": float(data.get("payload[transaction][amount_in_cents]", 0)) / 100,
                "currency": "USD",
                "status": status,
                "timestamp": data.get("created_at"),
                "metadata": metadata,
                "customer_data": {
                    "company_name": data.get(
                        "payload[subscription][customer][organization]", "Unknown"
                    ),
                    "team_size": 0,
                    "plan_name": data.get(
                        "payload[subscription][product][name]", "Unknown"
                    ),
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
