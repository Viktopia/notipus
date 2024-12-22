from typing import Dict, Any, List

from .insights import CustomerInsightAnalyzer
from .models import Notification, PaymentEvent, NotificationSection


class EventProcessor:
    """Processes payment events and generates enriched notifications"""

    VALID_EVENT_TYPES = {
        "payment_success",
        "payment_failure",
        "trial_end",
        "subscription_update",
    }

    def __init__(self):
        self.insight_analyzer = CustomerInsightAnalyzer()

    def format_notification(
        self, event: PaymentEvent, customer_data: Dict[str, Any]
    ) -> Notification:
        """Format a payment event into an enriched notification"""
        # Validate event type
        if event.event_type not in self.VALID_EVENT_TYPES:
            raise ValueError(f"Invalid event type: {event.event_type}")

        # Validate customer data
        required_fields = ["company_name", "team_size", "plan_name"]
        missing_fields = [
            field for field in required_fields if field not in customer_data
        ]
        if missing_fields:
            raise ValueError(
                f"Missing required customer data: {', '.join(missing_fields)}"
            )

        # Create notification sections
        sections = self._create_notification_sections(event, customer_data)

        # Create action buttons based on event type and insights
        action_buttons = self._create_action_buttons(
            event, self.insight_analyzer.analyze_customer(event, customer_data)
        )

        return Notification(
            id=event.id,
            status=event.status,
            event=event,
            sections=sections,
            action_buttons=action_buttons,
        )

    def _get_notification_properties(
        self, event: PaymentEvent
    ) -> tuple[str, str, str, str]:
        """Get notification properties based on event type"""
        amount_str = f"${event.amount:,.2f}" if event.amount else ""

        if event.event_type == "payment_success":
            return (
                f"🎉 Payment Received: {amount_str}",
                "#36a64f",  # Green
                "low",
                "payment",
            )
        elif event.event_type == "payment_failure":
            return (
                f"🚨 Payment Failed: {amount_str}",
                "#dc3545",  # Red
                "high",
                "payment",
            )
        elif event.event_type == "trial_end":
            days_left = event.metadata.get("days_remaining", "few")
            return (
                f"📢 Trial Ending in {days_left} Days",
                "#ffc107",  # Yellow
                "medium",
                "trial",
            )
        elif event.event_type == "subscription_update":
            old_plan = event.metadata.get("old_plan", "")
            new_plan = event.metadata.get("new_plan", "")
            if old_plan and new_plan:
                return (
                    f"📈 Plan Change: {old_plan} → {new_plan}",
                    "#17a2b8",  # Blue
                    "low",
                    "subscription",
                )
            return (
                "ℹ️ Subscription Updated",
                "#17a2b8",  # Blue
                "low",
                "subscription",
            )
        else:
            return (
                "ℹ️ Account Update",
                "#17a2b8",  # Blue
                "low",
                "general",
            )

    def _create_notification_sections(
        self, event: PaymentEvent, customer_data: Dict[str, Any]
    ) -> List[NotificationSection]:
        """Create notification sections based on event type"""
        sections = []

        # Add event details section
        if event.event_type == "payment_success":
            sections.append(
                NotificationSection(
                    text=(
                        f"Successfully processed payment of "
                        f"{event.amount} {event.currency}"
                    )
                )
            )
        elif event.event_type == "payment_failure":
            sections.append(
                NotificationSection(
                    text=(
                        f"Failed to process payment of "
                        f"{event.amount} {event.currency}\n"
                        f"Reason: {event.metadata.get('failure_reason', 'Unknown')}"
                    )
                )
            )
        elif event.event_type == "trial_end":
            trial_days = event.metadata.get("trial_days_remaining", 0)
            sections.append(
                NotificationSection(
                    text=(
                        f"Trial period ending in {trial_days} days\n"
                        f"Plan: {customer_data.get('plan_name', 'Unknown')}"
                    )
                )
            )

        # Add customer details section
        sections.append(
            NotificationSection(
                text=(
                    f"*Customer Details:*\n"
                    f"• Company: {customer_data.get('company_name', 'N/A')}\n"
                    f"• Team Size: {customer_data.get('team_size', 0)}\n"
                    f"• Plan: {customer_data.get('plan_name', 'N/A')}"
                )
            )
        )

        return sections

    def _create_action_buttons(
        self, event: PaymentEvent, customer_insights: Any
    ) -> List[Dict[str, Any]]:
        """Create action buttons based on event type and insights"""
        buttons = []

        if event.event_type == "payment_failure":
            buttons.extend(
                [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Update Payment Method",
                        },
                        "style": "primary",
                        "url": f"/update-payment/{event.customer_id}",
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Contact Support",
                        },
                        "url": f"/support/{event.customer_id}",
                    },
                ]
            )
        elif event.event_type == "trial_end":
            buttons.extend(
                [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Upgrade Now",
                        },
                        "style": "primary",
                        "url": f"/upgrade/{event.customer_id}",
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Schedule Demo",
                        },
                        "url": f"/schedule-demo/{event.customer_id}",
                    },
                ]
            )

        # Add general action buttons based on insights
        if customer_insights.recommendations:
            buttons.append(
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "View Recommendations",
                    },
                    "url": f"/recommendations/{event.customer_id}",
                }
            )

        return buttons
