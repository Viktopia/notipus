import json
import logging
from typing import Any, Dict, Optional

import requests
from django.conf import settings
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)


class StripeAPI:
    """API client for Stripe operations"""

    @staticmethod
    def create_stripe_customer(
        customer_data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
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
            logger.error(f"Error creating Stripe customer: {str(e)}")
            return None
