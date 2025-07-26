"""
Enhanced Shopify API service using the official Shopify Python library.

This service provides secure and reliable access to Shopify's Admin API
using the official shopifyapi library with proper session management.

Note: This service requires tenant-specific credentials passed as parameters.
No global Shopify configuration is used to maintain proper multi-tenancy.
"""

import logging
from typing import Dict, Optional

import shopify

logger = logging.getLogger(__name__)


class ShopifyAPI:
    """
    API client for Shopify operations using the official Shopify Python library.

    This class provides secure access to Shopify's Admin API with proper
    session management and error handling. Requires tenant-specific credentials.
    """

    @classmethod
    def _get_session(cls, shop_domain: str, access_token: str) -> shopify.Session:
        """
        Create and configure a Shopify session.

        Args:
            shop_domain: The Shopify shop domain (e.g., 'mystore.myshopify.com')
            access_token: The Shopify access token for API authentication

        Returns:
            shopify.Session: Configured session for API access
        """
        try:
            # Use the latest stable API version
            api_version = "2024-01"
            session = shopify.Session(
                shop_domain=shop_domain,
                api_version=api_version,
                access_token=access_token,
            )
            return session
        except Exception as e:
            logger.error(f"Failed to create Shopify session: {str(e)}")
            raise

    @classmethod
    def get_shop_domain(cls, shop_domain: str, access_token: str) -> Optional[str]:
        """
        Get shop domain from Shopify API using the official library.

        Args:
            shop_domain: The Shopify shop domain
            access_token: The Shopify access token

        Returns:
            Optional[str]: The shop's myshopify domain, or None if failed
        """
        try:
            session = cls._get_session(shop_domain, access_token)

            # Use context manager for proper session handling
            with shopify.Session.temp(
                session.domain, session.api_version, session.token
            ):
                shop = shopify.Shop.current()
                return shop.myshopify_domain if shop else None

        except Exception as e:
            logger.error(f"Error fetching Shopify shop data: {str(e)}")
            return None

    @classmethod
    def get_shop_info(
        cls, shop_domain: str, access_token: str
    ) -> Optional[Dict[str, str]]:
        """
        Get comprehensive shop information from Shopify API.

        Args:
            shop_domain: The Shopify shop domain
            access_token: The Shopify access token

        Returns:
            Optional[Dict[str, str]]: Shop information dictionary, or None if failed
        """
        try:
            session = cls._get_session(shop_domain, access_token)

            with shopify.Session.temp(
                session.domain, session.api_version, session.token
            ):
                shop = shopify.Shop.current()
                if not shop:
                    return None

                return {
                    "id": str(shop.id),
                    "name": shop.name,
                    "email": shop.email,
                    "domain": shop.domain,
                    "myshopify_domain": shop.myshopify_domain,
                    "plan_name": shop.plan_name,
                    "currency": shop.currency,
                    "timezone": shop.timezone,
                    "country_name": shop.country_name,
                    "created_at": shop.created_at,
                }

        except Exception as e:
            logger.error(f"Error fetching Shopify shop info: {str(e)}")
            return None

    @classmethod
    def get_customer(
        cls, customer_id: str, shop_domain: str, access_token: str
    ) -> Optional[Dict]:
        """
        Retrieve customer information by ID.

        Args:
            customer_id (str): Shopify customer ID
            shop_domain: The Shopify shop domain
            access_token: The Shopify access token

        Returns:
            Optional[Dict]: Customer data dictionary, or None if not found
        """
        try:
            session = cls._get_session(shop_domain, access_token)

            with shopify.Session.temp(
                session.domain, session.api_version, session.token
            ):
                customer = shopify.Customer.find(customer_id)
                if not customer:
                    return None

                return {
                    "id": str(customer.id),
                    "email": customer.email,
                    "first_name": customer.first_name,
                    "last_name": customer.last_name,
                    "company": getattr(customer, "company", ""),
                    "orders_count": customer.orders_count,
                    "total_spent": customer.total_spent,
                    "created_at": customer.created_at,
                    "updated_at": customer.updated_at,
                    "state": customer.state,
                    "note": getattr(customer, "note", ""),
                    "tags": getattr(customer, "tags", ""),
                }

        except Exception as e:
            logger.error(f"Error fetching customer {customer_id}: {str(e)}")
            return None

    @classmethod
    def get_order(
        cls, order_id: str, shop_domain: str, access_token: str
    ) -> Optional[Dict]:
        """
        Retrieve order information by ID.

        Args:
            order_id (str): Shopify order ID
            shop_domain: The Shopify shop domain
            access_token: The Shopify access token

        Returns:
            Optional[Dict]: Order data dictionary, or None if not found
        """
        try:
            session = cls._get_session(shop_domain, access_token)

            with shopify.Session.temp(
                session.domain, session.api_version, session.token
            ):
                order = shopify.Order.find(order_id)
                if not order:
                    return None

                return {
                    "id": str(order.id),
                    "order_number": order.order_number,
                    "email": order.email,
                    "total_price": order.total_price,
                    "subtotal_price": order.subtotal_price,
                    "total_tax": order.total_tax,
                    "currency": order.currency,
                    "financial_status": order.financial_status,
                    "fulfillment_status": order.fulfillment_status,
                    "created_at": order.created_at,
                    "updated_at": order.updated_at,
                    "customer_id": str(order.customer.id) if order.customer else None,
                }

        except Exception as e:
            logger.error(f"Error fetching order {order_id}: {str(e)}")
            return None
