import logging
from typing import Any, Dict, Optional

import stripe
from django.conf import settings
from django.http import HttpRequest

from .base import InvalidDataError, PaymentProvider

logger = logging.getLogger(__name__)


class StripeProvider(PaymentProvider):
    """Handle Stripe webhooks using official Stripe SDK"""

    EVENT_TYPE_MAPPING = {
        "customer.subscription.created": "subscription_created",
        "invoice.payment_succeeded": "payment_success",
        "invoice.payment_failed": "payment_failure",
        "test": "test",
    }

    def __init__(self, webhook_secret: str):
        super().__init__(webhook_secret)
        # Configure Stripe API key
        stripe.api_key = settings.STRIPE_SECRET_KEY

    def validate_webhook(self, request: HttpRequest) -> bool:
        """Validate webhook signature using Stripe SDK"""
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

        if not signature:
            return False

        try:
            # Use Stripe's built-in webhook validation
            stripe.Webhook.construct_event(payload, signature, self.webhook_secret)
            return True
        except stripe.error.SignatureVerificationError as e:
            logger.error(f"Stripe webhook signature verification failed: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Stripe webhook validation error: {str(e)}")
            return False

    def _extract_stripe_event_info(self, event: Any) -> tuple:
        """Extract event type and data from Stripe event object"""
        body_event_type = event.type
        if not body_event_type:
            raise InvalidDataError("Missing event type")

        event_type = self.EVENT_TYPE_MAPPING.get(body_event_type)
        if not event_type:
            raise InvalidDataError(f"Unsupported webhook type: {body_event_type}")

        data = event.data.object
        if not data:
            raise InvalidDataError("Missing data parameter")

        return event_type, data

    def _handle_stripe_billing(self, event_type: str, data: Dict[str, Any]) -> str:
        """Handle billing service calls and return amount"""
        from ..services.billing import BillingService

        if event_type == "subscription_created":
            amount = str(data.get("plan", {}).get("amount", 0))
            BillingService.handle_subscription_created(data)
        elif event_type == "payment_success":
            amount = str(data.get("amount_due", 0))
            BillingService.handle_payment_success(data)
        elif event_type == "payment_failure":
            amount = str(data.get("amount_due", 0))
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
            "currency": str(data.get("currency", "USD")).upper(),
            "amount": float(amount),
        }

    def parse_webhook(self, request: HttpRequest) -> Optional[Dict[str, Any]]:
        """Parse webhook data using Stripe SDK"""
        logger.info(
            "Parsing Stripe webhook data",
            extra={
                "content_type": request.content_type,
                "form_data": (request.POST.dict() if request.POST else None),
                "headers": dict(request.headers),
            },
        )

        signature = request.headers.get("Stripe-Signature")
        payload = request.body

        if not signature:
            raise InvalidDataError("Missing Stripe signature")

        try:
            # Use Stripe SDK to construct and validate the event
            event = stripe.Webhook.construct_event(
                payload, signature, self.webhook_secret
            )
        except stripe.error.SignatureVerificationError as e:
            raise InvalidDataError(f"Invalid webhook signature: {str(e)}") from e
        except Exception as e:
            raise InvalidDataError(f"Webhook parsing error: {str(e)}") from e

        # Extract event info using Stripe event object
        event_type, data = self._extract_stripe_event_info(event)

        try:
            # Convert Stripe object to dict for easier processing
            if hasattr(data, "to_dict"):
                data_dict = data.to_dict()
            else:
                data_dict = dict(data)

            customer_id = str(data_dict.get("customer", ""))
            if not customer_id:
                raise InvalidDataError("Missing customer ID")

            # Handle billing and get amount
            amount = self._handle_stripe_billing(event_type, data_dict)

            # Build and return event data
            return self._build_stripe_event_data(
                event_type, customer_id, data_dict, amount
            )

        except (KeyError, ValueError, AttributeError) as e:
            raise InvalidDataError("Missing required fields") from e

    def get_customer_data(self, customer_id: str) -> Dict[str, Any]:
        """Get customer data"""
        return {
            "company_name": "<COMPANY_NAME>",
            "email": "<EMAIL>",
            "first_name": "<FIRST_NAME>",
            "last_name": "<LAST_NAME>",
        }
