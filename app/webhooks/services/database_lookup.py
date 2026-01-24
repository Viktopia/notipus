"""Database lookup service for webhook records.

This module provides services for storing and retrieving webhook
records in Redis with TTL-based expiration.
"""

import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)


class DatabaseLookupService:
    """Service for managing webhook records in Redis with TTL.

    Stores payment and order records with automatic expiration and
    provides lookup capabilities for cross-referencing events.

    Attributes:
        lookup_window_hours: Hours to look back for matches.
        ttl_seconds: Time-to-live for webhook records.
    """

    def __init__(self) -> None:
        """Initialize the database lookup service."""
        self.lookup_window_hours = 24  # Look for matches within 24 hours
        self.ttl_seconds = 60 * 60 * 24  # 24 hours TTL for webhook records

    def _get_webhook_key(self, webhook_type: str, timestamp: str) -> str:
        """Generate Redis key for webhook record.

        Args:
            webhook_type: Type of webhook (payment, order, etc.).
            timestamp: Timestamp string for uniqueness.

        Returns:
            Formatted Redis key string.
        """
        return f"webhook:{webhook_type}:{timestamp}"

    def _get_activity_key(self, date_str: str) -> str:
        """Generate Redis key for daily activity list.

        Args:
            date_str: Date string in YYYY-MM-DD format.

        Returns:
            Formatted Redis key for activity list.
        """
        return f"webhook_activity:{date_str}"

    def _normalize_status(self, status: str | None) -> str:
        """Normalize status string for consistent display.

        Args:
            status: Raw status string from event data.

        Returns:
            Normalized status string.
        """
        if not status:
            return "pending"
        status = str(status).lower()
        if status in ["successful", "completed", "paid"]:
            return "success"
        if status in ["declined", "error"]:
            return "failed"
        if status in ["active", "trialing"]:
            return "active"
        if status in ["canceled", "cancelled"]:
            return "cancelled"
        return status

    def _get_event_display_type(self, event_type: str) -> str:
        """Map event type to display category.

        Args:
            event_type: The original event type string.

        Returns:
            Display category for the event.
        """
        type_category_map = {
            "payment_success": "payment",
            "payment_failure": "payment",
            "subscription_created": "subscription",
            "subscription_updated": "subscription",
            "subscription_deleted": "subscription",
            "checkout_completed": "checkout",
            "invoice_paid": "payment",
            "trial_ending": "subscription",
            "payment_action_required": "payment",
        }
        return type_category_map.get(event_type, "payment")

    def store_payment_record(self, event_data: dict[str, Any]) -> bool:
        """Store a payment/subscription record in Redis with TTL.

        Handles all event types including payments, subscriptions, and checkouts.

        Args:
            event_data: Dictionary containing event data.

        Returns:
            True if storage was successful, False otherwise.
        """
        try:
            provider = event_data.get("provider", "").lower()
            if not provider:
                logger.warning("Missing provider in event data")
                return False

            # Extract and validate fields
            external_id = (
                event_data.get("external_id")
                or event_data.get("transaction_id")
                or event_data.get("id")
            )
            customer_id = event_data.get("customer_id")
            if not customer_id:
                logger.warning(
                    f"Missing customer_id in event: {event_data.get('type')}"
                )
                return False

            # Generate fallback ID if needed
            now = timezone.now()
            if not external_id:
                external_id = f"{provider}_{now.strftime('%Y%m%d_%H%M%S_%f')}"

            # Extract other fields with defaults
            # The `or` fallback handles explicit None values from some providers
            amount = event_data.get("amount", 0) or 0
            currency = event_data.get("currency", "USD") or "USD"
            status = self._normalize_status(event_data.get("status"))
            event_type = event_data.get("type", "payment")
            display_type = self._get_event_display_type(event_type)

            # Create webhook record for Redis
            webhook_record = {
                "type": display_type,
                "event_type": event_type,
                "provider": provider,
                "external_id": str(external_id),
                "customer_id": str(customer_id),
                "amount": float(Decimal(str(amount))),
                "currency": currency.upper(),
                "status": status,
                "metadata": event_data.get("metadata", {}),
                "processed_at": now.isoformat(),
                "timestamp": now.timestamp(),
                "shopify_order_ref": event_data.get("shopify_order_ref", ""),
                "chargify_transaction_id": event_data.get(
                    "chargify_transaction_id", ""
                ),
                "stripe_payment_intent_id": event_data.get(
                    "stripe_payment_intent_id", ""
                ),
            }

            # Store in Redis with TTL
            timestamp_key = now.strftime("%Y%m%d_%H%M%S_%f")
            webhook_key = self._get_webhook_key(display_type, timestamp_key)

            cache.set(webhook_key, json.dumps(webhook_record), timeout=self.ttl_seconds)

            # Add to daily activity list
            date_str = now.strftime("%Y-%m-%d")
            activity_key = self._get_activity_key(date_str)

            # Get current activity list and append new record
            current_activity = cache.get(activity_key, [])
            if isinstance(current_activity, str):
                current_activity = json.loads(current_activity)

            current_activity.append(webhook_key)

            # Keep only last 100 records per day to prevent memory issues
            if len(current_activity) > 100:
                # Remove oldest records from cache
                old_keys = current_activity[:-100]
                for old_key in old_keys:
                    cache.delete(old_key)
                current_activity = current_activity[-100:]

            cache.set(
                activity_key, json.dumps(current_activity), timeout=self.ttl_seconds
            )

            logger.info(
                f"Stored {event_type} record in Redis: {provider} {external_id}"
            )
            return True

        except Exception as e:
            logger.error(f"Error storing event record in Redis: {e!s}", exc_info=True)
            return False

    def _validate_order_data(self, event_data: dict[str, Any]) -> dict[str, Any] | None:
        """Validate and extract order data fields.

        Args:
            event_data: Raw event data dictionary.

        Returns:
            Validated data dictionary, or None if validation fails.
        """
        platform = event_data.get("provider", "").lower()
        if platform not in ["shopify"]:
            logger.warning(f"Unsupported platform for order: {platform}")
            return None

        # Extract required fields
        external_id = (
            event_data.get("external_id")
            or event_data.get("order_id")
            or event_data.get("id")
        )
        customer_id = event_data.get("customer_id")
        total_amount = event_data.get("amount") or event_data.get("total_amount")

        if not external_id or not customer_id or total_amount is None:
            logger.warning(f"Missing required fields in order event: {event_data}")
            return None

        return {
            "platform": platform,
            "external_id": external_id,
            "customer_id": customer_id,
            "total_amount": total_amount,
            "status": event_data.get("status", "pending").lower(),
            "currency": event_data.get("currency", "USD"),
            "order_number": event_data.get("order_number", ""),
            "order_date": event_data.get("order_date"),
            "metadata": event_data.get("metadata", {}),
        }

    def _normalize_order_status(self, status: str) -> str:
        """Normalize order status to standard values.

        Args:
            status: Raw status string.

        Returns:
            Normalized status string.
        """
        if status in ["successful", "completed", "fulfilled"]:
            return "paid"
        elif status in ["cancelled", "canceled"]:
            return "cancelled"
        return status

    def _parse_order_date(self, order_date_str: str | None) -> datetime:
        """Parse order date from string or return current time.

        Args:
            order_date_str: ISO format date string or None.

        Returns:
            Parsed datetime or current time if parsing fails.
        """
        if not order_date_str:
            return timezone.now()

        try:
            return datetime.fromisoformat(order_date_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return timezone.now()

    def _create_order_record(self, validated_data: dict[str, Any]) -> dict[str, Any]:
        """Create webhook record for order.

        Args:
            validated_data: Validated order data dictionary.

        Returns:
            Formatted webhook record dictionary.
        """
        now = timezone.now()
        order_date = self._parse_order_date(validated_data["order_date"])
        status = self._normalize_order_status(validated_data["status"])

        return {
            "type": "order",
            "provider": validated_data["platform"],
            "external_id": str(validated_data["external_id"]),
            "customer_id": str(validated_data["customer_id"]),
            "order_number": str(validated_data["order_number"]),
            "amount": float(Decimal(str(validated_data["total_amount"]))),
            "currency": validated_data["currency"].upper(),
            "status": status,
            "metadata": validated_data["metadata"],
            "order_date": order_date.isoformat(),
            "processed_at": now.isoformat(),
            "timestamp": now.timestamp(),
        }

    def store_order_record(self, event_data: dict[str, Any]) -> bool:
        """Store an order record in Redis with TTL.

        Args:
            event_data: Dictionary containing order event data.

        Returns:
            True if storage was successful, False otherwise.
        """
        try:
            # Validate and extract order data
            validated_data = self._validate_order_data(event_data)
            if not validated_data:
                return False

            # Create webhook record
            webhook_record = self._create_order_record(validated_data)

            # Store in Redis with TTL
            now = timezone.now()
            timestamp_key = now.strftime("%Y%m%d_%H%M%S_%f")
            webhook_key = self._get_webhook_key("order", timestamp_key)

            cache.set(webhook_key, json.dumps(webhook_record), timeout=self.ttl_seconds)

            # Add to daily activity list
            self._add_to_activity_list(webhook_key)

            logger.info(
                f"Stored order record in Redis: "
                f"{validated_data['platform']} {validated_data['external_id']}"
            )
            return True

        except Exception as e:
            logger.error(f"Error storing order record in Redis: {e!s}", exc_info=True)
            return False

    def _add_to_activity_list(self, webhook_key: str) -> None:
        """Add webhook key to daily activity list with cleanup.

        Args:
            webhook_key: Redis key for the webhook record.
        """
        now = timezone.now()
        date_str = now.strftime("%Y-%m-%d")
        activity_key = self._get_activity_key(date_str)

        # Get current activity list and append new record
        current_activity = cache.get(activity_key, [])
        if isinstance(current_activity, str):
            current_activity = json.loads(current_activity)

        current_activity.append(webhook_key)

        # Keep only last 100 records per day
        if len(current_activity) > 100:
            # Remove oldest records from cache
            old_keys = current_activity[:-100]
            for old_key in old_keys:
                cache.delete(old_key)
            current_activity = current_activity[-100:]

        cache.set(activity_key, json.dumps(current_activity), timeout=self.ttl_seconds)

    def get_recent_webhook_activity(
        self, days: int = 7, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Get recent webhook activity from Redis.

        Args:
            days: Number of days to look back.
            limit: Maximum number of records to return.

        Returns:
            List of webhook activity records, sorted by timestamp.
        """
        try:
            activity_records: list[dict[str, Any]] = []

            # Get activity from last N days
            for i in range(days):
                date = timezone.now() - timedelta(days=i)
                date_str = date.strftime("%Y-%m-%d")
                activity_key = self._get_activity_key(date_str)

                # Get webhook keys for this day
                webhook_keys = cache.get(activity_key, [])
                if isinstance(webhook_keys, str):
                    webhook_keys = json.loads(webhook_keys)

                # Fetch webhook records
                for webhook_key in webhook_keys:
                    webhook_data = cache.get(webhook_key)
                    if webhook_data:
                        if isinstance(webhook_data, str):
                            webhook_data = json.loads(webhook_data)
                        activity_records.append(webhook_data)

            # Sort by timestamp (most recent first)
            activity_records.sort(key=lambda x: x.get("timestamp", 0), reverse=True)

            # Return limited results
            return activity_records[:limit]

        except Exception as e:
            logger.error(
                f"Error retrieving webhook activity from Redis: {e!s}", exc_info=True
            )
            return []

    def lookup_chargify_payment_for_shopify_order(self, order_ref: str) -> str | None:
        """Look up Chargify payment for Shopify order.

        Args:
            order_ref: Shopify order reference.

        Returns:
            Related Chargify payment reference, or None if not found.
        """
        try:
            # For now, just log the lookup attempt
            # In a full implementation, this would search through recent webhook records
            logger.info(f"Looking up Chargify payment for Shopify order: {order_ref}")
            return None

        except Exception as e:
            logger.error(f"Error looking up payment reference: {e!s}", exc_info=True)
            return None

    def lookup_shopify_order_for_chargify_payment(self, order_ref: str) -> str | None:
        """Look up Shopify order for Chargify payment.

        Args:
            order_ref: Chargify order reference.

        Returns:
            Related Shopify order reference, or None if not found.
        """
        try:
            # For now, just log the lookup attempt
            # In a full implementation, this would search through recent webhook records
            # for matching Shopify orders based on the order reference
            logger.info(
                f"Looking up Shopify order for Chargify payment "
                f"with order ref: {order_ref}"
            )
            return None

        except Exception as e:
            logger.error(f"Error looking up order reference: {e!s}", exc_info=True)
            return None
