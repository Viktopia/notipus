import logging
from typing import Any, Dict

from core.models import Organization

logger = logging.getLogger(__name__)


class BillingService:
    """Service for handling billing-related webhook events"""

    @staticmethod
    def handle_subscription_created(subscription: Dict[str, Any]) -> None:
        """Handle subscription created event"""
        try:
            customer_id = subscription.get("customer")
            if not customer_id:
                logger.error("Missing customer ID in subscription data")
                return

            plan_id = (
                subscription.get("items", {})
                .get("data", [{}])[0]
                .get("plan", {})
                .get("id")
            )
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
    def handle_payment_success(invoice: Dict[str, Any]) -> None:
        """Handle successful payment event"""
        try:
            customer_id = invoice.get("customer")
            if not customer_id:
                logger.error("Missing customer ID in invoice data")
                return

            subscription_id = invoice.get("subscription")
            amount_paid = invoice.get("amount_paid", 0)

            updated_count = Organization.objects.filter(
                stripe_customer_id=customer_id
            ).update(subscription_status="active")

            if updated_count > 0:
                logger.info(
                    f"Payment successful for customer {customer_id}, "
                    f"amount: {amount_paid/100:.2f}, subscription: {subscription_id}"
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

            subscription_id = invoice.get("subscription")
            attempt_count = invoice.get("attempt_count", 0)

            updated_count = Organization.objects.filter(
                stripe_customer_id=customer_id
            ).update(subscription_status="past_due")

            if updated_count > 0:
                logger.warning(
                    f"Payment failed for customer {customer_id}, "
                    f"attempt: {attempt_count}, subscription: {subscription_id}"
                )
            else:
                logger.warning(f"No organization found for customer {customer_id}")

        except Exception as e:
            logger.error(f"Error handling payment failure: {str(e)}")
