# providers/chargify.py
import hashlib
import hmac
import logging
import re
import time
from collections import OrderedDict
from datetime import datetime, timezone
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
    _TIMESTAMP_TOLERANCE_SECONDS = 300  # 5 minutes tolerance for webhook timestamps

    def __init__(self, webhook_secret: str):
        """Initialize provider with webhook secret"""
        super().__init__(webhook_secret)
        self._current_webhook_data = None

    def _check_webhook_duplicate(self, webhook_id: str) -> bool:
        """Check if a webhook ID has been processed recently (proper idempotency)"""
        if not webhook_id:
            logger.warning("No webhook ID provided for deduplication check")
            return False

        now = time.time()

        # Clean up old entries
        cutoff = now - self._DEDUP_WINDOW_SECONDS
        self._webhook_cache = OrderedDict(
            (k, v) for k, v in self._webhook_cache.items() if v > cutoff
        )

        # Check if webhook ID has been processed
        if webhook_id in self._webhook_cache:
            logger.info(f"Duplicate webhook detected: {webhook_id}")
            return True

        # Add to cache
        self._webhook_cache[webhook_id] = now
        if len(self._webhook_cache) > self._CACHE_MAX_SIZE:
            self._webhook_cache.popitem(last=False)  # Remove oldest

        return False

    def _validate_webhook_timestamp(self, request: HttpRequest) -> bool:
        """Validate webhook timestamp to prevent replay attacks"""
        timestamp_header = request.headers.get("X-Chargify-Webhook-Timestamp")
        if not timestamp_header:
            # Timestamp is optional, so continue if not present
            return True

        try:
            webhook_time = datetime.fromisoformat(timestamp_header.replace("Z", "+00:00"))
            current_time = datetime.now(timezone.utc)
            age_seconds = abs((current_time - webhook_time).total_seconds())

            if age_seconds > self._TIMESTAMP_TOLERANCE_SECONDS:
                logger.warning(
                    "Webhook timestamp outside tolerance window",
                    extra={
                        "webhook_timestamp": timestamp_header,
                        "age_seconds": age_seconds,
                        "tolerance": self._TIMESTAMP_TOLERANCE_SECONDS,
                    }
                )
                return False

            return True
        except (ValueError, TypeError) as e:
            logger.warning(
                "Invalid webhook timestamp format",
                extra={"timestamp": timestamp_header, "error": str(e)}
            )
            return False

    def validate_webhook(self, request: HttpRequest) -> bool:
        """Validate webhook signature and timestamp"""
        try:
            # If no webhook secret is configured, skip validation
            if not self.webhook_secret:
                logger.info("No webhook secret configured, skipping validation")
                return True

            # Validate timestamp first
            if not self._validate_webhook_timestamp(request):
                logger.warning("Webhook timestamp validation failed")
                return False

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
            raise CustomerNotFoundError(
                f"Failed to extract customer data: {str(e)}"
            ) from e

    def _extract_chargify_fields(self, data: Dict[str, Any]) -> tuple:
        """Extract subscription, customer, and transaction data from webhook"""
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
                if "customer" not in key:  # Skip customer fields handled above
                    field = key.replace("payload[subscription][", "").replace("]", "")
                    subscription[field] = value
            elif key.startswith("payload[transaction]["):
                field = key.replace("payload[transaction][", "").replace("]", "")
                transaction[field] = value

        return subscription, customer, transaction

    def _determine_chargify_status(
        self, event_type: str, subscription: Dict[str, Any]
    ) -> str:
        """Determine status based on event type and subscription state"""
        if event_type == "payment_failure":
            return "failed"
        elif event_type == "payment_success":
            return "success"
        elif event_type == "subscription_state_change":
            return subscription.get("state", "unknown")
        else:
            return subscription.get("state", "unknown")

    def _extract_chargify_amount(
        self, transaction: Dict[str, Any], subscription: Dict[str, Any]
    ) -> float:
        """Extract amount from transaction or subscription data"""
        if transaction.get("amount_in_cents"):
            return float(transaction["amount_in_cents"]) / 100
        elif subscription.get("total_revenue_in_cents"):
            return float(subscription["total_revenue_in_cents"]) / 100
        else:
            return 0

    def _build_chargify_customer_data(
        self, customer: Dict[str, Any], subscription: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build customer data structure"""
        return {
            "id": customer.get("id"),
            "email": customer.get("email"),
            "first_name": customer.get("first_name"),
            "last_name": customer.get("last_name"),
            "company_name": customer.get("organization"),
            "subscription_status": subscription.get("state"),
            "plan_name": subscription.get("product", {}).get("name"),
        }

    def _build_chargify_response(
        self,
        event_type: str,
        customer_id: str,
        amount: float,
        status: str,
        data: Dict[str, Any],
        subscription: Dict[str, Any],
        customer_data: Dict[str, Any],
        failure_reason: str,
    ) -> Dict[str, Any]:
        """Build final response structure"""
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
                "cancel_at_period_end": (
                    subscription.get("cancel_at_end_of_period") == "true"
                ),
                "failure_reason": failure_reason,
            },
            "customer_data": customer_data,
        }

    def _parse_webhook_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse webhook data into standardized format"""
        event_type = data.get("event")
        if not event_type:
            raise InvalidDataError("Missing event type")

        # Extract fields from nested form data
        subscription, customer, transaction = self._extract_chargify_fields(data)

        # Determine status
        status = self._determine_chargify_status(event_type, subscription)

        # Extract amount
        amount = self._extract_chargify_amount(transaction, subscription)

        # Extract failure reason if present
        failure_reason = None
        if event_type == "payment_failure":
            failure_reason = transaction.get("failure_message")

        # Build customer data
        customer_data = self._build_chargify_customer_data(customer, subscription)

        # Extract customer ID
        customer_id = customer.get("id")
        if not customer_id:
            raise InvalidDataError("Missing customer ID")

        # Store webhook data for customer lookup
        self._current_webhook_data = data

        # Build and return response
        return self._build_chargify_response(
            event_type,
            customer_id,
            amount,
            status,
            data,
            subscription,
            customer_data,
            failure_reason,
        )

    def _validate_chargify_request(self, request: HttpRequest) -> Dict[str, Any]:
        """Validate Chargify webhook request and return form data"""
        if request.content_type != "application/x-www-form-urlencoded":
            raise InvalidDataError("Invalid content type")

        data = request.POST.dict()
        if not data:
            raise InvalidDataError("Missing required fields")

        return data

    def _get_chargify_event_info(self, data: Dict[str, Any]) -> tuple:
        """Extract event type and customer ID from webhook data"""
        event_type = data.get("event")
        if not event_type:
            raise InvalidDataError("Missing event type")

        customer_id = data.get("payload[subscription][customer][id]")
        if not customer_id:
            raise InvalidDataError("Missing customer ID")

        return event_type, customer_id

    def _handle_chargify_event(
        self, event_type: str, customer_id: str, data: Dict[str, Any], webhook_id: str
    ) -> Dict[str, Any]:
        """Route webhook event to appropriate handler with proper deduplication"""
        # Check for duplicates using webhook ID (proper idempotency)
        if self._check_webhook_duplicate(webhook_id):
            raise InvalidDataError(f"Duplicate webhook: {webhook_id}")

        if event_type == "payment_success":
            return self._parse_payment_success(data)
        elif event_type == "payment_failure":
            return self._parse_payment_failure(data)
        elif event_type == "subscription_state_change":
            return self._parse_subscription_state_change(data)
        elif event_type == "renewal_success":
            # Renewal success is treated as payment success
            return self._parse_payment_success(data)
        else:
            raise InvalidDataError(f"Unsupported event type: {event_type}")

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

        # Validate request and get data
        data = self._validate_chargify_request(request)

        # Store webhook data for customer lookup
        self._current_webhook_data = data

        # Get event info
        event_type, customer_id = self._get_chargify_event_info(data)

        # Handle the event
        return self._handle_chargify_event(event_type, customer_id, data, request.headers.get("X-Chargify-Webhook-Id"))

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

        # Validate amount is a valid number
        try:
            amount_float = float(amount) / 100
        except (ValueError, TypeError) as e:
            raise InvalidDataError(f"Invalid amount format: {amount}") from e

        customer_data = self.get_customer_data(data)

        # Extract Shopify order reference from memo
        memo = data.get("payload[transaction][memo]", "")
        shopify_order_ref = self._parse_shopify_order_ref(memo)

        # Safely get subscription data
        subscription_id = data.get("payload[subscription][id]", "")
        plan_name = data.get("payload[subscription][product][name]", "")

        return {
            "type": "payment_success",
            "customer_id": data["payload[subscription][customer][id]"],
            "amount": amount_float,
            "currency": "USD",  # Chargify amounts are in USD
            "status": "success",
            "metadata": {
                "subscription_id": subscription_id,
                "transaction_id": data.get("payload[transaction][id]", ""),
                "plan_name": plan_name,
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
