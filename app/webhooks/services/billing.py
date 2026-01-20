import logging
from typing import Any, Dict, Optional

from core.models import Organization

logger = logging.getLogger(__name__)


class BillingService:
    """Service for handling billing-related webhook events from Stripe"""

    @staticmethod
    def _get_customer_id(data: Dict[str, Any], data_type: str) -> Optional[str]:
        """Extract customer ID from webhook data."""
        customer_id = data.get("customer")
        if not customer_id:
            logger.error(f"Missing customer ID in {data_type} data")
            return None
        return customer_id

    @staticmethod
    def _extract_plan_id(subscription: Dict[str, Any]) -> Optional[str]:
        """
        Extract plan ID from subscription data.

        Handles multiple Stripe API formats (nested and direct).
        """
        # Try the nested items.data[0].plan.id format (Stripe API >= 2020)
        items = subscription.get("items", {})
        if isinstance(items, dict):
            data_list = items.get("data", [])
            if data_list and isinstance(data_list, list):
                first_item = data_list[0] if data_list else {}
                plan = first_item.get("plan", {})
                if isinstance(plan, dict) and plan.get("id"):
                    return plan.get("id")

        # Try direct plan.id format (older format)
        plan = subscription.get("plan", {})
        if isinstance(plan, dict) and plan.get("id"):
            return plan.get("id")

        return None

    @staticmethod
    def handle_subscription_created(subscription: Dict[str, Any]) -> None:
        """Handle subscription created event"""
        try:
            customer_id = BillingService._get_customer_id(subscription, "subscription")
            if not customer_id:
                return

            plan_id = BillingService._extract_plan_id(subscription)
            if not plan_id:
                logger.error(
                    f"Missing plan ID in subscription data for customer {customer_id}"
                )
                return

            updated_count = Organization.objects.filter(
                stripe_customer_id=customer_id
            ).update(
                subscription_plan=plan_id,
                subscription_status="active",
                billing_cycle_anchor=subscription.get("current_period_start"),
            )

            if updated_count > 0:
                logger.info(
                    f"Updated subscription for customer {customer_id} to plan {plan_id}"
                )
            else:
                logger.warning(f"No organization found for customer {customer_id}")

        except Exception as e:
            logger.error(f"Error handling subscription created: {str(e)}")

    @staticmethod
    def handle_subscription_updated(subscription: Dict[str, Any]) -> None:
        """Handle subscription updated event (plan changes, status changes)"""
        try:
            customer_id = BillingService._get_customer_id(subscription, "subscription")
            if not customer_id:
                return

            # Extract subscription status
            status = subscription.get("status", "active")

            # Map Stripe statuses to our internal statuses
            status_mapping = {
                "active": "active",
                "trialing": "trial",
                "past_due": "past_due",
                "canceled": "cancelled",
                "unpaid": "past_due",
                "incomplete": "trial",
                "incomplete_expired": "cancelled",
            }
            internal_status = status_mapping.get(status, "active")

            update_data = {"subscription_status": internal_status}

            # Update plan if changed
            plan_id = BillingService._extract_plan_id(subscription)
            if plan_id:
                update_data["subscription_plan"] = plan_id

            # Update billing cycle anchor if present
            if subscription.get("current_period_end"):
                update_data["billing_cycle_anchor"] = subscription.get(
                    "current_period_end"
                )

            updated_count = Organization.objects.filter(
                stripe_customer_id=customer_id
            ).update(**update_data)

            if updated_count > 0:
                logger.info(
                    f"Updated subscription status to {internal_status} "
                    f"for customer {customer_id}"
                )
            else:
                logger.warning(f"No organization found for customer {customer_id}")

        except Exception as e:
            logger.error(f"Error handling subscription updated: {str(e)}")

    @staticmethod
    def handle_subscription_deleted(subscription: Dict[str, Any]) -> None:
        """Handle subscription deleted/cancelled event"""
        try:
            customer_id = BillingService._get_customer_id(subscription, "subscription")
            if not customer_id:
                return

            updated_count = Organization.objects.filter(
                stripe_customer_id=customer_id
            ).update(subscription_status="cancelled")

            if updated_count > 0:
                logger.info(
                    f"Marked subscription as cancelled for customer {customer_id}"
                )
            else:
                logger.warning(f"No organization found for customer {customer_id}")

        except Exception as e:
            logger.error(f"Error handling subscription deleted: {str(e)}")

    @staticmethod
    def handle_payment_success(invoice: Dict[str, Any]) -> None:
        """Handle successful payment event"""
        try:
            customer_id = invoice.get("customer")
            if not customer_id:
                logger.error("Missing customer ID in invoice data")
                return

            period_end = invoice.get("period_end")

            # Prepare update data
            update_data = {"subscription_status": "active"}
            if period_end:
                update_data["billing_cycle_anchor"] = period_end

            updated_count = Organization.objects.filter(
                stripe_customer_id=customer_id
            ).update(**update_data)

            if updated_count > 0:
                logger.info(
                    f"Updated payment status to active for customer {customer_id}"
                )
            else:
                logger.warning(f"No organization found for customer {customer_id}")

        except Exception as e:
            logger.error(f"Error handling payment success: {str(e)}")

    @staticmethod
    def handle_payment_failed(invoice: Dict[str, Any]) -> None:
        """Handle failed payment event"""
        try:
            customer_id = invoice.get("customer")
            if not customer_id:
                logger.error("Missing customer ID in invoice data")
                return

            updated_count = Organization.objects.filter(
                stripe_customer_id=customer_id
            ).update(subscription_status="past_due")

            if updated_count > 0:
                logger.warning(
                    f"Updated payment status to past_due for customer {customer_id}"
                )
            else:
                logger.warning(f"No organization found for customer {customer_id}")

        except Exception as e:
            logger.error(f"Error handling payment failure: {str(e)}")
