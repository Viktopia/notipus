"""Dashboard service for handling dashboard data aggregation and processing."""

import logging
from datetime import datetime
from typing import Dict, List, Optional

from core.models import Integration, Organization, UserProfile
from django.utils import timezone
from webhooks.services.database_lookup import DatabaseLookupService
from webhooks.services.rate_limiter import rate_limiter

logger = logging.getLogger(__name__)


class DashboardService:
    """Service class for dashboard data preparation and business logic."""

    def __init__(self):
        self.db_service = DatabaseLookupService()

    def get_dashboard_data(self, user) -> Optional[Dict]:
        """
        Get all dashboard data for a user.

        Args:
            user: Django User instance

        Returns:
            Dict with dashboard data or None if user has no profile
        """
        try:
            user_profile = UserProfile.objects.get(user=user)
            organization = user_profile.organization
        except UserProfile.DoesNotExist:
            return None

        return {
            "organization": organization,
            "user_profile": user_profile,
            "integrations": self._get_integration_data(organization),
            "recent_activity": self._get_recent_activity(organization),
            "usage_data": self._get_usage_data(organization),
            "trial_info": self._get_trial_info(organization),
        }

    def _get_integration_data(self, organization: Organization) -> Dict:
        """Get integration status and data for the organization."""
        integrations = Integration.objects.filter(
            organization=organization, is_active=True
        )

        return {
            "integrations": integrations,
            "has_slack": integrations.filter(
                integration_type="slack_notifications"
            ).exists(),
            "has_shopify": integrations.filter(integration_type="shopify").exists(),
            "has_chargify": integrations.filter(integration_type="chargify").exists(),
            "has_stripe": integrations.filter(
                integration_type="stripe_customer"
            ).exists(),
        }

    def _get_recent_activity(self, organization: Organization) -> List[Dict]:
        """Get and process recent webhook activity for the organization."""
        try:
            recent_activity_raw = self.db_service.get_recent_webhook_activity(
                days=7, limit=15
            )
            return self._transform_activity_data(recent_activity_raw)
        except Exception as e:
            logger.warning(f"Error getting recent activity: {str(e)}")
            return []

    def _transform_activity_data(self, raw_activity: List[Dict]) -> List[Dict]:
        """Transform raw Redis activity data to dashboard format."""
        recent_activity = []

        for record in raw_activity:
            try:
                # Parse timestamp
                if "timestamp" in record:
                    timestamp = datetime.fromtimestamp(
                        record["timestamp"], tz=timezone.get_current_timezone()
                    )
                else:
                    timestamp = timezone.now()

                activity_item = {
                    "type": record.get("type"),
                    "provider": record.get("provider"),
                    "status": record.get("status"),
                    "amount": record.get("amount"),
                    "currency": record.get("currency"),
                    "timestamp": timestamp,
                    "external_id": record.get("external_id"),
                    "customer_id": record.get("customer_id"),
                }

                # Add type-specific fields
                if record.get("type") == "order":
                    activity_item["order_number"] = record.get("order_number", "")

                recent_activity.append(activity_item)

            except Exception as e:
                logger.warning(f"Error processing webhook activity record: {str(e)}")
                continue

        return recent_activity

    def _get_usage_data(self, organization: Organization) -> Dict:
        """Get rate limiting and usage statistics for the organization."""
        try:
            # Get rate limit info and usage stats
            is_allowed, rate_limit_info = rate_limiter.check_rate_limit(organization)
            usage_stats = rate_limiter.get_usage_stats(organization, months=3)

            # Calculate usage percentage
            current_usage = rate_limit_info.get("current_usage", 0)
            limit = rate_limit_info.get("limit", 1000)
            usage_percentage = (current_usage / limit * 100) if limit > 0 else 0

            return {
                "is_allowed": is_allowed,
                "rate_limit_info": rate_limit_info,
                "usage_stats": usage_stats,
                "usage_percentage": min(usage_percentage, 100),  # Cap at 100%
            }
        except Exception as e:
            logger.error(f"Error getting usage data: {str(e)}")
            return {
                "is_allowed": True,
                "rate_limit_info": {},
                "usage_stats": {},
                "usage_percentage": 0,
            }

    def _get_trial_info(self, organization: Organization) -> Dict:
        """Get trial information for the organization."""
        trial_days_remaining = 0
        is_trial = organization.subscription_status == "trial"

        if is_trial and organization.trial_end_date:
            trial_days_remaining = max(
                0, (organization.trial_end_date - timezone.now()).days
            )

        return {
            "is_trial": is_trial,
            "trial_days_remaining": trial_days_remaining,
            "trial_end_date": organization.trial_end_date,
        }


class BillingService:
    """Service class for billing-related operations."""

    def get_available_plans(self, current_plan: str) -> List[Dict]:
        """Get available plans for upgrade, excluding current plan."""
        from core.models import Plan

        try:
            plans = Plan.objects.filter(is_active=True).exclude(name=current_plan)
            return [
                {
                    "id": plan.name,
                    "name": plan.display_name,
                    "description": plan.description,
                    "price": float(plan.price_monthly),
                    "currency": "USD",
                    "interval": "month",
                    "features": plan.features,
                    "stripe_price_id": plan.stripe_price_id_monthly,
                    "recommended": plan.name == "pro",  # Mark pro as recommended
                }
                for plan in plans
            ]
        except Exception as e:
            logger.error(f"Error getting available plans: {str(e)}")
            return []

    def get_billing_dashboard_data(self, organization: Organization) -> Dict:
        """Get billing dashboard data for an organization."""
        from core.services.dashboard import DashboardService

        dashboard_service = DashboardService()
        usage_data = dashboard_service._get_usage_data(organization)
        trial_info = dashboard_service._get_trial_info(organization)

        return {
            "organization": organization,
            "usage_data": usage_data,
            "trial_info": trial_info,
            "available_plans": self.get_available_plans(organization.subscription_plan),
            "current_plan": organization.subscription_plan,
        }


class IntegrationService:
    """Service class for integration-related operations."""

    def get_integration_overview(self, organization: Organization) -> Dict:
        """Get integration overview data for the integrations page."""
        current_integrations = Integration.objects.filter(
            organization=organization, is_active=True
        )

        # Event Sources - Services that send webhooks TO Notipus
        event_sources = [
            {
                "id": "shopify",
                "name": "Shopify",
                "description": (
                    "E-commerce events from your Shopify store "
                    "(orders, payments, customers)"
                ),
                "connected": current_integrations.filter(
                    integration_type="shopify"
                ).exists(),
                "category": "E-commerce",
            },
            {
                "id": "chargify",
                "name": "Chargify / Maxio Advanced Billing",
                "description": (
                    "Subscription billing events "
                    "(renewals, cancellations, upgrades)"
                ),
                "connected": current_integrations.filter(
                    integration_type="chargify"
                ).exists(),
                "category": "Billing",
            },
            {
                "id": "stripe_customer",
                "name": "Stripe Payments",
                "description": (
                    "Customer payment events "
                    "(successful payments, failed charges)"
                ),
                "connected": current_integrations.filter(
                    integration_type="stripe_customer"
                ).exists(),
                "category": "Payments",
            },
        ]

        # Notification Destinations - Services that receive notifications FROM Notipus
        notification_destinations = [
            {
                "id": "slack_notifications",
                "name": "Slack",
                "description": (
                    "Real-time notifications sent to your team's Slack workspace"
                ),
                "connected": current_integrations.filter(
                    integration_type="slack_notifications"
                ).exists(),
                "category": "Team Communication",
            },
        ]

        return {
            "organization": organization,
            "event_sources": event_sources,
            "notification_destinations": notification_destinations,
            "current_integrations": current_integrations,
        }
