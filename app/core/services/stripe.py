import logging
from typing import Any, Dict, Optional

import stripe
from django.conf import settings

logger = logging.getLogger(__name__)


class StripeAPI:
    """API client for Stripe operations using the official Stripe SDK"""

    def __init__(self):
        """Initialize the Stripe client with the secret key"""
        # Configure Stripe with the secret key
        stripe.api_key = settings.STRIPE_SECRET_KEY

    @staticmethod
    def create_stripe_customer(
        customer_data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Create Stripe customer using the Stripe SDK"""
        try:
            # Configure Stripe API key for this operation
            stripe.api_key = settings.STRIPE_SECRET_KEY

            # Use Stripe SDK to create customer
            customer = stripe.Customer.create(**customer_data)
            return customer.to_dict()
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error creating customer: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error creating Stripe customer: {str(e)}")
            return None
