import random
from typing import Any, Dict, List

from .domain_models import Priority
from .enrichment import ActionItem, EnrichedNotification


class MessageGenerator:
    """Generates whimsical and engaging Slack messages"""

    # Fun emojis for different event types
    EMOJIS = {
        "payment_success": ["🎉", "💰", "🌟", "✨", "🎊", "🚀"],
        "payment_failure": ["😅", "🤔", "🔄", "💫", "🎯"],
        "subscription_updated": ["📈", "🆙", "💪", "🌈", "🎨"],
        "trial_end": ["⏰", "🎭", "🎪", "🎢", "🎡"],
        "refund": ["↩️", "🔄", "🎪", "🎭"],
    }

    # Fun message templates for different event types
    SUCCESS_MESSAGES = [
        "Ka-ching! 💰 Another happy payment from {customer}!",
        "Money in the bank! 🎉 {customer} just dropped some coins in our jar!",
        "Woohoo! {customer} just made it rain! 💸",
        "Cha-ching! 🌟 {customer} keeps the party going!",
        "Another successful payment! {customer} is on fire! 🔥",
    ]

    FAILURE_MESSAGES = [
        "Oopsie! 😅 Looks like {customer}'s payment needs a little TLC",
        "Houston, we have a tiny hiccup! 🚀 {customer}'s payment is playing hide and seek",
        "Time for a payment adventure! 🗺️ {customer} needs our help",
        "Quick heads up! 🎯 {customer}'s payment is doing the moonwalk",
        "Payment party postponed! 🎪 {customer} needs a helping hand",
    ]

    UPGRADE_MESSAGES = [
        "Level up! 🎮 {customer} just upgraded their subscription!",
        "Pow! Bam! Zoom! 💥 {customer} is growing with us!",
        "To infinity and beyond! 🚀 {customer} just upgraded!",
        "Achievement unlocked! 🏆 {customer} leveled up their plan!",
        "Super upgrade time! ⭐ {customer} is reaching for the stars!",
    ]

    TRIAL_END_MESSAGES = [
        "The clock is ticking! ⏰ {customer}'s trial is wrapping up",
        "Trial finale approaching! 🎭 Time to check in with {customer}",
        "Last call for trial magic! ✨ {customer}'s journey continues",
        "Trial end in sight! 🔭 Let's make sure {customer} is loving it",
        "Final countdown! 🚀 {customer}'s trial is nearing the finish line",
    ]

    def generate_message(self, notification: EnrichedNotification) -> Dict[str, Any]:
        """Generate a whimsical and informative Slack message"""
        event = notification.event
        customer = notification.customer_data

        # Get base message template
        base_message = self._get_base_message(event.type, customer.name)

        # Get random emoji for the event type
        emoji = random.choice(self.EMOJIS.get(event.type, ["✨"]))

        # Build the message blocks
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} {base_message}",
                    "emoji": True,
                },
            }
        ]

        # Add insights section if available
        if notification.insights:
            blocks.append(self._create_insights_section(notification.insights))

        # Add metrics section
        blocks.append(self._create_metrics_section(notification.metrics))

        # Add action items if available
        if notification.action_items:
            blocks.extend(self._create_action_items_section(notification.action_items))

        # Add related events if available
        if notification.related_events:
            blocks.append(
                self._create_related_events_section(notification.related_events)
            )

        # Add customer profile link
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"👤 <https://your-crm.com/customers/{customer.customer_id}|View Customer Profile>",
                    }
                ],
            }
        )

        return {
            "blocks": blocks,
            "text": base_message,  # Fallback text
        }

    def _get_base_message(self, event_type: str, customer_name: str) -> str:
        """Get a random message template for the event type"""
        templates = {
            "payment_success": self.SUCCESS_MESSAGES,
            "payment_failure": self.FAILURE_MESSAGES,
            "subscription_updated": self.UPGRADE_MESSAGES,
            "trial_end": self.TRIAL_END_MESSAGES,
        }

        template = random.choice(templates.get(event_type, self.SUCCESS_MESSAGES))
        return template.format(customer=customer_name)

    def _create_insights_section(self, insights: List[str]) -> Dict[str, Any]:
        """Create a section block for insights"""
        return {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "🔍 *Insights*\n"
                + "\n".join(f"• {insight}" for insight in insights),
            },
        }

    def _create_metrics_section(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Create a section block for metrics"""
        formatted_metrics = []

        if "lifetime_value" in metrics:
            formatted_metrics.append(
                f"💎 Lifetime Value: ${metrics['lifetime_value']:,.2f}"
            )

        if "account_age_days" in metrics:
            formatted_metrics.append(
                f"📅 Account Age: {metrics['account_age_days']} days"
            )

        if "total_successful_payments" in metrics:
            formatted_metrics.append(
                f"💫 Total Payments: {metrics['total_successful_payments']}"
            )

        if "recent_payment_failures" in metrics:
            formatted_metrics.append(
                f"⚠️ Recent Failures: {metrics['recent_payment_failures']}"
            )

        if "average_payment_amount" in metrics:
            formatted_metrics.append(
                f"📊 Avg Payment: ${metrics['average_payment_amount']:,.2f}"
            )

        return {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Key Metrics*\n" + "\n".join(formatted_metrics),
            },
        }

    def _create_action_items_section(
        self, action_items: List[ActionItem]
    ) -> List[Dict[str, Any]]:
        """Create section blocks for action items"""
        blocks = [
            {"type": "divider"},
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "🎯 *Action Items*"},
            },
        ]

        for item in action_items:
            priority_emoji = {
                Priority.URGENT: "🚨",
                Priority.HIGH: "⚡",
                Priority.MEDIUM: "⚪",
                Priority.LOW: "⭕",
            }.get(item.priority, "⚪")

            due_date = (
                item.due_date.strftime("%Y-%m-%d %H:%M")
                if item.due_date
                else "No due date"
            )

            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"{priority_emoji} *{item.title}*\n"
                            f"_{item.description}_\n"
                            f"Due: {due_date}"
                        ),
                    },
                }
            )

        return blocks

    def _create_related_events_section(self, events: List[Any]) -> Dict[str, Any]:
        """Create a section block for related events"""
        if not events:
            return {}

        event_lines = []
        for event in events[:3]:  # Show only last 3 events
            event_date = event.timestamp.strftime("%Y-%m-%d")
            event_lines.append(f"• {event_date}: {event.type} (${event.amount:,.2f})")

        return {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "📜 *Recent Events*\n" + "\n".join(event_lines),
            },
        }
