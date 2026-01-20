import logging
from typing import Any, Dict, Optional

import stripe
from django.conf import settings

logger = logging.getLogger(__name__)


class StripeAPI:
    """API client for Stripe operations using the official Stripe SDK"""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the Stripe client with the secret key.

        Args:
            api_key: Optional Stripe API key. If not provided, uses
                     settings.STRIPE_SECRET_KEY (for Notipus billing).
        """
        self.api_key = api_key or settings.STRIPE_SECRET_KEY
        # Configure Stripe with the secret key
        stripe.api_key = self.api_key

    def get_account_info(self) -> Optional[Dict[str, Any]]:
        """
        Retrieve Stripe account information to verify API key validity.

        Returns:
            Dict with account info if successful, None if API key is invalid.
        """
        try:
            # Temporarily set the API key for this request
            stripe.api_key = self.api_key

            # Retrieve the connected account info
            account = stripe.Account.retrieve()
            return {
                "id": account.id,
                "business_profile": {
                    "name": getattr(account.business_profile, "name", None),
                    "url": getattr(account.business_profile, "url", None),
                }
                if account.business_profile
                else {},
                "email": account.email,
                "country": account.country,
                "default_currency": account.default_currency,
            }
        except stripe.error.AuthenticationError as e:
            logger.warning(f"Invalid Stripe API key: {str(e)}")
            return None
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error retrieving account: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error retrieving Stripe account: {str(e)}")
            return None

    def create_stripe_customer(
        self,
        customer_data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Create Stripe customer using the Stripe SDK"""
        try:
            # Configure Stripe API key for this operation
            stripe.api_key = self.api_key

            # Use Stripe SDK to create customer
            customer = stripe.Customer.create(**customer_data)
            return customer.to_dict()
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error creating customer: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error creating Stripe customer: {str(e)}")
            return None

    @staticmethod
    def create_stripe_customer_static(
        customer_data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Create Stripe customer using the default API key (static method).

        Kept for backward compatibility. Prefer using instance method.
        """
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
