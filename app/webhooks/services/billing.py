"""Billing service for handling Stripe webhook events.

This module processes billing-related webhook events from Stripe
and updates organization subscription status accordingly.
"""

import logging
from typing import Any

from core.models import Organization

logger = logging.getLogger(__name__)


class BillingService:
    """Service for handling billing-related webhook events from Stripe.

    Provides static methods for processing various subscription and
    payment events and updating organization records.
    """

    @staticmethod
    def _get_customer_id(data: dict[str, Any], data_type: str) -> str | None:
        """Extract customer ID from webhook data.

        Args:
            data: Webhook data dictionary.
            data_type: Description of data type for logging.

        Returns:
            Customer ID string, or None if not found.
        """
        customer_id = data.get("customer")
        if not customer_id:
            logger.error(f"Missing customer ID in {data_type} data")
            return None
        return customer_id

    @staticmethod
    def _extract_plan_id(subscription: dict[str, Any]) -> str | None:
        """Extract plan ID from subscription data.

        Handles multiple Stripe API formats (nested and direct).

        Args:
            subscription: Subscription data dictionary.

        Returns:
            Plan ID string, or None if not found.
        """
        # Try the nested items.data[0].plan.id format (Stripe API 2020-08-27 and later)
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
    def handle_subscription_created(subscription: dict[str, Any]) -> None:
        """Handle subscription created event.

        Args:
            subscription: Subscription data from Stripe webhook.
        """
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
            logger.error(f"Error handling subscription created: {e!s}")

    @staticmethod
    def handle_subscription_updated(subscription: dict[str, Any]) -> None:
        """Handle subscription updated event (plan changes, status changes).

        Args:
            subscription: Subscription data from Stripe webhook.
        """
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

            update_data: dict[str, Any] = {"subscription_status": internal_status}

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
            logger.error(f"Error handling subscription updated: {e!s}")

    @staticmethod
    def handle_subscription_deleted(subscription: dict[str, Any]) -> None:
        """Handle subscription deleted/cancelled event.

        Args:
            subscription: Subscription data from Stripe webhook.
        """
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
            logger.error(f"Error handling subscription deleted: {e!s}")

    @staticmethod
    def handle_payment_success(invoice: dict[str, Any]) -> None:
        """Handle successful payment event.

        Args:
            invoice: Invoice data from Stripe webhook.
        """
        try:
            customer_id = invoice.get("customer")
            if not customer_id:
                logger.error("Missing customer ID in invoice data")
                return

            period_end = invoice.get("period_end")

            # Prepare update data
            update_data: dict[str, Any] = {"subscription_status": "active"}
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
            logger.error(f"Error handling payment success: {e!s}")

    @staticmethod
    def handle_payment_failed(invoice: dict[str, Any]) -> None:
        """Handle failed payment event.

        Args:
            invoice: Invoice data from Stripe webhook.
        """
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
            logger.error(f"Error handling payment failure: {e!s}")

    @staticmethod
    def handle_checkout_completed(session: dict[str, Any]) -> None:
        """Handle checkout.session.completed event.

        This is triggered when a customer completes checkout and the
        subscription is created. Links the subscription to the organization.

        Args:
            session: Checkout session data from Stripe webhook.
        """
        try:
            customer_id = session.get("customer")
            if not customer_id:
                logger.error("Missing customer ID in checkout session")
                return

            # Extract metadata with organization and plan info
            metadata = session.get("metadata", {})
            organization_id = metadata.get("organization_id")
            plan_name = metadata.get("plan_name")

            subscription_id = session.get("subscription")

            # Update organization with new subscription status
            update_data: dict[str, Any] = {
                "subscription_status": "active",
                "payment_method_added": True,
            }

            if plan_name:
                update_data["subscription_plan"] = plan_name

            # Find organization by customer ID or organization ID from metadata
            if organization_id:
                updated_count = Organization.objects.filter(id=organization_id).update(
                    **update_data
                )
            else:
                updated_count = Organization.objects.filter(
                    stripe_customer_id=customer_id
                ).update(**update_data)

            if updated_count > 0:
                logger.info(
                    f"Checkout completed for customer {customer_id}, "
                    f"subscription: {subscription_id}, plan: {plan_name}"
                )
            else:
                logger.warning(
                    f"No organization found for checkout session. "
                    f"Customer: {customer_id}, Org ID: {organization_id}"
                )

        except Exception as e:
            logger.error(f"Error handling checkout completed: {e!s}")

    @staticmethod
    def handle_trial_ending(subscription: dict[str, Any]) -> None:
        """Handle trial ending notification (3 days before trial ends).

        This event is fired when a subscription's trial is about to end.
        Can be used to send reminder notifications to customers.

        Args:
            subscription: Subscription data from Stripe webhook.
        """
        try:
            customer_id = BillingService._get_customer_id(subscription, "trial ending")
            if not customer_id:
                return

            trial_end = subscription.get("trial_end")

            # Find organization and log the event
            org = Organization.objects.filter(stripe_customer_id=customer_id).first()

            if org:
                logger.info(
                    f"Trial ending soon for organization {org.name} "
                    f"(customer: {customer_id}), trial_end: {trial_end}"
                )
                # TODO: Send notification email to organization admins
                # TODO: Trigger Slack notification if configured
            else:
                logger.warning(f"Trial ending for unknown customer {customer_id}")

        except Exception as e:
            logger.error(f"Error handling trial ending: {e!s}")

    @staticmethod
    def handle_invoice_paid(invoice: dict[str, Any]) -> None:
        """Handle invoice.paid event.

        This confirms that an invoice was paid successfully.
        Similar to payment_success but for invoice-specific events.

        Args:
            invoice: Invoice data from Stripe webhook.
        """
        try:
            customer_id = invoice.get("customer")
            if not customer_id:
                logger.error("Missing customer ID in paid invoice")
                return

            # Mark organization as active with payment method confirmed
            update_data: dict[str, Any] = {
                "subscription_status": "active",
                "payment_method_added": True,
            }

            # Update billing cycle anchor if period_end is present
            period_end = invoice.get("period_end")
            if period_end:
                update_data["billing_cycle_anchor"] = period_end

            updated_count = Organization.objects.filter(
                stripe_customer_id=customer_id
            ).update(**update_data)

            if updated_count > 0:
                logger.info(f"Invoice paid for customer {customer_id}")
            else:
                logger.warning(f"No organization found for paid invoice: {customer_id}")

        except Exception as e:
            logger.error(f"Error handling invoice paid: {e!s}")

    @staticmethod
    def handle_payment_action_required(invoice: dict[str, Any]) -> None:
        """Handle invoice.payment_action_required event.

        This is triggered when a payment requires customer action,
        such as 3D Secure authentication.

        Args:
            invoice: Invoice data from Stripe webhook.
        """
        try:
            customer_id = invoice.get("customer")
            if not customer_id:
                logger.error("Missing customer ID in action required invoice")
                return

            hosted_invoice_url = invoice.get("hosted_invoice_url")

            # Find organization and log the event
            org = Organization.objects.filter(stripe_customer_id=customer_id).first()

            if org:
                logger.warning(
                    f"Payment action required for organization {org.name} "
                    f"(customer: {customer_id}). Invoice URL: {hosted_invoice_url}"
                )
                # TODO: Send notification email to organization admins
                # with link to complete payment
            else:
                logger.warning(
                    f"Payment action required for unknown customer: {customer_id}"
                )

        except Exception as e:
            logger.error(f"Error handling payment action required: {e!s}")
