import hmac
import hashlib
import logging
import json
from typing import Any, Dict, Optional
from django.http import HttpRequest
from django.conf import settings

from .base import PaymentProvider, InvalidDataError

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
        if request.content_type != "application/json":
            raise InvalidDataError("Invalid content type")

        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, AttributeError):
            raise InvalidDataError("Invalid JSON data")

        if not isinstance(body, dict):
            raise InvalidDataError("Invalid JSON data")
        if not body:
            raise InvalidDataError("Missing required fields")

        body_event_type = body.get("type")
        if not body_event_type:
            raise InvalidDataError("Missing event type")

        event_type = self.EVENT_TYPE_MAPPING.get(body_event_type)
        if not event_type:
            raise InvalidDataError(f"Unsupported webhook type: {body_event_type}")

        data = body["data"]["object"]
        if not data:
            raise InvalidDataError("Missing data parameter")

        try:
            from ..services.billing import BillingService

            customer_id = str(data["customer"])
            if not customer_id:
                raise InvalidDataError("Missing required fields")

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

            event_data = {
                "type": event_type,
                "customer_id": customer_id,
                "status": data.get("status"),
                "created_at": data.get("created"),
                "currency": str(data["currency"]).upper(),
                "amount": float(amount),
            }

            return event_data

        except (KeyError, ValueError):
            raise InvalidDataError("Missing required fields")


    def get_customer_data(self, customer_id: str) -> Dict[str, Any]:
        """Get customer data"""
        return {
            "company_name": "<COMPANY_NAME>",
            "email": "<EMAIL>",
            "first_name": "<FIRST_NAME>",
            "last_name": "<LAST_NAME>",
        }

    def _handle_subscription_created(self, subscription: dict):
        Organization.objects.filter(stripe_customer_id=subscription["customer"]).update(
            subscription_plan=subscription["items"]["data"][0]["plan"]["id"],
            subscription_status="active",
            billing_cycle_anchor=subscription["current_period_start"],
        )

    def _handle_invoice_paid(self, invoice: dict):
        Organization.objects.filter(stripe_customer_id=invoice["customer"]).update(
            subscription_status="active", billing_cycle_anchor=invoice["period_end"]
        )

    def _handle_payment_failed(self, invoice: dict):
        Organization.objects.filter(stripe_customer_id=invoice["customer"]).update(
            subscription_status="past_due"
        )
