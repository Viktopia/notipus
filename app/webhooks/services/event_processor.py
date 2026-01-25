"""Event processor for webhook notifications.

This module handles processing events from various providers and
formatting them into RichNotification objects with company enrichment.
"""

import logging
from typing import Any, ClassVar

from core.models import Company
from core.services.enrichment import DomainEnrichmentService
from core.utils.email_domain import extract_domain, is_enrichable_domain
from plugins import PluginRegistry, PluginType
from plugins.destinations.base import BaseDestinationPlugin

from ..models.rich_notification import RichNotification
from .database_lookup import DatabaseLookupService
from .notification_builder import NotificationBuilder

logger = logging.getLogger(__name__)


class EventProcessor:
    """Process events from various providers and format notifications.

    This class handles the core event processing logic, including
    cross-reference lookups and notification formatting.

    Attributes:
        VALID_EVENT_TYPES: Set of recognized event type strings.
    """

    VALID_EVENT_TYPES: ClassVar[set[str]] = {
        # Payment events
        "payment_success",
        "payment_failure",
        "refund_issued",
        # Subscription events
        "subscription_created",
        "subscription_updated",
        "subscription_canceled",
        "subscription_deleted",
        "subscription_renewed",
        "trial_started",
        "trial_ending",
        "trial_converted",
        # Customer events
        "customer_created",
        "customer_updated",
        "customer_churned",
        # Usage events
        "feature_adopted",
        "usage_milestone",
        "quota_warning",
        "quota_exceeded",
        # Support events
        "feedback_received",
        "nps_response",
        "support_ticket",
        # System events
        "integration_connected",
        "integration_error",
        "webhook_received",
        # Logistics events
        "order_created",
        "order_fulfilled",
        "fulfillment_created",
        "fulfillment_updated",
        "shipment_delivered",
    }

    def __init__(self) -> None:
        """Initialize the event processor with services."""
        self.db_lookup = DatabaseLookupService()
        self.enrichment_service = DomainEnrichmentService()
        self.notification_builder = NotificationBuilder()

    def process_event_rich(
        self,
        event_data: dict[str, Any],
        customer_data: dict[str, Any],
        target: str = "slack",
    ) -> dict[str, Any]:
        """Process an event and return formatted output for target platform.

        This method uses the multi-target notification system with
        RichNotification and formatters.

        Args:
            event_data: Dictionary containing event type and metadata.
            customer_data: Dictionary containing customer information.
            target: Target platform identifier (default: "slack").

        Returns:
            Formatted notification dict for the target platform.

        Raises:
            ValueError: If event_data is missing or has invalid type.
            KeyError: If no formatter registered for target.
        """
        if not event_data or "type" not in event_data:
            raise ValueError("Missing event type")

        event_type = event_data["type"]
        if event_type not in self.VALID_EVENT_TYPES:
            raise ValueError(f"Invalid event type: {event_type}")

        # Enrich with cross-references
        enriched_event_data = self._enrich_with_cross_references(event_data)

        # Enrich company data
        company = self._enrich_company(customer_data)

        # Build target-agnostic notification
        notification = self.notification_builder.build(
            enriched_event_data, customer_data, company
        )

        # Format for target platform using destination plugin
        registry = PluginRegistry.instance()
        plugin = registry.get(PluginType.DESTINATION, target)
        if plugin is None or not isinstance(plugin, BaseDestinationPlugin):
            raise ValueError(f"No destination plugin found for target: {target}")
        return plugin.format(notification)

    def build_rich_notification(
        self,
        event_data: dict[str, Any],
        customer_data: dict[str, Any],
    ) -> RichNotification:
        """Build a RichNotification without formatting.

        Useful when you need the intermediate RichNotification object
        for custom processing or multiple target formatting.

        Args:
            event_data: Dictionary containing event type and metadata.
            customer_data: Dictionary containing customer information.

        Returns:
            RichNotification object.

        Raises:
            ValueError: If event_data is missing or has invalid type.
        """
        if not event_data or "type" not in event_data:
            raise ValueError("Missing event type")

        event_type = event_data["type"]
        if event_type not in self.VALID_EVENT_TYPES:
            raise ValueError(f"Invalid event type: {event_type}")

        # Enrich with cross-references
        enriched_event_data = self._enrich_with_cross_references(event_data)

        # Enrich company data
        company = self._enrich_company(customer_data)

        return self.notification_builder.build(
            enriched_event_data, customer_data, company
        )

    def _enrich_with_cross_references(
        self, event_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Enrich event data with cross-references and store in database.

        Args:
            event_data: Original event data dictionary.

        Returns:
            Enriched copy of event data with cross-reference information.
        """
        # Make a copy to avoid modifying the original
        enriched_data = event_data.copy()

        # Store the event data in database
        # All payment/subscription events should be stored for activity tracking
        payment_event_types = {
            "payment_success",
            "payment_failure",
            "subscription_created",
            "subscription_updated",
            "subscription_deleted",
            "checkout_completed",
            "invoice_paid",
            "trial_ending",
            "payment_action_required",
        }
        event_type = event_data.get("type")
        provider = event_data.get("provider", "").lower()

        if event_type in payment_event_types:
            self.db_lookup.store_payment_record(event_data)
        elif provider == "shopify":
            self.db_lookup.store_order_record(event_data)

        # Perform cross-reference lookups
        if "metadata" not in enriched_data:
            enriched_data["metadata"] = {}

        metadata = enriched_data["metadata"]
        provider = enriched_data.get("provider")

        # For Shopify events, look for matching Chargify payment
        if provider == "shopify" and metadata.get("order_ref"):
            order_ref = metadata["order_ref"]
            related_payment_ref = (
                self.db_lookup.lookup_chargify_payment_for_shopify_order(order_ref)
            )
            metadata["related_payment_ref"] = related_payment_ref

            if related_payment_ref:
                logger.info(
                    f"Found related Chargify payment {related_payment_ref} for "
                    f"Shopify order {order_ref}"
                )
            else:
                logger.debug(
                    f"No related Chargify payment found for Shopify order {order_ref}"
                )

        # For Chargify events, look for matching Shopify order
        elif provider == "chargify" and metadata.get("shopify_order_ref"):
            order_ref = metadata["shopify_order_ref"]
            related_order_ref = (
                self.db_lookup.lookup_shopify_order_for_chargify_payment(order_ref)
            )
            metadata["related_order_ref"] = related_order_ref

            if related_order_ref:
                logger.info(
                    f"Found related Shopify order {related_order_ref} for "
                    f"Chargify payment with order ref {order_ref}"
                )
            else:
                logger.debug(
                    f"No related Shopify order found for Chargify payment "
                    f"with order ref {order_ref}"
                )

        return enriched_data

    def _enrich_company(self, customer_data: dict[str, Any]) -> Company | None:
        """Enrich customer data with company branding information.

        Args:
            customer_data: Customer data dictionary with email.

        Returns:
            Company model with branding data, or None if not enrichable.
        """
        customer_email = customer_data.get("email")
        if not customer_email:
            return None

        # Check if domain is worth enriching (not free/disposable)
        if not is_enrichable_domain(customer_email):
            return None

        # Extract domain and enrich
        domain = extract_domain(customer_email)
        if not domain:
            return None

        try:
            company = self.enrichment_service.enrich_domain(domain)
            if company:
                logger.info(f"Enriched company data for domain: {domain}")
            return company
        except Exception as e:
            # Don't fail webhook processing if enrichment fails
            logger.warning(f"Failed to enrich company for {domain}: {e}")
            return None
