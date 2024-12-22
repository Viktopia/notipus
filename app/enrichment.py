from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict

from .models import CustomerContext, Priority, ActionItem

@dataclass
class EnrichedNotification:
    event_type: str
    priority: Priority
    context: Dict[str, Any]
    actions: List[ActionItem]
    timestamp: datetime

    def __contains__(self, item):
        """Make the object support 'in' operator"""
        return hasattr(self, item)

class NotificationEnricher:
    def enrich_notification(self, event: Dict[str, Any]) -> EnrichedNotification:
        """Enrich a notification with context and actions"""
        event_type = event.get("type", "unknown")
        customer_id = event.get("customer_id")

        # Get customer context
        context = self.get_customer_context(customer_id)

        # Build enriched context based on event type
        enriched_context = {
            "customer": asdict(context),
            **self._get_event_specific_context(event),
            "related_events": self._get_related_events(customer_id),
            "event_patterns": self._identify_patterns(customer_id),
            "pattern_based_recommendations": self._get_pattern_recommendations(customer_id)
        }

        # Generate action items
        actions = self.generate_action_items(event)

        # Determine priority
        priority = self._calculate_priority(event, context)

        return EnrichedNotification(
            event_type=event_type,
            priority=priority,
            context=enriched_context,
            actions=actions,
            timestamp=datetime.now()
        )

    def get_customer_context(self, customer_id: str) -> CustomerContext:
        """Get comprehensive customer context"""
        # This would integrate with your customer data platform
        # For now, returning mock data
        now = datetime.now()
        customer_since = now - timedelta(days=90)

        return CustomerContext(
            customer_id=customer_id,
            name="Mock Customer",
            subscription_start=customer_since,
            current_plan="pro",
            customer_health_score=0.8,
            health_score=0.85,
            churn_risk_score=0.2,
            lifetime_value=5000.0,
            recent_interactions=[
                {
                    "type": "support",
                    "timestamp": now - timedelta(days=5),
                    "description": "Feature inquiry"
                }
            ],
            feature_usage={
                "api": 0.9,
                "dashboard": 0.7,
                "integrations": 0.5
            },
            payment_history=[
                {
                    "amount": 500,
                    "status": "success",
                    "date": now - timedelta(days=30)
                }
            ],
            metrics={
                "active_users_trend": [10, 12, 15, 18],
                "feature_usage": {
                    "api_calls": 1000,
                    "dashboard_views": 500
                },
                "support_tickets": 2
            },
            customer_since=customer_since,
            last_interaction=now - timedelta(days=1),
            account_stage="growth"
        )

    def generate_action_items(self, event: Dict[str, Any]) -> List[ActionItem]:
        """Generate specific and actionable items based on the event"""
        event_type = event.get("type", "unknown")
        actions = []

        if event_type == "payment_failure":
            actions.extend(self._generate_payment_failure_actions(event))
        elif event_type == "trial_ending":
            actions.extend(self._generate_trial_ending_actions(event))
        elif event_type == "subscription_cancelled":
            actions.extend(self._generate_cancellation_actions(event))

        return actions

    def _get_event_specific_context(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Get context specific to the event type"""
        event_type = event.get("type", "unknown")
        context = {}

        if event_type == "payment_failure":
            context["payment_history"] = {
                "last_successful_payment": datetime.now() - timedelta(days=30),
                "total_successful_payments": 5,
                "average_payment_amount": 500
            }
            context["risk_factors"] = [
                "First payment failure",
                "High-value customer"
            ]

        elif event_type == "trial_ending":
            context["usage_metrics"] = {
                "active_users": 5,
                "feature_adoption_rate": 0.7,
                "engagement_score": 8.5
            }
            context["conversion_indicators"] = {
                "similar_customers_conversion_rate": 0.75,
                "positive_signals": ["High feature usage", "Team collaboration"],
                "areas_of_concern": ["No admin user setup"]
            }

        return context

    def _get_related_events(self, customer_id: str) -> List[Dict[str, Any]]:
        """Get related events for the customer"""
        # This would integrate with your event store
        # For now, returning mock data
        now = datetime.now()
        return [
            {
                "type": "login",
                "timestamp": (now - timedelta(days=1)).isoformat(),
                "details": "User login from web"
            },
            {
                "type": "feature_used",
                "timestamp": (now - timedelta(days=2)).isoformat(),
                "details": "API integration setup"
            }
        ]

    def _identify_patterns(self, customer_id: str) -> List[str]:
        """Identify patterns in customer behavior"""
        # This would use your analytics/ML system
        # For now, returning mock patterns
        return [
            "Regular weekly usage",
            "Multiple team members active",
            "Growing feature adoption"
        ]

    def _get_pattern_recommendations(self, customer_id: str) -> List[str]:
        """Get recommendations based on identified patterns"""
        return [
            "Schedule quarterly business review",
            "Introduce advanced features",
            "Suggest team training session"
        ]

    def _calculate_priority(self, event: Dict[str, Any], context: CustomerContext) -> Priority:
        """Calculate priority based on event type and customer context"""
        event_type = event.get("type", "unknown")

        if event_type == "payment_failure" and context.lifetime_value > 1000:
            return Priority.URGENT
        elif event_type == "trial_ending" and context.customer_health_score > 0.7:
            return Priority.HIGH
        elif event_type == "subscription_cancelled":
            return Priority.HIGH

        return Priority.MEDIUM

    def _generate_payment_failure_actions(self, event: Dict[str, Any]) -> List[ActionItem]:
        """Generate actions for payment failure"""
        now = datetime.now()
        return [
            ActionItem(
                type="contact",
                description="Contact customer about failed payment",
                owner_role="account_manager",
                due_date=now + timedelta(hours=4),
                expected_outcome="Payment method updated",
                relevant_links=[
                    "https://billing.system/customer/123",
                    "https://crm.system/customer/123"
                ],
                success_criteria="Payment received within 24 hours",
                priority=Priority.URGENT,
                link="https://crm.system/tasks/123"
            ),
            ActionItem(
                type="review",
                description="Review account health and usage",
                owner_role="customer_success",
                due_date=now + timedelta(days=1),
                expected_outcome="Account health assessment",
                relevant_links=[
                    "https://analytics.system/customer/123"
                ],
                success_criteria="Health check completed and documented",
                priority=Priority.HIGH,
                link="https://analytics.system/tasks/123"
            )
        ]

    def _generate_trial_ending_actions(self, event: Dict[str, Any]) -> List[ActionItem]:
        """Generate actions for trial ending"""
        now = datetime.now()
        return [
            ActionItem(
                type="schedule",
                description="Schedule conversion call",
                owner_role="sales",
                due_date=now + timedelta(days=1),
                expected_outcome="Demo scheduled",
                relevant_links=[
                    "https://calendar.system/schedule"
                ],
                success_criteria="Call scheduled within 2 days",
                priority=Priority.HIGH,
                link="https://calendar.system/tasks/123"
            ),
            ActionItem(
                type="prepare",
                description="Prepare custom success metrics report",
                owner_role="customer_success",
                due_date=now + timedelta(days=1),
                expected_outcome="ROI report",
                relevant_links=[
                    "https://analytics.system/reports"
                ],
                success_criteria="Report shared with customer",
                priority=Priority.MEDIUM,
                link="https://analytics.system/tasks/123"
            )
        ]

    def _generate_cancellation_actions(self, event: Dict[str, Any]) -> List[ActionItem]:
        """Generate actions for subscription cancellation"""
        now = datetime.now()
        return [
            ActionItem(
                type="interview",
                description="Conduct exit interview",
                owner_role="customer_success",
                due_date=now + timedelta(days=1),
                expected_outcome="Feedback collected",
                relevant_links=[
                    "https://forms.system/exit-interview"
                ],
                success_criteria="Interview completed and documented",
                priority=Priority.HIGH,
                link="https://forms.system/tasks/123"
            ),
            ActionItem(
                type="analyze",
                description="Analyze churn factors",
                owner_role="product",
                due_date=now + timedelta(days=7),
                expected_outcome="Churn analysis report",
                relevant_links=[
                    "https://analytics.system/churn"
                ],
                success_criteria="Analysis shared with product team",
                priority=Priority.MEDIUM,
                link="https://analytics.system/tasks/123"
            )
        ]