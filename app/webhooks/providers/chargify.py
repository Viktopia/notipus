# providers/chargify.py
import hashlib
import hmac
import logging
import re
import time
from collections import OrderedDict
from datetime import datetime
from typing import Any, Dict

from django.http import HttpRequest

from .base import CustomerNotFoundError, InvalidDataError, PaymentProvider

logger = logging.getLogger(__name__)


class ChargifyProvider(PaymentProvider):
    """Chargify payment provider implementation"""

    EVENT_TYPE_MAPPING = {
        "payment_success": "payment_success",
        "payment_failure": "payment_failure",
        "subscription_state_change": "subscription_state_change",
        "subscription_product_change": "subscription_product_change",
        "subscription_billing_date_change": "subscription_billing_date_change",
        "renewal_success": "payment_success",
        "renewal_failure": "payment_failure",
    }

    # Class-level cache for recently processed webhook IDs
    _webhook_cache = OrderedDict()
    _CACHE_MAX_SIZE = 1000
    _DEDUP_WINDOW_SECONDS = 300  # 5 minutes

    def __init__(self, webhook_secret: str):
        """Initialize provider with webhook secret"""
        super().__init__(webhook_secret)
        self._current_webhook_data = None
        self._recent_webhooks = {}

    def _check_webhook_duplicate(self, customer_id: str) -> bool:
        """Check if a webhook for this customer has been processed recently"""
        now = time.time()

        # Clean up old entries
        cutoff = now - self._DEDUP_WINDOW_SECONDS
        self._webhook_cache = OrderedDict(
            (k, v) for k, v in self._webhook_cache.items() if v > cutoff
        )

        # Check if customer has recent webhook
        if customer_id in self._webhook_cache:
            return True

        # Add to cache
        self._webhook_cache[customer_id] = now
        if len(self._webhook_cache) > self._CACHE_MAX_SIZE:
            self._webhook_cache.popitem(last=False)  # Remove oldest

        return False

    def validate_webhook(self, request: HttpRequest) -> bool:
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

            body = request.body
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

    def get_customer_data(self, customer_id: str) -> Dict[str, Any]:
        """Get customer data from stored webhook data"""
        if not self._current_webhook_data:
            raise CustomerNotFoundError("No webhook data available")

        try:
            # Extract customer data from form fields
            return {
                "company_name": self._current_webhook_data.get(
                    "payload[subscription][customer][organization]", ""
                ),
                "email": self._current_webhook_data.get(
                    "payload[subscription][customer][email]", ""
                ),
                "first_name": self._current_webhook_data.get(
                    "payload[subscription][customer][first_name]", ""
                ),
                "last_name": self._current_webhook_data.get(
                    "payload[subscription][customer][last_name]", ""
                ),
                "created_at": self._current_webhook_data.get("created_at", ""),
                "plan_name": self._current_webhook_data.get(
                    "payload[subscription][product][name]", ""
                ),
                "team_size": self._current_webhook_data.get(
                    "payload[subscription][team_size]", ""
                ),
                "total_revenue": float(
                    self._current_webhook_data.get(
                        "payload[subscription][total_revenue_in_cents]", 0
                    )
                )
                / 100,
            }
        except (KeyError, ValueError) as e:
            raise CustomerNotFoundError(f"Failed to extract customer data: {str(e)}")

    def _parse_webhook_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse webhook data into standardized format"""
        event_type = data.get("event")
        if not event_type:
            raise InvalidDataError("Missing event type")

        # Extract subscription data
        subscription = {}
        customer = {}
        transaction = {}
        for key, value in data.items():
            if key.startswith("payload[subscription][customer]["):
                field = key.replace("payload[subscription][customer][", "").replace(
                    "]", ""
                )
                customer[field] = value
            elif key.startswith("payload[subscription]["):
                if (
                    "customer" not in key
                ):  # Skip customer fields as they're handled above
                    field = key.replace("payload[subscription][", "").replace("]", "")
                    subscription[field] = value
            elif key.startswith("payload[transaction]["):
                field = key.replace("payload[transaction][", "").replace("]", "")
                transaction[field] = value

        # Map status based on event type and subscription state
        status = subscription.get("state", "unknown")
        if event_type == "payment_failure":
            status = "failed"
        elif event_type == "payment_success":
            status = "success"
        elif event_type == "subscription_state_change":
            status = subscription.get("state", "unknown")

        # Extract amount from transaction or subscription
        amount = 0
        if transaction.get("amount_in_cents"):
            amount = float(transaction["amount_in_cents"]) / 100
        elif subscription.get("total_revenue_in_cents"):
            amount = float(subscription["total_revenue_in_cents"]) / 100

        # Extract failure reason if present
        failure_reason = None
        if event_type == "payment_failure":
            failure_reason = transaction.get("failure_message")

        # Build customer data
        customer_data = {
            "id": customer.get("id"),
            "email": customer.get("email"),
            "first_name": customer.get("first_name"),
            "last_name": customer.get("last_name"),
            "company_name": customer.get("organization"),
            "subscription_status": subscription.get("state"),
            "plan_name": subscription.get("product", {}).get("name"),
        }

        # Extract customer ID from the correct field
        customer_id = customer.get("id")
        if not customer_id:
            raise InvalidDataError("Missing customer ID")

        # Store webhook data for customer lookup
        self._current_webhook_data = data

        return {
            "type": self.EVENT_TYPE_MAPPING.get(event_type, event_type),
            "customer_id": str(customer_id),
            "amount": amount,
            "currency": "USD",  # Chargify amounts are always in USD
            "status": status,
            "timestamp": datetime.fromisoformat(
                data["created_at"].replace("Z", "+00:00")
            ),
            "metadata": {
                "subscription_id": subscription.get("id"),
                "plan": subscription.get("product", {}).get("name"),
                "cancel_at_period_end": subscription.get("cancel_at_end_of_period")
                == "true",
                "failure_reason": failure_reason,
            },
            "customer_data": customer_data,
        }

    def _check_duplicate(self, customer_id: str, event_type: str) -> bool:
        """Check if this is a duplicate webhook for the customer"""
        now = datetime.now()
        key = f"{customer_id}:{event_type}"

        # Check if we've seen this customer recently
        if key in self._recent_webhooks:
            last_seen = self._recent_webhooks[key]
            if (now - last_seen).total_seconds() < self._DEDUP_WINDOW_SECONDS:
                return True

        # Update last seen time
        self._recent_webhooks[key] = now
        return False

    def parse_webhook(self, request: HttpRequest) -> Dict[str, Any]:
        """Parse Chargify webhook data"""
        logger.info(
            "Parsing Chargify webhook data",
            extra={
                "content_type": request.content_type,
                "form_data": (request.POST.dict() if request.POST else None),
                "headers": dict(request.headers),
            },
        )

        # Validate content type
        if request.content_type != "application/x-www-form-urlencoded":
            raise InvalidDataError("Invalid content type")

        # Parse form data
        data = request.POST.dict()
        if not data:
            raise InvalidDataError("Missing required fields")

        # Store webhook data for customer lookup
        self._current_webhook_data = data

        # Get event type and customer ID
        event_type = data.get("event")
        if not event_type:
            raise InvalidDataError("Missing event type")

        customer_id = data.get("payload[subscription][customer][id]")
        if not customer_id:
            raise InvalidDataError("Missing customer ID")

        # Check for duplicates
        if self._check_duplicate(customer_id, event_type):
            raise InvalidDataError("Duplicate webhook for customer")

        # Map webhook data to common format
        if event_type == "payment_success":
            return self._parse_payment_success(data)
        elif event_type == "payment_failure":
            return self._parse_payment_failure(data)
        elif event_type == "subscription_state_change":
            return self._parse_subscription_state_change(data)
        elif event_type == "renewal_success":
            # Check for duplicates with payment_success
            if self._check_duplicate(customer_id, "payment_success"):
                raise InvalidDataError("Duplicate webhook for customer")
            return self._parse_payment_success(data)
        else:
            raise InvalidDataError(f"Unsupported event type: {event_type}")

    def _parse_shopify_order_ref(self, memo: str) -> str:
        """Extract Shopify order reference from transaction memo."""
        if not memo:
            return None

        # First look for explicit mentions of Shopify order with any format
        match = re.search(r"Shopify Order[^\d]*(\d+)", memo, re.IGNORECASE)
        if match:
            return match.group(1)

        # Then look for any order number mentioned in an amount allocation
        match = re.search(r"allocated to[^$]*?(\d+)", memo, re.IGNORECASE)
        if match:
            return match.group(1)

        # Finally look for any order number in the memo
        match = re.search(r"order[^\d]*(\d+)", memo, re.IGNORECASE)
        if match:
            return match.group(1)

        return None

    def _parse_payment_success(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse payment_success webhook data"""
        amount = data.get("payload[transaction][amount_in_cents]")
        if not amount:
            raise InvalidDataError("Missing amount")

        customer_data = self.get_customer_data(data)

        # Extract Shopify order reference from memo
        memo = data.get("payload[transaction][memo]", "")
        shopify_order_ref = self._parse_shopify_order_ref(memo)

        return {
            "type": "payment_success",
            "customer_id": data["payload[subscription][customer][id]"],
            "amount": float(amount) / 100,  # Convert cents to dollars
            "currency": "USD",  # Chargify amounts are in USD
            "status": "success",
            "metadata": {
                "subscription_id": data["payload[subscription][id]"],
                "transaction_id": data.get("payload[transaction][id]", ""),
                "plan_name": data["payload[subscription][product][name]"],
                "shopify_order_ref": shopify_order_ref,
                "memo": memo,  # Include full memo for reference
            },
            "customer_data": customer_data,
        }

    def _parse_payment_failure(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse payment_failure webhook data"""
        amount = data.get("payload[transaction][amount_in_cents]")
        if not amount:
            raise InvalidDataError("Missing amount")

        customer_data = self.get_customer_data(data)
        return {
            "type": "payment_failure",
            "customer_id": data["payload[subscription][customer][id]"],
            "amount": float(amount) / 100,  # Convert cents to dollars
            "currency": "USD",  # Chargify amounts are in USD
            "status": "failed",
            "metadata": {
                "subscription_id": data["payload[subscription][id]"],
                "transaction_id": data.get("payload[transaction][id]", ""),
                "plan_name": data["payload[subscription][product][name]"],
                "failure_reason": data.get(
                    "payload[transaction][failure_message]", "Unknown error"
                ),
            },
            "customer_data": customer_data,
        }

    def _parse_subscription_state_change(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse subscription_state_change webhook data"""
        customer_data = self.get_customer_data(data)
        return {
            "type": "subscription_state_change",
            "customer_id": data["payload[subscription][customer][id]"],
            "status": data["payload[subscription][state]"],
            "metadata": {
                "subscription_id": data["payload[subscription][id]"],
                "plan_name": data["payload[subscription][product][name]"],
                "previous_state": data.get("payload[subscription][previous_state]"),
                "cancel_at_period_end": data.get(
                    "payload[subscription][cancel_at_end_of_period]"
                )
                == "true",
            },
            "customer_data": customer_data,
        }

    def get_event_type(self, event_data: Dict[str, Any]) -> str:
        """Get event type from webhook data"""
        if not event_data or "type" not in event_data:
            raise InvalidDataError("Invalid event type")
        return event_data["type"]
