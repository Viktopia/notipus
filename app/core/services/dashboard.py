"""Dashboard service for handling dashboard data aggregation and processing.

This module provides services for preparing dashboard, billing, and
integration overview data for the application frontend.
"""

import logging
from datetime import datetime
from typing import Any

from core.models import Integration, Organization, Plan, UserProfile
from django.contrib.auth.models import User
from django.db.models import QuerySet
from django.utils import timezone
from webhooks.services.database_lookup import DatabaseLookupService
from webhooks.services.rate_limiter import rate_limiter

logger = logging.getLogger(__name__)


class DashboardService:
    """Service class for dashboard data preparation and business logic.

    Aggregates data from various sources to prepare dashboard displays.
    """

    def __init__(self) -> None:
        """Initialize the dashboard service with dependencies."""
        self.db_service = DatabaseLookupService()

    def get_dashboard_data(self, user: User) -> dict[str, Any] | None:
        """Get all dashboard data for a user.

        Args:
            user: Django User instance.

        Returns:
            Dict with dashboard data or None if user has no profile.
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

    def _get_integration_data(self, organization: Organization) -> dict[str, Any]:
        """Get integration status and data for the organization.

        Args:
            organization: Organization model instance.

        Returns:
            Dictionary with integration status flags.
        """
        integrations: QuerySet[Integration] = Integration.objects.filter(
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

    def _get_recent_activity(self, organization: Organization) -> list[dict[str, Any]]:
        """Get and process recent webhook activity for the organization.

        Args:
            organization: Organization model instance.

        Returns:
            List of recent activity records.
        """
        try:
            recent_activity_raw = self.db_service.get_recent_webhook_activity(
                days=7, limit=15
            )
            return self._transform_activity_data(recent_activity_raw)
        except Exception as e:
            logger.warning(f"Error getting recent activity: {e!s}")
            return []

    def _transform_activity_data(
        self, raw_activity: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Transform raw Redis activity data to dashboard format.

        Args:
            raw_activity: List of raw activity records from Redis.

        Returns:
            List of transformed activity records.
        """
        recent_activity: list[dict[str, Any]] = []

        for record in raw_activity:
            try:
                # Parse timestamp
                if "timestamp" in record:
                    timestamp = datetime.fromtimestamp(
                        record["timestamp"], tz=timezone.get_current_timezone()
                    )
                else:
                    timestamp = timezone.now()

                activity_item: dict[str, Any] = {
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
                logger.warning(f"Error processing webhook activity record: {e!s}")
                continue

        return recent_activity

    def _get_usage_data(self, organization: Organization) -> dict[str, Any]:
        """Get rate limiting and usage statistics for the organization.

        Args:
            organization: Organization model instance.

        Returns:
            Dictionary with usage data and rate limit info.
        """
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
            logger.error(f"Error getting usage data: {e!s}")
            return {
                "is_allowed": True,
                "rate_limit_info": {},
                "usage_stats": {},
                "usage_percentage": 0,
            }

    def _get_trial_info(self, organization: Organization) -> dict[str, Any]:
        """Get trial information for the organization.

        Args:
            organization: Organization model instance.

        Returns:
            Dictionary with trial status and remaining days.
        """
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
    """Service class for billing-related operations.

    Provides methods for retrieving plan information and
    billing dashboard data, with Stripe as the source of truth.
    """

    def get_available_plans(
        self, current_plan: str, use_stripe: bool = True
    ) -> list[dict[str, Any]]:
        """Get available plans for upgrade, excluding current plan.

        Fetches plans from Stripe if available, falls back to local database.

        Args:
            current_plan: Name of the current subscription plan.
            use_stripe: Whether to fetch from Stripe (default True).

        Returns:
            List of available plan dictionaries.
        """
        if use_stripe:
            plans = self._get_plans_from_stripe(current_plan)
            if plans:
                return plans

        # Fall back to local database
        return self._get_plans_from_database(current_plan)

    def _get_plans_from_stripe(self, current_plan: str) -> list[dict[str, Any]]:
        """Fetch available plans from Stripe.

        Args:
            current_plan: Name of the current subscription plan to exclude.

        Returns:
            List of plan dictionaries from Stripe, or empty list on failure.
        """
        try:
            from core.services.stripe import StripeAPI

            stripe_api = StripeAPI()
            prices = stripe_api.list_prices(active_only=True)

            # Filter to monthly recurring prices and exclude current plan
            plans = []
            for price in prices:
                if not price.get("recurring"):
                    continue
                if price["recurring"].get("interval") != "month":
                    continue

                # Get plan name from metadata or product name
                metadata = price.get("metadata", {})
                plan_name = metadata.get("plan_name", "").lower()

                # Skip current plan
                if plan_name == current_plan:
                    continue

                # Skip trial plans
                if plan_name == "trial" or price.get("unit_amount", 0) == 0:
                    continue

                price_amount = (price.get("unit_amount", 0) or 0) / 100
                # Format price as integer if it's a whole number (e.g., 29 not 29.0)
                is_whole_number = price_amount == int(price_amount)
                formatted_price = int(price_amount) if is_whole_number else price_amount
                plans.append(
                    {
                        "id": plan_name or price["product_id"],
                        "name": price.get("product_name", "Unknown Plan"),
                        "description": price.get("product_description", ""),
                        "price": formatted_price,
                        "currency": price.get("currency", "usd").upper(),
                        "interval": "month",
                        "features": price.get("features", []),
                        "stripe_price_id": price["id"],
                        "recommended": plan_name == "pro",
                    }
                )

            return plans

        except Exception as e:
            logger.warning(f"Error fetching plans from Stripe: {e!s}")
            return []

    def _get_plans_from_database(self, current_plan: str) -> list[dict[str, Any]]:
        """Fetch available plans from local database.

        Args:
            current_plan: Name of the current subscription plan to exclude.

        Returns:
            List of plan dictionaries from database.
        """
        try:
            # Exclude current plan and free/trial plans (upgrade is for paid plans)
            plans = Plan.objects.filter(is_active=True).exclude(
                name__in=[current_plan, "free", "trial"]
            )
            result = []
            for plan in plans:
                price = float(plan.price_monthly)
                result.append(
                    {
                        "id": plan.name,
                        "name": plan.display_name,
                        "description": plan.description,
                        "price": int(price) if price == int(price) else price,
                        "currency": "USD",
                        "interval": "month",
                        "features": plan.features,
                        "stripe_price_id": plan.stripe_price_id_monthly,
                        "recommended": plan.name == "pro",
                    }
                )
            return result
        except Exception as e:
            logger.error(f"Error getting plans from database: {e!s}")
            return []

    def get_stripe_subscription_info(
        self, organization: Organization
    ) -> dict[str, Any] | None:
        """Get current subscription info from Stripe.

        Args:
            organization: Organization model instance.

        Returns:
            Subscription info dictionary or None if not found.
        """
        if not organization.stripe_customer_id:
            return None

        try:
            from core.services.stripe import StripeAPI

            stripe_api = StripeAPI()
            subscriptions = stripe_api.get_customer_subscriptions(
                organization.stripe_customer_id, status="active"
            )

            if not subscriptions:
                return None

            # Return the first active subscription
            sub = subscriptions[0]
            return {
                "id": sub["id"],
                "status": sub["status"],
                "current_period_end": sub.get("current_period_end"),
                "cancel_at_period_end": sub.get("cancel_at_period_end", False),
                "items": sub.get("items", []),
            }

        except Exception as e:
            logger.warning(f"Error fetching subscription from Stripe: {e!s}")
            return None

    def get_billing_dashboard_data(self, organization: Organization) -> dict[str, Any]:
        """Get billing dashboard data for an organization.

        Includes real-time data from Stripe when available.

        Args:
            organization: Organization model instance.

        Returns:
            Dictionary with billing dashboard information.
        """
        dashboard_service = DashboardService()
        usage_data = dashboard_service._get_usage_data(organization)
        trial_info = dashboard_service._get_trial_info(organization)

        # Get Stripe subscription info if available
        stripe_subscription = self.get_stripe_subscription_info(organization)

        return {
            "organization": organization,
            "usage_data": usage_data,
            "trial_info": trial_info,
            "available_plans": self.get_available_plans(organization.subscription_plan),
            "current_plan": organization.subscription_plan,
            "stripe_subscription": stripe_subscription,
        }


class IntegrationService:
    """Service class for integration-related operations.

    Provides methods for retrieving integration status and
    overview data.
    """

    def get_integration_overview(self, organization: Organization) -> dict[str, Any]:
        """Get integration overview data for the integrations page.

        Args:
            organization: Organization model instance.

        Returns:
            Dictionary with integration sources and destinations.
        """
        current_integrations: QuerySet[Integration] = Integration.objects.filter(
            organization=organization, is_active=True
        )

        # Event Sources - Services that send webhooks TO Notipus
        event_sources: list[dict[str, Any]] = [
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
                    "Subscription billing events (renewals, cancellations, upgrades)"
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
                    "Customer payment events (successful payments, failed charges)"
                ),
                "connected": current_integrations.filter(
                    integration_type="stripe_customer"
                ).exists(),
                "category": "Payments",
            },
        ]

        # Notification Destinations - Services that receive notifications FROM Notipus
        notification_destinations: list[dict[str, Any]] = [
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
            "notification_channels": notification_destinations,
            "current_integrations": current_integrations,
        }
