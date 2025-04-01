import hmac
import hashlib
from django.http import HttpRequest
from django.conf import settings
from core.models import Organization


class StripeProvider:
    def __init__(self):
        self.webhook_secret = settings.STRIPE_WEBHOOK_SECRET

    def validate_webhook(self, request: HttpRequest) -> bool:
        signature = request.headers.get('Stripe-Signature')
        payload = request.body
        secret = self.webhook_secret.encode()

        try:
            timestamp, signatures = signature.split(',')
            expected_sig = hmac.new(secret, f"{timestamp}.{payload.decode()}".encode(), hashlib.sha256).hexdigest()
            return any(sig.strip() == f"v1={expected_sig}" for sig in signatures.split(','))
        except:
            return False

    def process_event(self, payload: dict):
        event_type = payload['type']
        data = payload['data']['object']

        if event_type == 'customer.subscription.created':
            self._handle_subscription_created(data)
        elif event_type == 'invoice.paid':
            self._handle_invoice_paid(data)
        elif event_type == 'invoice.payment_failed':
            self._handle_payment_failed(data)

    def _handle_subscription_created(self, subscription: dict):
        Organization.objects.filter(stripe_customer_id=subscription['customer']).update(
            subscription_plan=subscription['items']['data'][0]['plan']['id'],
            subscription_status='active',
            billing_cycle_anchor=subscription['current_period_start']
        )

    def _handle_invoice_paid(self, invoice: dict):
        Organization.objects.filter(stripe_customer_id=invoice['customer']).update(
            subscription_status='active',
            billing_cycle_anchor=invoice['period_end']
        )

    def _handle_payment_failed(self, invoice: dict):
        Organization.objects.filter(stripe_customer_id=invoice['customer']).update(
            subscription_status='past_due'
        )
