from core.models import Organization


class BillingService:
    @staticmethod
    def handle_subscription_created(subscription: dict):
        Organization.objects.filter(stripe_customer_id=subscription["customer"]).update(
            subscription_plan=subscription["items"]["data"][0]["plan"]["id"],
            subscription_status="active",
            billing_cycle_anchor=subscription["current_period_start"],
        )

    @staticmethod
    def handle_payment_success(invoice: dict):
        Organization.objects.filter(stripe_customer_id=invoice["customer"]).update(
            subscription_status="active", billing_cycle_anchor=invoice["period_end"]
        )

    @staticmethod
    def handle_payment_failed(invoice: dict):
        Organization.objects.filter(stripe_customer_id=invoice["customer"]).update(
            subscription_status="past_due"
        )
