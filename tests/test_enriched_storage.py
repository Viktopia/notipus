"""Tests for enriched webhook record storage.

This module tests the store_enriched_record method in DatabaseLookupService
that stores RichNotification data for dashboard display.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from webhooks.models.rich_notification import (
    CompanyInfo,
    CustomerInfo,
    InsightInfo,
    NotificationSeverity,
    NotificationType,
    PaymentInfo,
    RichNotification,
)
from webhooks.services.database_lookup import DatabaseLookupService


@pytest.fixture
def db_service() -> DatabaseLookupService:
    """Create a fresh DatabaseLookupService instance.

    Returns:
        DatabaseLookupService instance for testing.
    """
    return DatabaseLookupService()


@pytest.fixture
def sample_event_data() -> dict:
    """Create sample event data for testing.

    Returns:
        Dictionary with sample event data.
    """
    return {
        "type": "payment_success",
        "provider": "stripe",
        "external_id": "pi_test123",
        "customer_id": "cus_test456",
        "amount": 299.00,
        "currency": "USD",
        "status": "succeeded",
        "metadata": {
            "plan_name": "Pro Plan",
            "subscription_id": "sub_test789",
        },
    }


@pytest.fixture
def sample_notification() -> RichNotification:
    """Create a sample RichNotification for testing.

    Returns:
        RichNotification instance with enriched data.
    """
    return RichNotification(
        type=NotificationType.PAYMENT_SUCCESS,
        severity=NotificationSeverity.SUCCESS,
        headline="$299.00 from Acme Corp",
        headline_icon="money",
        provider="stripe",
        provider_display="Stripe",
        customer=CustomerInfo(
            email="billing@acme.com",
            name="John Doe",
            company_name="Acme Corp",
            tenure_display="Since Mar 2024",
            ltv_display="$2.5k",
            orders_count=5,
            total_spent=2500.00,
            status_flags=["vip"],
        ),
        company=CompanyInfo(
            name="Acme Corporation",
            domain="acme.com",
            industry="Technology",
            logo_url="https://logo.clearbit.com/acme.com",
            linkedin_url="https://linkedin.com/company/acme",
        ),
        insight=InsightInfo(
            icon="celebration",
            text="First payment - Welcome aboard!",
        ),
        payment=PaymentInfo(
            amount=299.00,
            currency="USD",
            interval="monthly",
            plan_name="Pro Plan",
            subscription_id="sub_test789",
            payment_method="visa",
            card_last4="4242",
        ),
    )


class TestStoreEnrichedRecord:
    """Tests for store_enriched_record method."""

    @patch("webhooks.services.database_lookup.cache")
    @patch("webhooks.services.database_lookup.timezone")
    def test_store_enriched_record_success(
        self,
        mock_timezone: MagicMock,
        mock_cache: MagicMock,
        db_service: DatabaseLookupService,
        sample_event_data: dict,
        sample_notification: RichNotification,
    ) -> None:
        """Test successful enriched record storage."""
        from django.utils import timezone

        mock_now = timezone.now()
        mock_timezone.now.return_value = mock_now
        # Return empty list for activity list lookup
        mock_cache.get.return_value = []

        result = db_service.store_enriched_record(
            sample_event_data, sample_notification
        )

        assert result is True
        assert mock_cache.set.call_count >= 1

        # Verify the stored data structure
        first_call_args = mock_cache.set.call_args_list[0]
        webhook_data = json.loads(first_call_args[0][1])

        # Check basic fields
        assert webhook_data["provider"] == "stripe"
        assert webhook_data["external_id"] == "pi_test123"
        assert webhook_data["customer_id"] == "cus_test456"
        assert webhook_data["amount"] == 299.00
        assert webhook_data["currency"] == "USD"

        # Check enriched fields
        assert webhook_data["headline"] == "$299.00 from Acme Corp"
        assert webhook_data["severity"] == "success"
        assert webhook_data["company_name"] == "Acme Corporation"
        assert webhook_data["company_logo_url"] == "https://logo.clearbit.com/acme.com"
        assert webhook_data["company_domain"] == "acme.com"
        assert webhook_data["customer_email"] == "billing@acme.com"
        assert webhook_data["customer_name"] == "John Doe"
        assert webhook_data["customer_ltv"] == "$2.5k"
        assert webhook_data["customer_tenure"] == "Since Mar 2024"
        assert webhook_data["customer_status_flags"] == ["vip"]
        assert webhook_data["insight_text"] == "First payment - Welcome aboard!"
        assert webhook_data["insight_icon"] == "celebration"
        assert webhook_data["plan_name"] == "Pro Plan"
        assert webhook_data["payment_method"] == "visa"
        assert webhook_data["card_last4"] == "4242"

    @patch("webhooks.services.database_lookup.cache")
    def test_store_enriched_record_missing_provider(
        self,
        mock_cache: MagicMock,
        db_service: DatabaseLookupService,
        sample_notification: RichNotification,
    ) -> None:
        """Test storage fails gracefully when provider is missing."""
        event_data = {"type": "payment_success", "customer_id": "cus_123"}

        result = db_service.store_enriched_record(event_data, sample_notification)

        assert result is False
        mock_cache.set.assert_not_called()

    @patch("webhooks.services.database_lookup.cache")
    def test_store_enriched_record_missing_customer_id(
        self,
        mock_cache: MagicMock,
        db_service: DatabaseLookupService,
        sample_notification: RichNotification,
    ) -> None:
        """Test storage fails gracefully when customer_id is missing."""
        event_data = {"type": "payment_success", "provider": "stripe"}

        result = db_service.store_enriched_record(event_data, sample_notification)

        assert result is False
        mock_cache.set.assert_not_called()

    @patch("webhooks.services.database_lookup.cache")
    @patch("webhooks.services.database_lookup.timezone")
    def test_store_enriched_record_without_company(
        self,
        mock_timezone: MagicMock,
        mock_cache: MagicMock,
        db_service: DatabaseLookupService,
        sample_event_data: dict,
    ) -> None:
        """Test storage works without company enrichment."""
        from django.utils import timezone

        mock_now = timezone.now()
        mock_timezone.now.return_value = mock_now
        mock_cache.get.return_value = []

        notification = RichNotification(
            type=NotificationType.PAYMENT_SUCCESS,
            severity=NotificationSeverity.SUCCESS,
            headline="$299.00 from Customer",
            headline_icon="money",
            provider="stripe",
            provider_display="Stripe",
            customer=CustomerInfo(email="test@example.com"),
        )

        result = db_service.store_enriched_record(sample_event_data, notification)

        assert result is True

        first_call_args = mock_cache.set.call_args_list[0]
        webhook_data = json.loads(first_call_args[0][1])

        assert "company_name" not in webhook_data
        assert "company_logo_url" not in webhook_data
        assert webhook_data["customer_email"] == "test@example.com"

    @patch("webhooks.services.database_lookup.cache")
    @patch("webhooks.services.database_lookup.timezone")
    def test_store_enriched_record_without_insight(
        self,
        mock_timezone: MagicMock,
        mock_cache: MagicMock,
        db_service: DatabaseLookupService,
        sample_event_data: dict,
    ) -> None:
        """Test storage works without insight data."""
        from django.utils import timezone

        mock_now = timezone.now()
        mock_timezone.now.return_value = mock_now
        mock_cache.get.return_value = []

        notification = RichNotification(
            type=NotificationType.PAYMENT_SUCCESS,
            severity=NotificationSeverity.SUCCESS,
            headline="$299.00 from Customer",
            headline_icon="money",
            provider="stripe",
            provider_display="Stripe",
            customer=CustomerInfo(email="test@example.com"),
            insight=None,
        )

        result = db_service.store_enriched_record(sample_event_data, notification)

        assert result is True

        first_call_args = mock_cache.set.call_args_list[0]
        webhook_data = json.loads(first_call_args[0][1])

        assert "insight_text" not in webhook_data
        assert "insight_icon" not in webhook_data

    @patch("webhooks.services.database_lookup.cache")
    def test_store_enriched_record_handles_exception(
        self,
        mock_cache: MagicMock,
        db_service: DatabaseLookupService,
        sample_event_data: dict,
        sample_notification: RichNotification,
    ) -> None:
        """Test storage handles exceptions gracefully."""
        mock_cache.set.side_effect = Exception("Redis connection failed")

        result = db_service.store_enriched_record(
            sample_event_data, sample_notification
        )

        assert result is False

    def test_ttl_defaults_to_7_days(self) -> None:
        """Test that default TTL is 7 days."""
        service = DatabaseLookupService()
        expected_ttl = 60 * 60 * 24 * 7  # 7 days in seconds
        assert service.ttl_seconds == expected_ttl

    def test_ttl_can_be_customized(self) -> None:
        """Test that TTL can be customized via constructor."""
        service = DatabaseLookupService(ttl_days=14)
        expected_ttl = 60 * 60 * 24 * 14  # 14 days in seconds
        assert service.ttl_seconds == expected_ttl
