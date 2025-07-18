import logging

from core.models import Organization

logger = logging.getLogger(__name__)


class BillingService:
    @staticmethod
    def handle_subscription_created(subscription: dict):
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
    def handle_payment_success(invoice: dict):
        """Handle successful payment event"""
        try:
            customer_id = invoice.get("customer")
            if not customer_id:
                logger.error("Missing customer ID in invoice data")
                return

            updated_count = Organization.objects.filter(
                stripe_customer_id=customer_id
            ).update(
                subscription_status="active",
                billing_cycle_anchor=invoice.get("period_end"),
            )

            if updated_count > 0:
                logger.info(
                    f"Updated payment status to active for customer {customer_id}"
                )
            else:
                logger.warning(f"No organization found for customer {customer_id}")

        except Exception as e:
            logger.error(f"Error handling payment success: {str(e)}")

    @staticmethod
    def handle_payment_failed(invoice: dict):
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
