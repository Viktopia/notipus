"""Stripe source plugin implementation.

This module implements the BaseSourcePlugin interface for Stripe,
handling webhook validation, parsing, and customer data retrieval
using the official Stripe SDK.
"""

import logging
from typing import Any, ClassVar

import stripe
from django.conf import settings
from django.http import HttpRequest
from plugins.base import PluginCapability, PluginMetadata, PluginType
from plugins.sources.base import BaseSourcePlugin, InvalidDataError

logger = logging.getLogger(__name__)


class StripeSourcePlugin(BaseSourcePlugin):
    """Handle Stripe webhooks using official Stripe SDK.

    This plugin validates webhook signatures using Stripe's built-in
    verification and parses various subscription and payment events.

    Attributes:
        PROVIDER_NAME: Provider identifier used in event data.
        EVENT_TYPE_MAPPING: Maps Stripe event types to internal types.
    """

    PROVIDER_NAME: ClassVar[str] = "stripe"

    EVENT_TYPE_MAPPING: ClassVar[dict[str, str]] = {
        "customer.subscription.created": "subscription_created",
        "customer.subscription.updated": "subscription_updated",
        "customer.subscription.deleted": "subscription_deleted",
        "customer.subscription.trial_will_end": "trial_ending",
        "invoice.payment_succeeded": "payment_success",
        "invoice.payment_failed": "payment_failure",
        "invoice.paid": "invoice_paid",
        "invoice.payment_action_required": "payment_action_required",
        "checkout.session.completed": "checkout_completed",
        "test": "test",
    }

    @classmethod
    def get_metadata(cls) -> PluginMetadata:
        """Return plugin metadata.

        Returns:
            PluginMetadata describing the Stripe source plugin.
        """
        return PluginMetadata(
            name="stripe",
            display_name="Stripe",
            version="1.0.0",
            description="Stripe webhook handler for payments and subscriptions",
            plugin_type=PluginType.SOURCE,
            capabilities={
                PluginCapability.WEBHOOK_VALIDATION,
                PluginCapability.CUSTOMER_DATA,
                PluginCapability.PAYMENT_HISTORY,
            },
            priority=100,
        )

    def __init__(self, webhook_secret: str = "") -> None:
        """Initialize Stripe plugin with webhook secret.

        Args:
            webhook_secret: Stripe webhook signing secret.
        """
        super().__init__(webhook_secret)
        # Configure Stripe API key and version
        stripe.api_key = settings.STRIPE_SECRET_KEY
        stripe.api_version = settings.STRIPE_API_VERSION

    def validate_webhook(self, request: HttpRequest) -> bool:
        """Validate webhook signature using Stripe SDK.

        Args:
            request: The incoming HTTP request.

        Returns:
            True if signature is valid, False otherwise.
        """
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
            logger.error(f"Stripe webhook signature verification failed: {e!s}")
            return False
        except Exception as e:
            logger.error(f"Stripe webhook validation error: {e!s}")
            return False

    def _extract_stripe_event_info(
        self, event: Any
    ) -> tuple[str, Any] | tuple[None, None]:
        """Extract event type and data from Stripe event object.

        Args:
            event: Stripe event object.

        Returns:
            Tuple of (event_type, event_data), or (None, None) for unsupported
            event types that should be acknowledged but not processed.

        Raises:
            InvalidDataError: If event type is missing or data is missing.
        """
        body_event_type = event.type
        if not body_event_type:
            raise InvalidDataError("Missing event type")

        event_type = self.EVENT_TYPE_MAPPING.get(body_event_type)
        if not event_type:
            # Unsupported event types are acknowledged but not processed.
            # Stripe sends many event types; we only handle a subset.
            logger.info(f"Ignoring unsupported Stripe event type: {body_event_type}")
            return None, None

        data = event.data.object
        if not data:
            raise InvalidDataError("Missing data parameter")

        # Capture previous_attributes for detecting changes (upgrades/downgrades)
        # Stripe provides this for update events to show what changed
        previous_attributes = getattr(event.data, "previous_attributes", None)
        if previous_attributes:
            # Convert to dict if it's a Stripe object
            if hasattr(previous_attributes, "to_dict"):
                data["_previous_attributes"] = previous_attributes.to_dict()
            else:
                data["_previous_attributes"] = dict(previous_attributes)

        return event_type, data

    def _handle_stripe_billing(self, event_type: str, data: dict[str, Any]) -> float:
        """Handle billing service calls and return amount in dollars.

        Stripe amounts are in cents, so we divide by 100 to get dollars.

        Args:
            event_type: The normalized event type.
            data: Event data dictionary.

        Returns:
            Amount in dollars as a float.
        """
        from webhooks.services.billing import BillingService

        amount_cents: int = 0

        if event_type == "subscription_created":
            amount_cents = data.get("plan", {}).get("amount", 0)
            BillingService.handle_subscription_created(data)
        elif event_type == "subscription_updated":
            # Get current plan amount
            current_amount = data.get("plan", {}).get("amount", 0)
            amount_cents = current_amount

            # Detect upgrade/downgrade by comparing with previous plan amount
            prev_attrs = data.get("_previous_attributes", {})
            prev_plan = prev_attrs.get("plan", {})
            prev_amount = prev_plan.get("amount") if prev_plan else None

            # Also check items for multi-item subscriptions
            if prev_amount is None and "items" in prev_attrs:
                prev_items = prev_attrs.get("items", {})
                if isinstance(prev_items, dict) and "data" in prev_items:
                    items_data = prev_items.get("data", [])
                    if items_data and len(items_data) > 0:
                        prev_amount = items_data[0].get("plan", {}).get("amount")

            # Determine change direction
            if prev_amount is not None:
                if current_amount > prev_amount:
                    data["_change_direction"] = "upgrade"
                elif current_amount < prev_amount:
                    data["_change_direction"] = "downgrade"
                else:
                    data["_change_direction"] = "other"

            BillingService.handle_subscription_updated(data)
        elif event_type == "subscription_deleted":
            amount_cents = 0
            BillingService.handle_subscription_deleted(data)
        elif event_type == "payment_success":
            # Use amount_paid, not amount_due (amount_due is 0 after payment succeeds)
            amount_cents = data.get("amount_paid", 0)

            # Detect trial conversion: first real payment after trial.
            # billing_reason "subscription_cycle" indicates recurring payment.
            # If subscription was trialing and this is first real payment,
            # it's a conversion.
            billing_reason = data.get("billing_reason", "")
            if billing_reason == "subscription_cycle" and amount_cents > 0:
                # This is the first payment after trial period ended
                data["_is_trial_conversion"] = True

            BillingService.handle_payment_success(data)
        elif event_type == "payment_failure":
            amount_cents = data.get("amount_due", 0)
            BillingService.handle_payment_failed(data)
        elif event_type == "checkout_completed":
            amount_cents = data.get("amount_total", 0)
            BillingService.handle_checkout_completed(data)
        elif event_type == "trial_ending":
            amount_cents = 0
            BillingService.handle_trial_ending(data)
        elif event_type == "invoice_paid":
            amount_cents = data.get("amount_paid", 0)
            BillingService.handle_invoice_paid(data)
        elif event_type == "payment_action_required":
            amount_cents = data.get("amount_due", 0)
            BillingService.handle_payment_action_required(data)

        # Convert cents to dollars
        return float(amount_cents) / 100.0

    def _build_stripe_event_data(
        self,
        event_type: str,
        customer_id: str,
        data: dict[str, Any],
        amount: float,
    ) -> dict[str, Any]:
        """Build Stripe event data structure.

        Args:
            event_type: The normalized event type.
            customer_id: Customer identifier.
            data: Raw event data.
            amount: Payment amount in dollars.

        Returns:
            Standardized event data dictionary.
        """
        event_data: dict[str, Any] = {
            "type": event_type,
            "customer_id": customer_id,
            "provider": self.PROVIDER_NAME,
            "external_id": data.get("id", ""),
            "status": data.get("status"),
            "created_at": data.get("created"),
            "currency": str(data.get("currency", "USD")).upper(),
            "amount": amount,
            "metadata": {},
        }

        # Add trial conversion flag if detected
        if data.get("_is_trial_conversion"):
            event_data["metadata"]["is_trial_conversion"] = True

        # Add change direction for subscription updates (upgrade/downgrade)
        if data.get("_change_direction"):
            event_data["metadata"]["change_direction"] = data["_change_direction"]

        return event_data

    def parse_webhook(
        self, request: HttpRequest, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Parse webhook data using Stripe SDK.

        Args:
            request: The incoming HTTP request.
            **kwargs: Additional arguments (unused).

        Returns:
            Parsed event data dictionary.

        Raises:
            InvalidDataError: If webhook data is invalid or missing fields.
        """
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
            raise InvalidDataError(f"Invalid webhook signature: {e!s}") from e
        except Exception as e:
            raise InvalidDataError(f"Webhook parsing error: {e!s}") from e

        # Extract event info using Stripe event object
        event_type, data = self._extract_stripe_event_info(event)

        # Return None for unsupported event types (acknowledged but not processed)
        if event_type is None:
            return None

        try:
            # Convert Stripe object to dict for easier processing
            if hasattr(data, "to_dict"):
                data_dict = data.to_dict()
            else:
                data_dict = dict(data)

            # Get customer ID - some events may not require one
            # (checkout sessions use metadata for organization lookup)
            customer_id = str(data_dict.get("customer", "") or "")

            # For checkout_completed and trial_ending, customer ID is optional
            # These events use metadata for organization lookup
            events_without_required_customer = {
                "checkout_completed",
                "trial_ending",
                "payment_action_required",
            }
            if not customer_id and event_type not in events_without_required_customer:
                raise InvalidDataError("Missing customer ID")

            # Handle billing and get amount
            amount = self._handle_stripe_billing(event_type, data_dict)

            # Build and return event data
            return self._build_stripe_event_data(
                event_type, customer_id, data_dict, amount
            )

        except (KeyError, ValueError, AttributeError) as e:
            raise InvalidDataError("Missing required fields") from e

    def get_customer_data(self, customer_id: str) -> dict[str, Any]:
        """Get customer data from Stripe API.

        Fetches customer details including email, name, and company info
        from the Stripe Customer object.

        Args:
            customer_id: The Stripe customer identifier (e.g., "cus_xxx").

        Returns:
            Dictionary with customer data including:
            - company_name: From metadata or empty string
            - email: Customer email
            - first_name: First part of name
            - last_name: Last part of name
        """
        if not customer_id:
            logger.warning("Empty customer_id provided to get_customer_data")
            return self._empty_customer_data()

        try:
            customer = stripe.Customer.retrieve(customer_id)

            # Handle deleted customers
            if getattr(customer, "deleted", False):
                logger.info(f"Customer {customer_id} has been deleted")
                return self._empty_customer_data()

            # Extract email
            email = customer.get("email", "") or ""

            # Extract name and split into first/last
            name = customer.get("name", "") or ""
            first_name, last_name = self._split_name(name)

            # Extract company name from metadata or use empty string
            metadata = customer.get("metadata", {}) or {}
            company_name = (
                metadata.get("company")
                or metadata.get("company_name")
                or metadata.get("organization")
                or ""
            )

            return {
                "company_name": company_name,
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
            }

        except stripe.error.InvalidRequestError as e:
            logger.warning(f"Invalid customer ID {customer_id}: {e}")
            return self._empty_customer_data()
        except stripe.error.StripeError as e:
            logger.error(f"Stripe API error fetching customer {customer_id}: {e}")
            return self._empty_customer_data()
        except Exception as e:
            logger.error(f"Unexpected error fetching customer {customer_id}: {e}")
            return self._empty_customer_data()

    def _empty_customer_data(self) -> dict[str, Any]:
        """Return empty customer data structure.

        Returns:
            Dictionary with empty customer fields.
        """
        return {
            "company_name": "",
            "email": "",
            "first_name": "",
            "last_name": "",
        }

    def _split_name(self, full_name: str) -> tuple[str, str]:
        """Split a full name into first and last name.

        Args:
            full_name: The full name string.

        Returns:
            Tuple of (first_name, last_name).
        """
        if not full_name:
            return "", ""

        parts = full_name.strip().split(None, 1)
        if len(parts) == 1:
            return parts[0], ""
        return parts[0], parts[1]
