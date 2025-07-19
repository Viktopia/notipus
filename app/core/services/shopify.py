import logging
from typing import Optional

import requests
from django.conf import settings
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)


class ShopifyAPI:
    """API client for Shopify operations"""

    @staticmethod
    def get_shop_domain() -> Optional[str]:
        """Get shop domain from Shopify API"""
        try:
            headers = {
                "X-Shopify-Access-Token": settings.SHOPIFY_ACCESS_TOKEN,
                "Content-Type": "application/json",
            }
            response = requests.get(
                f"https://{settings.SHOPIFY_SHOP_URL}/admin/api/2023-07/shop.json",
                headers=headers,
            )
            response.raise_for_status()
            shop_data = response.json().get("shop", {})
            return shop_data.get("myshopify_domain")
        except RequestException as e:
            logger.error(f"Error fetching Shopify shop data: {str(e)}")
            return None
