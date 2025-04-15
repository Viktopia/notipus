import requests
from django.conf import settings
from requests.exceptions import RequestException


class ShopifyAPI:
    @staticmethod
    def get_shop_domain():
        """Get shop_domain from Shopify API"""
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
            return response.json().get("shop", {}).get("myshopify_domain")
        except RequestException as e:
            print(f"Error fetching Shopify shop data: {e}")
            return None
