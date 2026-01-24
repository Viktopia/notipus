"""Event processor for webhook notifications.

This module handles processing events from various providers and
formatting them into Slack notifications with company enrichment.
"""

import logging
from typing import Any, ClassVar

from core.models import Company
from core.services.enrichment import DomainEnrichmentService
from core.utils.email_domain import extract_domain, is_enrichable_domain

from ..models.notification import Notification, Section
from .database_lookup import DatabaseLookupService

logger = logging.getLogger(__name__)


class EventProcessor:
    """Process events from various providers and format notifications.

    This class handles the core event processing logic, including
    cross-reference lookups and notification formatting.

    Attributes:
        VALID_EVENT_TYPES: Set of recognized event type strings.
    """

    VALID_EVENT_TYPES: ClassVar[set[str]] = {
        "payment_success",
        "payment_failure",
        "subscription_created",
        "subscription_updated",
        "subscription_canceled",
        "subscription_deleted",
        "trial_ending",
        "customer_updated",
    }

    def __init__(self) -> None:
        """Initialize the event processor with services."""
        self.db_lookup = DatabaseLookupService()
        self.enrichment_service = DomainEnrichmentService()

    def process_event(
        self, event_data: dict[str, Any], customer_data: dict[str, Any]
    ) -> Notification:
        """Process an event and return a notification.

        Args:
            event_data: Dictionary containing event type and metadata.
            customer_data: Dictionary containing customer information.

        Returns:
            A Notification object ready for Slack delivery.

        Raises:
            ValueError: If event_data is missing or has invalid type.
        """
        if not event_data or "type" not in event_data:
            raise ValueError("Missing event type")

        event_type = event_data["type"]
        if event_type not in self.VALID_EVENT_TYPES:
            raise ValueError(f"Invalid event type: {event_type}")

        return self.format_notification(event_data, customer_data)

    def format_notification(
        self, event_data: dict[str, Any], customer_data: dict[str, Any]
    ) -> Notification:
        """Format event data into a notification.

        Args:
            event_data: Dictionary containing event type and metadata.
            customer_data: Dictionary containing customer information.

        Returns:
            A Notification object formatted for Slack.

        Raises:
            ValueError: If required data is missing or invalid.
        """
        if not event_data:
            raise ValueError("Missing event data")
        if not customer_data:
            raise ValueError("Missing customer data")

        # Validate required customer data
        company_name = customer_data.get("company_name") or customer_data.get(
            "company", "Individual"
        )
        if not company_name:
            raise ValueError("Missing required customer data: company name")

        # Validate amount if present
        if "amount" in event_data:
            amount = event_data["amount"]
            if amount is not None and amount < 0:
                raise ValueError("Amount cannot be negative")

        # Validate currency if present
        if "currency" in event_data:
            currency = event_data["currency"]
            if currency and currency not in ["USD", "EUR", "GBP", "CAD", "AUD"]:
                raise ValueError("Invalid currency")

        # Store event data in database and perform cross-reference lookups
        enriched_event_data = self._enrich_with_cross_references(event_data)

        # Enrich with company branding if email domain is enrichable
        company = self._enrich_company(customer_data)

        # Create notification sections
        main_section = self._create_main_section(enriched_event_data, customer_data)
        customer_section = self._create_customer_section(customer_data, company)

        # Add cross-reference section if we found related data
        sections = [main_section, customer_section]
        if self._has_cross_references(enriched_event_data):
            sections.append(self._create_cross_reference_section(enriched_event_data))

        # Determine color and emoji based on event type
        color, emoji = self._get_notification_style(enriched_event_data["type"])

        return Notification(
            title=f"{emoji} {self._get_title(enriched_event_data, company_name)}",
            sections=sections,
            color=color,
            emoji=emoji,
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
        if event_data.get("type") in ["payment_success", "payment_failure"]:
            self.db_lookup.store_payment_record(event_data)
        elif event_data.get("provider") == "shopify":
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

    def _has_cross_references(self, event_data: dict[str, Any]) -> bool:
        """Check if event data has cross-reference information.

        Args:
            event_data: Event data dictionary.

        Returns:
            True if cross-references exist, False otherwise.
        """
        metadata = event_data.get("metadata", {})
        return bool(
            metadata.get("related_payment_ref") or metadata.get("related_order_ref")
        )

    def _create_cross_reference_section(self, event_data: dict[str, Any]) -> Section:
        """Create a section showing cross-reference information.

        Args:
            event_data: Event data with cross-references.

        Returns:
            Section containing related transaction information.
        """
        metadata = event_data.get("metadata", {})
        fields: dict[str, str] = {}

        if metadata.get("related_payment_ref"):
            fields["Related Payment"] = (
                f"Chargify Payment #{metadata['related_payment_ref']}"
            )

        if metadata.get("related_order_ref"):
            fields["Related Order"] = f"Shopify Order #{metadata['related_order_ref']}"

        return Section("🔗 Related Transactions", fields)

    def _create_main_section(
        self, event_data: dict[str, Any], customer_data: dict[str, Any]
    ) -> Section:
        """Create the main event information section.

        Args:
            event_data: Event data dictionary.
            customer_data: Customer data dictionary.

        Returns:
            Section containing event details.
        """
        fields: dict[str, str] = {}

        # Event type and status
        fields["Event"] = event_data["type"].replace("_", " ").title()

        if "status" in event_data:
            status = event_data["status"]
            status_emoji = {"success": "✅", "failed": "❌", "pending": "⏳"}.get(
                status, "ℹ️"
            )
            fields["Status"] = f"{status_emoji} {status.title()}"

        # Amount and currency
        if "amount" in event_data:
            amount = event_data["amount"]
            currency = event_data.get("currency", "USD")
            fields["Amount"] = f"{currency} {amount:,.2f}"

        # Metadata fields
        metadata = event_data.get("metadata", {})
        if metadata.get("plan_name"):
            fields["Plan"] = metadata["plan_name"]
        if metadata.get("subscription_id"):
            fields["Subscription"] = f"#{metadata['subscription_id']}"
        if metadata.get("transaction_id"):
            fields["Transaction"] = f"#{metadata['transaction_id']}"
        if metadata.get("failure_reason"):
            fields["Failure Reason"] = f"❌ {metadata['failure_reason']}"

        return Section("📊 Event Details", fields)

    def _create_customer_section(
        self, customer_data: dict[str, Any], company: Company | None = None
    ) -> Section:
        """Create the customer information section with optional company branding.

        Args:
            customer_data: Customer data dictionary.
            company: Optional enriched Company model with branding.

        Returns:
            Section containing customer information and company logo.
        """
        fields: dict[str, str] = {}

        # Company and contact info - prefer enriched company name
        if company and company.name:
            company_display = company.name
        else:
            company_display = customer_data.get("company_name") or customer_data.get(
                "company", "Individual"
            )
        fields["Company"] = company_display

        # Add industry from enrichment if available
        if company and company.brand_info:
            industry = company.brand_info.get("industry")
            if industry:
                fields["Industry"] = industry

        if customer_data.get("email"):
            fields["Email"] = customer_data["email"]

        # Customer name
        first_name = customer_data.get("first_name", "")
        last_name = customer_data.get("last_name", "")
        if first_name or last_name:
            fields["Contact"] = f"{first_name} {last_name}".strip()

        # Order/spending info
        if customer_data.get("orders_count"):
            fields["Total Orders"] = str(customer_data["orders_count"])
        if customer_data.get("total_spent"):
            fields["Total Spent"] = f"${customer_data['total_spent']}"

        # Create section with optional logo accessory
        section = Section("👤 Customer Info", fields)

        # Add company logo as accessory if available
        if company and company.has_logo:
            section.accessory = {
                "type": "image",
                "image_url": company.get_logo_url(),
                "alt_text": company.name or company.domain,
            }

        return section

    def _get_title(self, event_data: dict[str, Any], company_name: str) -> str:
        """Generate notification title.

        Args:
            event_data: Event data dictionary.
            company_name: Company name for the title.

        Returns:
            Formatted notification title string.
        """
        event_type = event_data["type"]

        if event_type == "payment_success":
            return f"Payment received from {company_name}"
        elif event_type == "payment_failure":
            return f"Payment failed for {company_name}"
        elif event_type == "subscription_created":
            return f"New subscription for {company_name}"
        elif event_type == "subscription_canceled":
            return f"Subscription canceled for {company_name}"
        else:
            return f"{event_type.replace('_', ' ').title()} for {company_name}"

    def _get_notification_style(self, event_type: str) -> tuple[str, str]:
        """Get color and emoji for notification based on event type.

        Args:
            event_type: The type of event.

        Returns:
            Tuple of (hex_color, emoji) for the notification.
        """
        if event_type == "payment_success":
            return "#28a745", "💰"  # Green, money emoji
        elif event_type == "payment_failure":
            return "#dc3545", "❌"  # Red, X emoji
        elif event_type == "subscription_created":
            return "#17a2b8", "🎉"  # Blue, celebration emoji
        elif event_type == "subscription_canceled":
            return "#ffc107", "⚠️"  # Yellow, warning emoji
        else:
            return "#17a2b8", "ℹ️"  # Blue, info emoji
