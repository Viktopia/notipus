from typing import Dict, Any, Optional
import logging

from .models import Notification, NotificationSection

logger = logging.getLogger(__name__)


class EventProcessor:
    """Processes payment events and generates enriched notifications"""

    VALID_EVENT_TYPES = {
        "payment_success",
        "payment_failure",
        "trial_end",
        "subscription_update",
    }

    def __init__(self):
        pass

    def format_notification(self, event: Dict[str, Any], customer_data: Dict[str, Any]) -> Optional[Notification]:
        """Format event data into a notification"""
        if not event or not customer_data:
            logger.error("Missing required data")
            return None

        if event["type"] not in self.VALID_EVENT_TYPES:
            logger.error(
                "Invalid event type",
                extra={
                    "event_type": event["type"],
                    "valid_types": list(self.VALID_EVENT_TYPES),
                },
            )
            return None

        # Build notification sections
        sections = []

        # Add customer info section
        customer_section = NotificationSection(
            title="Customer Info",
            fields={
                "Company": customer_data["company_name"],
                "Team Size": str(customer_data["team_size"]),
                "Plan": customer_data["plan_name"],
            },
        )
        sections.append(customer_section)

        # Add event details section
        event_section = NotificationSection(
            title="Event Details",
            fields={
                "Type": event["type"],
                "Status": event["status"],
                "Amount": f"${event['amount']:.2f} {event['currency']}",
                "Timestamp": event["timestamp"],
            },
        )
        sections.append(event_section)

        # Add metadata section if available
        if event.get("metadata"):
            metadata_section = NotificationSection(
                title="Additional Info",
                fields=event["metadata"],
            )
            sections.append(metadata_section)

        return Notification(
            title=self._format_title(event),
            sections=sections,
            color=self._get_color(event),
            emoji=self._get_emoji(event),
        )

    def _format_title(self, event: Dict[str, Any]) -> str:
        """Format notification title based on event type"""
        amount_str = f"${event['amount']:,.2f}" if event.get('amount') else ""

        if event["type"] == "payment_success":
            return f"Payment Received: {amount_str}"
        elif event["type"] == "payment_failure":
            return f"Payment Failed: {amount_str}"
        elif event["type"] == "trial_end":
            days_left = event.get("metadata", {}).get("days_remaining", "few")
            return f"Trial Ending in {days_left} Days"
        elif event["type"] == "subscription_update":
            old_plan = event.get("metadata", {}).get("old_plan", "")
            new_plan = event.get("metadata", {}).get("new_plan", "")
            if old_plan and new_plan:
                return f"Plan Change: {old_plan} → {new_plan}"
            return "Subscription Updated"
        else:
            return "Account Update"

    def _get_color(self, event: Dict[str, Any]) -> str:
        """Get notification color based on event type"""
        if event["type"] == "payment_success":
            return "#36a64f"  # Green
        elif event["type"] == "payment_failure":
            return "#dc3545"  # Red
        elif event["type"] == "trial_end":
            return "#ffc107"  # Yellow
        elif event["type"] == "subscription_update":
            return "#17a2b8"  # Blue
        else:
            return "#17a2b8"  # Blue

    def _get_emoji(self, event: Dict[str, Any]) -> str:
        """Get notification emoji based on event type"""
        if event["type"] == "payment_success":
            return "🎉"
        elif event["type"] == "payment_failure":
            return "🚨"
        elif event["type"] == "trial_end":
            return "📢"
        elif event["type"] == "subscription_update":
            return "📈"
        else:
            return "ℹ️"
