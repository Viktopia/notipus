from datetime import datetime, timedelta
from enum import Enum
from typing import List, Optional


class EventType(Enum):
    PAYMENT_FAILURE = "payment_failure"
    TRIAL_END = "trial_end"
    UPGRADE = "upgrade"


class Priority(Enum):
    URGENT = "urgent"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Action:
    def __init__(
        self, type: str, link: Optional[str] = None, due_date: Optional[datetime] = None
    ):
        self.type = type
        self.link = link
        self.due_date = due_date
        self.deadline = due_date  # For compatibility with tests


class CustomerContext:
    def __init__(self):
        self.customer_health_score = 0.0
        self.churn_risk_score = 0.0
        self.recent_interactions = []
        self.feature_usage = {}
        self.payment_history = []

    def calculate_health_score(self, customer_data: dict) -> float:
        # TODO: Implement actual health score calculation
        return 0.75

    def calculate_churn_risk(self, customer_data: dict) -> float:
        # TODO: Implement actual churn risk calculation
        return 0.25


class Event:
    def __init__(self, type: EventType, priority: Priority, response_sla: timedelta):
        self.type = type
        self.priority = priority
        self.response_sla = response_sla


class CorrelatedEvents:
    def __init__(self, event_chain: List[dict], resolution: str, duration: timedelta):
        self.event_chain = event_chain
        self.resolution = resolution
        self.duration = duration


class NotificationSection:
    def __init__(self, text: str, actions: Optional[List[Action]] = None):
        self.text = text
        self.actions = actions or []


class Notification:
    def __init__(
        self,
        header: str,
        color: str,
        sections: List[NotificationSection],
        action_buttons: List[dict],
        customer_context: CustomerContext,
    ):
        self.header = header
        self.color = color
        self.sections = sections
        self.action_buttons = action_buttons
        self.customer_context = customer_context

    def to_slack_message(self) -> dict:
        """Convert the notification to a Slack message format."""
        blocks = []

        # Add header block
        blocks.append(
            {"type": "header", "text": {"type": "plain_text", "text": self.header}}
        )

        # Add sections
        for section in self.sections:
            blocks.append(
                {"type": "section", "text": {"type": "mrkdwn", "text": section.text}}
            )
            if section.actions:
                blocks.append(
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": action.type},
                                "url": action.link,
                            }
                            for action in section.actions
                            if action.link
                        ],
                    }
                )

        # Add action buttons
        if self.action_buttons:
            blocks.append({"type": "actions", "elements": self.action_buttons})

        return {"blocks": blocks, "color": self.color}


class EventProcessor:
    def classify_event(self, event_data: dict) -> Event:
        event_type = event_data.get("event")
        customer = event_data.get("customer", {})

        if event_type == "payment_failure":
            if (
                customer.get("lifetime_value", 0) > 10000
                or customer.get("subscription_tier") == "enterprise"
            ):
                return Event(
                    EventType.PAYMENT_FAILURE, Priority.URGENT, timedelta(hours=2)
                )
            return Event(EventType.PAYMENT_FAILURE, Priority.HIGH, timedelta(hours=4))

        elif event_type == "trial_end":
            if (
                customer.get("trial_usage") == "high"
                and customer.get("feature_adoption", 0) > 0.7
            ):
                return Event(EventType.TRIAL_END, Priority.HIGH, timedelta(hours=24))
            return Event(EventType.TRIAL_END, Priority.MEDIUM, timedelta(days=2))

        elif event_type == "subscription_upgrade":
            return Event(EventType.UPGRADE, Priority.MEDIUM, timedelta(days=2))

        return Event(EventType.PAYMENT_FAILURE, Priority.LOW, timedelta(days=7))

    def enrich_customer_context(self, customer_data: dict) -> CustomerContext:
        context = CustomerContext()
        context.customer_health_score = context.calculate_health_score(customer_data)
        context.churn_risk_score = context.calculate_churn_risk(customer_data)
        context.recent_interactions = [
            "Support ticket #123",
            "Sales call on 2024-03-01",
        ]
        context.feature_usage = {"feature1": 0.8, "feature2": 0.6}
        context.payment_history = ["2024-02-01: Success", "2024-01-01: Success"]
        return context

    def generate_action_items(self, event_data: dict) -> List[Action]:
        event_type = event_data.get("event")
        customer = event_data.get("customer", {})
        actions = []

        if event_type == "payment_failure":
            actions = [
                Action(
                    "contact_customer",
                    "mailto:" + customer.get("billing_contact", ""),
                    datetime.now() + timedelta(hours=2),
                ),
                Action(
                    "update_payment_method",
                    "https://billing.example.com",
                    datetime.now() + timedelta(hours=4),
                ),
                Action(
                    "review_account",
                    "https://crm.example.com",
                    datetime.now() + timedelta(days=1),
                ),
            ]
        elif event_type == "trial_end":
            actions = [
                Action(
                    "schedule_call",
                    "https://calendar.example.com",
                    datetime.now() + timedelta(days=1),
                ),
                Action(
                    "send_case_studies",
                    "https://crm.example.com/templates",
                    datetime.now() + timedelta(days=2),
                ),
            ]

        return actions

    def format_notification(self, event_data: dict) -> Notification:
        event_type = event_data.get("type")
        priority = event_data.get("priority")
        customer = event_data.get("customer", {})

        header = (
            "🚨 Urgent Notification"
            if priority == Priority.URGENT
            else "📢 Notification"
        )
        color = "#FF0000" if priority == Priority.URGENT else "#FFA500"

        sections = [
            NotificationSection(
                f"*Customer:* {customer.get('name')}\n*Tier:* {customer.get('tier')}"
            )
        ]

        # Always include an Actions Required section
        actions = self.generate_action_items(
            {"event": event_type, "customer": customer}
        )
        sections.append(
            NotificationSection(
                "*Actions Required:*\n"
                + (
                    "\n".join(f"• {a.type} (Due: {a.deadline})" for a in actions)
                    if actions
                    else "• No immediate actions required"
                ),
                actions,
            )
        )

        # Always include action buttons
        action_buttons = [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "View Customer"},
                "url": f"https://crm.example.com/customers/{customer.get('id', '')}",
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Contact Support"},
                "url": "https://support.example.com",
            },
        ]

        # Add event-specific buttons
        if event_type == EventType.PAYMENT_FAILURE:
            action_buttons.append(
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Update Payment"},
                    "url": f"https://billing.example.com/customers/{customer.get('id', '')}/payment",
                }
            )
        elif event_type == EventType.TRIAL_END:
            action_buttons.append(
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Schedule Demo"},
                    "url": "https://calendly.com/demo",
                }
            )

        return Notification(
            header=header,
            color=color,
            sections=sections,
            action_buttons=action_buttons,
            customer_context=self.enrich_customer_context({"customer": customer}),
        )

    def correlate_events(self, events: List[dict]) -> CorrelatedEvents:
        if not events:
            return CorrelatedEvents([], "", timedelta())

        sorted_events = sorted(events, key=lambda e: e["timestamp"])
        first_event = datetime.fromisoformat(
            sorted_events[0]["timestamp"].replace("Z", "+00:00")
        )
        last_event = datetime.fromisoformat(
            sorted_events[-1]["timestamp"].replace("Z", "+00:00")
        )
        duration = last_event - first_event

        return CorrelatedEvents(
            event_chain=sorted_events,
            resolution=sorted_events[-1]["event"],
            duration=duration,
        )
