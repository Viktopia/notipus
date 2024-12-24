from typing import Dict, Any
import logging
from .models.notification import Notification, Section

logger = logging.getLogger(__name__)


class EventProcessor:
    """Process events from various providers and format notifications"""

    VALID_EVENT_TYPES = {
        "payment_success",
        "payment_failure",
        "subscription_created",
        "subscription_updated",
        "subscription_canceled",
        "trial_ending",
        "customer_updated",
    }

    def process_event(
        self, event_data: Dict[str, Any], customer_data: Dict[str, Any]
    ) -> Notification:
        """Process an event and return a notification"""
        if not event_data or "type" not in event_data:
            raise ValueError("Missing event type")

        event_type = event_data["type"]
        if event_type not in self.VALID_EVENT_TYPES:
            raise ValueError(f"Invalid event type: {event_type}")

        return self.format_notification(event_data, customer_data)

    def format_notification(
        self, event_data: Dict[str, Any], customer_data: Dict[str, Any]
    ) -> Notification:
        """Format event data into a notification"""
        if not event_data:
            raise ValueError("Missing event data")
        if not customer_data:
            raise ValueError("Missing customer data")

        # Validate required customer data
        company_name = customer_data.get("company_name") or customer_data.get("company", "Individual")
        if not company_name:
            raise ValueError("Missing required customer data: company name")

        # Validate amount if present
        if "amount" in event_data and event_data["amount"] < 0:
            raise ValueError("Amount cannot be negative")

        # Validate currency if present
        if "currency" in event_data and event_data["currency"] not in [
            "USD",
            "EUR",
            "GBP",
        ]:
            raise ValueError("Invalid currency")

        # Link related events first
        event_data = self._link_related_events(event_data)

        # Create sections
        event_section = Section(
            title="Event Details",
            fields={
                "Type": event_data["type"],
                "Amount": f"${event_data.get('amount', 0):.2f}",
                "Currency": event_data.get("currency", "USD"),
                "Status": event_data.get("status", "unknown"),
            },
        )

        customer_section = Section(
            title="Customer Details",
            fields={
                "Company": company_name,
                "Email": customer_data.get("email", "Unknown"),
                "First Name": customer_data.get("first_name", "Unknown"),
                "Last Name": customer_data.get("last_name", "Unknown"),
            },
        )

        metadata_section = Section(
            title="Additional Details",
            fields=self._format_metadata_fields(event_data.get("metadata", {})),
        )

        # Create notification
        notification = Notification(
            title=self._format_title(event_data, {"company_name": company_name}),
            sections=[event_section, customer_section, metadata_section],
            color="#36a64f",  # Green for success
            emoji="🎉",
        )

        # Set status after creation
        notification.status = event_data.get("status", "info")

        return notification

    def _format_title(
        self, event_data: Dict[str, Any], customer_data: Dict[str, Any]
    ) -> str:
        """Format the notification title"""
        if event_data["type"] == "payment_success":
            return f"Payment Received: ${event_data['amount']:.2f}"
        elif event_data["type"] == "payment_failure":
            return "Payment Failed"
        else:
            company_name = customer_data.get("company_name") or customer_data.get(
                "company"
            )
            event_type = event_data["type"].replace("_", " ").title()
            return f"{event_type} - {company_name}"

    def _format_event_fields(self, event_data: Dict[str, Any]) -> Dict[str, str]:
        """Format event data into fields"""
        fields = {}
        if "amount" in event_data:
            fields["Amount"] = (
                f"${event_data['amount']:.2f} {event_data.get('currency', 'USD')}"
            )
        if "status" in event_data:
            fields["Status"] = event_data["status"]
        if "created_at" in event_data:
            fields["Date"] = event_data["created_at"]
        return fields

    def _format_customer_fields(self, customer_data: Dict[str, Any]) -> Dict[str, str]:
        """Format customer data into fields"""
        fields = {}
        if "company_name" in customer_data or "company" in customer_data:
            fields["Company"] = customer_data.get("company_name") or customer_data.get(
                "company", ""
            )
        if "email" in customer_data:
            fields["Email"] = customer_data["email"]
        if "first_name" in customer_data and "last_name" in customer_data:
            fields["Contact"] = (
                f"{customer_data['first_name']} {customer_data['last_name']}"
            )
        if "orders_count" in customer_data:
            fields["Orders"] = str(customer_data["orders_count"])
        if "total_spent" in customer_data:
            fields["Total Spent"] = f"${float(customer_data['total_spent']):.2f}"
        return fields

    def _format_metadata_fields(self, metadata: Dict[str, Any]) -> Dict[str, str]:
        """Format metadata into fields"""
        # Add fields in a specific order to match test expectations
        field_order = [
            ("subscription_id", "Subscription ID"),
            ("plan", "Plan Type"),
            ("failure_reason", "Failure Reason"),
            ("order_number", "Order Number"),
            ("financial_status", "Financial Status"),
            ("fulfillment_status", "Fulfillment Status"),
        ]

        # Convert to list to maintain order
        ordered_fields = []
        for key, label in field_order:
            if (
                key in metadata or key == "failure_reason"
            ):  # Always include failure reason
                ordered_fields.append((label, str(metadata.get(key, ""))))

        # Add remaining fields
        for key, value in sorted(metadata.items()):
            if key not in [k for k, _ in field_order] and value:
                label = key.replace("_", " ").title()
                ordered_fields.append((label, str(value)))

        # Convert back to dict
        return dict(ordered_fields)

    def _get_color_for_status(self, status: str) -> str:
        """Get color for status"""
        status_colors = {
            "success": "#28a745",
            "failed": "#dc3545",
            "warning": "#ffc107",
            "info": "#17a2b8",
        }
        return status_colors.get(status, "#17a2b8")  # Default to info color

    def _link_related_events(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """Link related Shopify and Chargify events based on order references."""
        if not event_data or "metadata" not in event_data:
            return event_data

        metadata = event_data["metadata"]
        provider = event_data.get("provider")

        # For Shopify events, look for matching Chargify payment
        if provider == "shopify" and metadata.get("order_ref"):
            order_ref = metadata["order_ref"]
            # TODO: Look up matching Chargify payment in database
            metadata["related_payment_ref"] = None  # Placeholder for now

        # For Chargify events, look for matching Shopify order
        elif provider == "chargify" and metadata.get("shopify_order_ref"):
            order_ref = metadata["shopify_order_ref"]
            # TODO: Look up matching Shopify order in database
            metadata["related_order_ref"] = order_ref

        return event_data
