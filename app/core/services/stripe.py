import json

import requests
from django.conf import settings
from requests.exceptions import RequestException


class StripeAPI:
    @staticmethod
    def create_stripe_customer(customer_data):
        """Create Stripe customer"""
        try:
            response = requests.post(
                "https://api.stripe.com/v1/customers",
                headers={"Authorization": f"Bearer {settings.STRIPE_SECRET_KEY}"},
                data=json.dumps(customer_data),
            )
            response.raise_for_status()
            return response.json()
        except RequestException as e:
            print(f"Error fetching Stripe customer data: {e}")
            return None
