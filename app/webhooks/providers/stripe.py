import hashlib
import hmac
import json
import logging
from typing import Any, Dict, Optional

from django.conf import settings
from django.http import HttpRequest

from .base import InvalidDataError, PaymentProvider

logger = logging.getLogger(__name__)


class StripeProvider(PaymentProvider):
    """Handle Stripe webhooks"""

    EVENT_TYPE_MAPPING = {
        "customer.subscription.created": "subscription_created",
        "invoice.payment_succeeded": "payment_success",
        "invoice.payment_failed": "payment_failure",
        "test": "test",
    }

    def __init__(self, webhook_secret: str):
        super().__init__(webhook_secret)

    def validate_webhook(self, request: HttpRequest) -> bool:
        """Validate webhook signature"""
        if settings.DISABLE_BILLING:
            return False

        logger.info(
            "Validate Stripe webhook data",
            extra={
                "content_type": request.content_type,
                "form_data": (request.POST.dict() if request.POST else None),
                "headers": dict(request.headers),
            },
        )

        signature = request.headers.get("Stripe-Signature")
        payload = request.body
        secret = self.webhook_secret.encode()

        if not signature:
            return False

        try:
            elements = signature.split(",")
            timestamp = None
            signatures = []
            for element in elements:
                if element.startswith("t="):
                    timestamp = element.split("=")[1]
                elif element.startswith("v1="):
                    signatures.append(element)

            if not timestamp or not signatures:
                return False

            signed_payload = f"{timestamp}.{payload.decode()}"
            expected_sig = hmac.new(
                secret, signed_payload.encode(), hashlib.sha256
            ).hexdigest()

            return any(f"v1={expected_sig}" == sig for sig in signatures)

        except Exception as e:
            logger.error(f"Stripe webhook error: {str(e)}")
            return False

    def _validate_stripe_request(self, request: HttpRequest) -> Dict[str, Any]:
        """Validate Stripe webhook request and return parsed body"""
        if request.content_type != "application/json":
            raise InvalidDataError("Invalid content type")

        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, AttributeError) as e:
            raise InvalidDataError("Invalid JSON data") from e

        if not isinstance(body, dict):
            raise InvalidDataError("Invalid JSON data")
        if not body:
            raise InvalidDataError("Missing required fields")

        return body

    def _extract_stripe_event_info(self, body: Dict[str, Any]) -> tuple:
        """Extract event type and data from Stripe webhook body"""
        body_event_type = body.get("type")
        if not body_event_type:
            raise InvalidDataError("Missing event type")

        event_type = self.EVENT_TYPE_MAPPING.get(body_event_type)
        if not event_type:
            raise InvalidDataError(f"Unsupported webhook type: {body_event_type}")

        data = body["data"]["object"]
        if not data:
            raise InvalidDataError("Missing data parameter")

        return event_type, data

    def _handle_stripe_billing(self, event_type: str, data: Dict[str, Any]) -> str:
        """Handle billing service calls and return amount"""
        from ..services.billing import BillingService

        if event_type == "subscription_created":
            amount = str(data["plan"]["amount"])
            BillingService.handle_subscription_created(data)
        elif event_type == "payment_success":
            amount = str(data["amount_due"])
            BillingService.handle_payment_success(data)
        elif event_type == "payment_failure":
            amount = str(data["amount_due"])
            BillingService.handle_payment_failed(data)
        else:
            amount = "0"

        return amount

    def _build_stripe_event_data(
        self,
        event_type: str,
        customer_id: str,
        data: Dict[str, Any],
        amount: str,
    ) -> Dict[str, Any]:
        """Build Stripe event data structure"""
        return {
            "type": event_type,
            "customer_id": customer_id,
            "status": data.get("status"),
            "created_at": data.get("created"),
            "currency": str(data["currency"]).upper(),
            "amount": float(amount),
        }

    def parse_webhook(self, request: HttpRequest) -> Optional[Dict[str, Any]]:
        """Parse webhook data"""
        logger.info(
            "Parsing Stripe webhook data",
            extra={
                "content_type": request.content_type,
                "form_data": (request.POST.dict() if request.POST else None),
                "headers": dict(request.headers),
            },
        )

        # Validate request and get body
        body = self._validate_stripe_request(request)

        # Extract event info
        event_type, data = self._extract_stripe_event_info(body)

        try:
            customer_id = str(data["customer"])
            if not customer_id:
                raise InvalidDataError("Missing required fields")

            # Handle billing and get amount
            amount = self._handle_stripe_billing(event_type, data)

            # Build and return event data
            return self._build_stripe_event_data(event_type, customer_id, data, amount)

        except (KeyError, ValueError) as e:
            raise InvalidDataError("Missing required fields") from e

    def get_customer_data(self, customer_id: str) -> Dict[str, Any]:
        """Get customer data"""
        return {
            "company_name": "<COMPANY_NAME>",
            "email": "<EMAIL>",
            "first_name": "<FIRST_NAME>",
            "last_name": "<LAST_NAME>",
        }
