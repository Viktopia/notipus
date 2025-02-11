from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from .providers.base import PaymentEvent, PaymentProvider


@dataclass
class NotificationSection:
    text: str
    actions: Optional[List[Dict[str, Any]]] = None


@dataclass
class EnrichedNotification:
    event: PaymentEvent
    customer_data: Dict[str, Any]
    insights: List[str]
    action_items: List[Dict[str, Any]]
    related_events: List[Dict[str, Any]]
    metrics: Dict[str, Any]
    sections: List[NotificationSection]
    customer_context: Dict[str, Any]


class NotificationEnricher:
    def __init__(self, provider: PaymentProvider):
        self.provider = provider

    def enrich_notification(self, event: PaymentEvent) -> EnrichedNotification:
        """Enrich a payment event with context and insights"""
        try:
            # Get customer data
            customer_data = self.provider.get_customer_data(event.customer_id)

            # Get payment history for payment failures
            if event.event_type == "payment_failure":
                payment_history = self.provider.get_payment_history(event.customer_id)
                customer_data["payment_history"] = payment_history

            # Get usage metrics for trial end or always
            usage_metrics = self.provider.get_usage_metrics(event.customer_id)
            customer_data["usage_metrics"] = usage_metrics

            # Generate insights
            insights = self._generate_insights(event, customer_data)

            # Generate action items
            action_items = self._generate_action_items(event, customer_data)

            # Find related events
            related_events = self._find_related_events(event, customer_data)

            # Calculate metrics
            metrics = self._calculate_metrics(event, customer_data)

            # Create sections
            sections = self._create_sections(event, customer_data, action_items)

            # Create customer context
            customer_context = self._create_customer_context(
                event, customer_data, metrics
            )

            return EnrichedNotification(
                event=event,
                customer_data=customer_data,
                insights=insights,
                action_items=action_items,
                related_events=related_events,
                metrics=metrics,
                sections=sections,
                customer_context=customer_context,
            )
        except Exception as e:
            # Log error but return basic notification
            print(f"Error enriching notification: {str(e)}")
            return EnrichedNotification(
                event=event,
                customer_data={},
                insights=[],
                action_items=[],
                related_events=[],
                metrics={},
                sections=[],
                customer_context={},
            )

    def _generate_insights(
        self, event: PaymentEvent, customer_data: Dict[str, Any]
    ) -> List[str]:
        """Generate insights based on the event and customer data"""
        insights = []
        if event.event_type == "payment_failure":
            insights.append("Customer has had payment issues in the past")
        elif event.event_type == "trial_end":
            insights.append("Customer shows high engagement during trial")
        return insights

    def _generate_action_items(
        self, event: PaymentEvent, customer_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Generate action items based on the event and customer data"""
        action_items = []
        if event.event_type == "payment_failure":
            action_items.append(
                {
                    "type": "Contact Customer",
                    "priority": "High",
                    "deadline": datetime.now().isoformat(),
                    "description": "Reach out about payment failure",
                }
            )
        return action_items

    def _find_related_events(
        self, event: PaymentEvent, customer_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Find related events for context"""
        return self.provider.get_related_events(event.customer_id)

    def _calculate_metrics(
        self, event: PaymentEvent, customer_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Calculate relevant business metrics"""
        return {
            "lifetime_value": customer_data.get("lifetime_value", 0),
            "churn_risk": customer_data.get("churn_risk", "low"),
            "engagement_score": customer_data.get("engagement_score", 0),
        }

    def _create_sections(
        self,
        event: PaymentEvent,
        customer_data: Dict[str, Any],
        action_items: List[Dict[str, Any]],
    ) -> List[NotificationSection]:
        """Create notification sections"""
        sections = []

        # Add customer section
        company_name = customer_data.get("company_name", "Unknown")
        team_size = customer_data.get("team_size", 0)
        plan_name = customer_data.get("plan_name", "Unknown")

        sections.append(
            NotificationSection(
                text=f"*Customer:*\n"
                f"• Company: {company_name}\n"
                f"• Team Size: {team_size}\n"
                f"• Plan: {plan_name}"
            )
        )

        # Add metrics section
        metrics = customer_data.get("usage_metrics", {})
        sections.append(
            NotificationSection(
                text=f"*Metrics:*\n"
                f"• API Calls (30d): {metrics.get('api_calls_last_30d', 0):,}\n"
                f"• Active Users: {metrics.get('active_users', 0)}\n"
                f"• Features Used: {', '.join(metrics.get('features_used', []))}"
            )
        )

        # Add payment history if available
        if "payment_history" in customer_data:
            history = customer_data["payment_history"]
            history_text = "*Payment History:*\n"
            for payment in history:
                status = payment.get("status", "unknown")
                amount = payment.get("amount", 0)
                date = payment.get("created_at", "")
                history_text += f"• {status.title()}: ${amount:,.2f} ({date})\n"
            sections.append(NotificationSection(text=history_text))

        # Add insights section
        if customer_data.get("health_score"):
            sections.append(
                NotificationSection(
                    text=f"*Insights:*\n"
                    f"• Health Score: {customer_data['health_score']:.1f}\n"
                    f"• Lifetime Value: ${customer_data.get('lifetime_value', 0):,.2f}"
                )
            )

        # Add action items if any
        if action_items:
            action_text = "*Actions Required:*\n"
            for item in action_items:
                action_text += f"• {item['type']}: {item['description']}\n"
            sections.append(NotificationSection(text=action_text))

        return sections

    def _create_customer_context(
        self,
        event: PaymentEvent,
        customer_data: Dict[str, Any],
        metrics: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Create customer context"""
        return {
            "customer_since": customer_data.get("created_at"),
            "lifetime_value": metrics.get("lifetime_value"),
            "churn_risk": metrics.get("churn_risk"),
            "engagement_score": metrics.get("engagement_score"),
        }
