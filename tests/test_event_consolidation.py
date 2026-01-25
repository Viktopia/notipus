"""Tests for event consolidation service.

This module tests the EventConsolidationService which prevents notification
spam by consolidating related webhook events that fire in quick succession.
"""

from unittest.mock import patch

import pytest
from webhooks.services.event_consolidation import EventConsolidationService


class TestEventConsolidationService:
    """Test EventConsolidationService functionality."""

    @pytest.fixture
    def service(self) -> EventConsolidationService:
        """Create a fresh consolidation service for each test.

        Returns:
            EventConsolidationService instance.
        """
        return EventConsolidationService()

    @pytest.fixture
    def mock_cache(self):
        """Mock Django cache for testing.

        Yields:
            Mock cache with get/set methods.
        """
        cache_data: dict = {}

        def mock_get(key: str, default=None):
            return cache_data.get(key, default)

        def mock_set(key: str, value, timeout=None):
            cache_data[key] = value

        with patch("webhooks.services.event_consolidation.cache") as mock:
            mock.get = mock_get
            mock.set = mock_set
            yield mock

    def test_primary_event_allows_notification(
        self, service: EventConsolidationService, mock_cache
    ) -> None:
        """Test that primary events always allow notifications."""
        result = service.should_send_notification(
            event_type="subscription_created",
            customer_id="cus_123",
            workspace_id="ws_456",
        )

        assert result is True

    def test_secondary_event_suppressed_after_primary(
        self, service: EventConsolidationService, mock_cache
    ) -> None:
        """Test that secondary events are suppressed after a primary event."""
        # First, process the primary event
        service.should_send_notification(
            event_type="subscription_created",
            customer_id="cus_123",
            workspace_id="ws_456",
        )

        # Now the secondary event should be suppressed
        result = service.should_send_notification(
            event_type="payment_success",
            customer_id="cus_123",
            workspace_id="ws_456",
        )

        assert result is False

    def test_invoice_paid_suppressed_after_subscription_created(
        self, service: EventConsolidationService, mock_cache
    ) -> None:
        """Test that invoice_paid is suppressed after subscription_created."""
        # Process subscription_created
        service.should_send_notification(
            event_type="subscription_created",
            customer_id="cus_123",
            workspace_id="ws_456",
        )

        # invoice_paid should be suppressed
        result = service.should_send_notification(
            event_type="invoice_paid",
            customer_id="cus_123",
            workspace_id="ws_456",
        )

        assert result is False

    def test_payment_failure_never_suppressed(
        self, service: EventConsolidationService, mock_cache
    ) -> None:
        """Test that payment_failure is never suppressed."""
        # Even after a primary event, payment_failure should go through
        service.should_send_notification(
            event_type="subscription_created",
            customer_id="cus_123",
            workspace_id="ws_456",
        )

        result = service.should_send_notification(
            event_type="payment_failure",
            customer_id="cus_123",
            workspace_id="ws_456",
        )

        assert result is True

    def test_trial_ending_never_suppressed(
        self, service: EventConsolidationService, mock_cache
    ) -> None:
        """Test that trial_ending is never suppressed."""
        service.should_send_notification(
            event_type="subscription_created",
            customer_id="cus_123",
            workspace_id="ws_456",
        )

        result = service.should_send_notification(
            event_type="trial_ending",
            customer_id="cus_123",
            workspace_id="ws_456",
        )

        assert result is True

    def test_different_customer_not_affected(
        self, service: EventConsolidationService, mock_cache
    ) -> None:
        """Test that consolidation is per-customer."""
        # Process subscription_created for customer 1
        service.should_send_notification(
            event_type="subscription_created",
            customer_id="cus_123",
            workspace_id="ws_456",
        )

        # Different customer should not be suppressed
        # Note: amount > 0 required to pass $0 payment filter
        result = service.should_send_notification(
            event_type="payment_success",
            customer_id="cus_789",
            workspace_id="ws_456",
            amount=100.00,
        )

        assert result is True

    def test_different_workspace_not_affected(
        self, service: EventConsolidationService, mock_cache
    ) -> None:
        """Test that consolidation is per-workspace."""
        # Process subscription_created for workspace 1
        service.should_send_notification(
            event_type="subscription_created",
            customer_id="cus_123",
            workspace_id="ws_456",
        )

        # Different workspace should not be suppressed
        # Note: amount > 0 required to pass $0 payment filter
        result = service.should_send_notification(
            event_type="payment_success",
            customer_id="cus_123",
            workspace_id="ws_other",
            amount=100.00,
        )

        assert result is True

    def test_checkout_completed_suppresses_payment_events(
        self, service: EventConsolidationService, mock_cache
    ) -> None:
        """Test that checkout_completed suppresses payment events."""
        service.should_send_notification(
            event_type="checkout_completed",
            customer_id="cus_123",
            workspace_id="ws_456",
        )

        # Both payment_success and invoice_paid should be suppressed
        result1 = service.should_send_notification(
            event_type="payment_success",
            customer_id="cus_123",
            workspace_id="ws_456",
        )
        result2 = service.should_send_notification(
            event_type="invoice_paid",
            customer_id="cus_123",
            workspace_id="ws_456",
        )

        assert result1 is False
        assert result2 is False

    def test_empty_customer_id_allows_notification(
        self, service: EventConsolidationService, mock_cache
    ) -> None:
        """Test that empty customer_id always allows notification.

        Note: Uses subscription_created since payment_success without amount
        is filtered out by the $0 payment filter.
        """
        result = service.should_send_notification(
            event_type="subscription_created",
            customer_id="",
            workspace_id="ws_456",
        )

        assert result is True

    def test_empty_workspace_id_allows_notification(
        self, service: EventConsolidationService, mock_cache
    ) -> None:
        """Test that empty workspace_id always allows notification.

        Note: Uses subscription_created since payment_success without amount
        is filtered out by the $0 payment filter.
        """
        result = service.should_send_notification(
            event_type="subscription_created",
            customer_id="cus_123",
            workspace_id="",
        )

        assert result is True

    def test_is_duplicate_returns_false_for_new_event(
        self, service: EventConsolidationService, mock_cache
    ) -> None:
        """Test that is_duplicate returns False for new events."""
        result = service.is_duplicate(
            workspace_id="ws_456",
            external_id="evt_123",
        )

        assert result is False

    def test_is_duplicate_returns_true_for_recorded_event(
        self, service: EventConsolidationService, mock_cache
    ) -> None:
        """Test that is_duplicate returns True for recorded events."""
        # Record the event
        service.record_event(
            event_type="payment_success",
            customer_id="cus_123",
            workspace_id="ws_456",
            external_id="evt_123",
        )

        # Now it should be detected as duplicate
        result = service.is_duplicate(
            workspace_id="ws_456",
            external_id="evt_123",
        )

        assert result is True

    def test_is_duplicate_returns_false_for_empty_external_id(
        self, service: EventConsolidationService, mock_cache
    ) -> None:
        """Test that is_duplicate returns False for empty external_id."""
        result = service.is_duplicate(
            workspace_id="ws_456",
            external_id="",
        )

        assert result is False

    def test_is_duplicate_returns_false_for_none_external_id(
        self, service: EventConsolidationService, mock_cache
    ) -> None:
        """Test that is_duplicate returns False for None external_id."""
        result = service.is_duplicate(
            workspace_id="ws_456",
            external_id=None,
        )

        assert result is False

    def test_non_primary_event_does_not_suppress_others(
        self, service: EventConsolidationService, mock_cache
    ) -> None:
        """Test that non-primary events don't suppress other events."""
        # Process a non-primary event with amount > 0
        service.should_send_notification(
            event_type="payment_success",
            customer_id="cus_123",
            workspace_id="ws_456",
            amount=100.00,
        )

        # Another payment_success should still go through
        result = service.should_send_notification(
            event_type="payment_success",
            customer_id="cus_123",
            workspace_id="ws_456",
            amount=100.00,
        )

        assert result is True

    def test_subscription_deleted_suppresses_invoice_paid(
        self, service: EventConsolidationService, mock_cache
    ) -> None:
        """Test that subscription_deleted suppresses invoice_paid."""
        service.should_send_notification(
            event_type="subscription_deleted",
            customer_id="cus_123",
            workspace_id="ws_456",
        )

        result = service.should_send_notification(
            event_type="invoice_paid",
            customer_id="cus_123",
            workspace_id="ws_456",
        )

        assert result is False

    def test_shopify_order_created_suppresses_payment_success(
        self, service: EventConsolidationService, mock_cache
    ) -> None:
        """Test that Shopify order_created suppresses payment_success.

        When a Shopify order is placed, both orders/create and orders/paid webhooks
        fire. The order_created event should suppress the subsequent payment_success
        to prevent duplicate notifications.
        """
        # First, process order_created (from orders/create webhook)
        service.should_send_notification(
            event_type="order_created",
            customer_id="shopify_cus_123",
            workspace_id="ws_456",
        )

        # Now payment_success (from orders/paid webhook) should be suppressed
        result = service.should_send_notification(
            event_type="payment_success",
            customer_id="shopify_cus_123",
            workspace_id="ws_456",
        )

        assert result is False

    def test_shopify_order_created_allows_notification(
        self, service: EventConsolidationService, mock_cache
    ) -> None:
        """Test that Shopify order_created allows its own notification."""
        result = service.should_send_notification(
            event_type="order_created",
            customer_id="shopify_cus_123",
            workspace_id="ws_456",
        )

        assert result is True


class TestZeroAmountFiltering:
    """Test zero-amount payment filtering functionality."""

    @pytest.fixture
    def service(self) -> EventConsolidationService:
        """Create a fresh consolidation service for each test.

        Returns:
            EventConsolidationService instance.
        """
        return EventConsolidationService()

    def test_zero_amount_payment_success_suppressed(
        self, service: EventConsolidationService
    ) -> None:
        """Test that $0 payment_success events are suppressed."""
        result = service.should_send_notification(
            event_type="payment_success",
            customer_id="cus_123",
            workspace_id="ws_456",
            amount=0.0,
        )
        assert result is False

    def test_zero_amount_invoice_paid_suppressed(
        self, service: EventConsolidationService
    ) -> None:
        """Test that $0 invoice_paid events are suppressed."""
        result = service.should_send_notification(
            event_type="invoice_paid",
            customer_id="cus_123",
            workspace_id="ws_456",
            amount=0.0,
        )
        assert result is False

    def test_none_amount_payment_success_suppressed(
        self, service: EventConsolidationService
    ) -> None:
        """Test that payment_success with no amount is suppressed."""
        result = service.should_send_notification(
            event_type="payment_success",
            customer_id="cus_123",
            workspace_id="ws_456",
            amount=None,
        )
        assert result is False

    def test_positive_amount_payment_success_allowed(
        self, service: EventConsolidationService
    ) -> None:
        """Test that payment_success with positive amount is allowed."""
        with patch("webhooks.services.event_consolidation.cache") as mock_cache:
            mock_cache.get.return_value = None
            result = service.should_send_notification(
                event_type="payment_success",
                customer_id="cus_123",
                workspace_id="ws_456",
                amount=100.00,
            )
        assert result is True

    def test_subscription_created_not_affected_by_zero_filter(
        self, service: EventConsolidationService
    ) -> None:
        """Test that subscription_created is not affected by zero amount filter."""
        with patch("webhooks.services.event_consolidation.cache") as mock_cache:
            mock_cache.get.return_value = None
            result = service.should_send_notification(
                event_type="subscription_created",
                customer_id="cus_123",
                workspace_id="ws_456",
                amount=0.0,
            )
        assert result is True

    def test_payment_failure_not_affected_by_zero_filter(
        self, service: EventConsolidationService
    ) -> None:
        """Test that payment_failure is not affected by zero amount filter."""
        with patch("webhooks.services.event_consolidation.cache") as mock_cache:
            mock_cache.get.return_value = None
            result = service.should_send_notification(
                event_type="payment_failure",
                customer_id="cus_123",
                workspace_id="ws_456",
                amount=0.0,
            )
        assert result is True


class TestIdempotencyDeduplication:
    """Test idempotency-based deduplication functionality.

    Stripe sends multiple events for the same action (e.g., subscription creation
    triggers subscription.created, invoice.paid, invoice.payment_succeeded).
    All events share the same idempotency_key, which we use to deduplicate.
    """

    @pytest.fixture
    def service(self) -> EventConsolidationService:
        """Create a fresh consolidation service for each test.

        Returns:
            EventConsolidationService instance.
        """
        return EventConsolidationService()

    @pytest.fixture
    def mock_cache(self):
        """Mock Django cache for testing.

        Yields:
            Mock cache with get/set methods.
        """
        cache_data: dict = {}

        def mock_get(key: str, default=None):
            return cache_data.get(key, default)

        def mock_set(key: str, value, timeout=None):
            cache_data[key] = value

        with patch("webhooks.services.event_consolidation.cache") as mock:
            mock.get = mock_get
            mock.set = mock_set
            yield mock

    def test_first_event_with_idempotency_key_not_duplicate(
        self, service: EventConsolidationService, mock_cache
    ) -> None:
        """Test that first event with an idempotency key is not a duplicate."""
        result = service.is_duplicate_by_idempotency(
            workspace_id="ws_456",
            idempotency_key="idem_12345",
        )

        assert result is False

    def test_second_event_with_same_idempotency_key_is_duplicate(
        self, service: EventConsolidationService, mock_cache
    ) -> None:
        """Test that second event with same idempotency key is duplicate."""
        # Record the first event
        service.record_idempotency_key(
            workspace_id="ws_456",
            idempotency_key="idem_12345",
        )

        # Second event should be detected as duplicate
        result = service.is_duplicate_by_idempotency(
            workspace_id="ws_456",
            idempotency_key="idem_12345",
        )

        assert result is True

    def test_none_idempotency_key_not_duplicate(
        self, service: EventConsolidationService, mock_cache
    ) -> None:
        """Test that None idempotency_key returns False (not duplicate)."""
        result = service.is_duplicate_by_idempotency(
            workspace_id="ws_456",
            idempotency_key=None,
        )

        assert result is False

    def test_empty_idempotency_key_not_duplicate(
        self, service: EventConsolidationService, mock_cache
    ) -> None:
        """Test that empty idempotency_key returns False (not duplicate)."""
        result = service.is_duplicate_by_idempotency(
            workspace_id="ws_456",
            idempotency_key="",
        )

        assert result is False

    def test_different_workspace_not_duplicate(
        self, service: EventConsolidationService, mock_cache
    ) -> None:
        """Test that same idempotency key in different workspace is not duplicate."""
        # Record for workspace 1
        service.record_idempotency_key(
            workspace_id="ws_456",
            idempotency_key="idem_12345",
        )

        # Different workspace should not be duplicate
        result = service.is_duplicate_by_idempotency(
            workspace_id="ws_other",
            idempotency_key="idem_12345",
        )

        assert result is False

    def test_record_idempotency_key_with_none_does_nothing(
        self, service: EventConsolidationService, mock_cache
    ) -> None:
        """Test that recording None idempotency key doesn't cause errors."""
        # Should not raise
        service.record_idempotency_key(
            workspace_id="ws_456",
            idempotency_key=None,
        )

        # And subsequent check should return False
        result = service.is_duplicate_by_idempotency(
            workspace_id="ws_456",
            idempotency_key=None,
        )
        assert result is False

    def test_realistic_stripe_multi_event_scenario(
        self, service: EventConsolidationService, mock_cache
    ) -> None:
        """Test realistic scenario: subscription creation triggers 3 events.

        When a subscription is created, Stripe fires:
        1. customer.subscription.created
        2. invoice.paid
        3. invoice.payment_succeeded

        All share the same idempotency_key. Only the first should process.
        """
        idempotency_key = "75fad5af-4d03-4ada-bfaa-f267c84702f9"
        workspace_id = "ws_test"

        # First event: subscription.created - should NOT be duplicate
        assert (
            service.is_duplicate_by_idempotency(workspace_id, idempotency_key) is False
        )
        # Record after processing
        service.record_idempotency_key(workspace_id, idempotency_key)

        # Second event: invoice.paid - should be duplicate
        assert (
            service.is_duplicate_by_idempotency(workspace_id, idempotency_key) is True
        )

        # Third event: invoice.payment_succeeded - should also be duplicate
        assert (
            service.is_duplicate_by_idempotency(workspace_id, idempotency_key) is True
        )


class TestEventConsolidationConstants:
    """Test EventConsolidationService constants."""

    def test_consolidation_window_is_reasonable(self) -> None:
        """Test that consolidation window is a reasonable value.

        Window is 5 minutes (300s) to handle Stripe's delayed event delivery
        where related events can arrive 3-4+ minutes apart.
        """
        assert EventConsolidationService.CONSOLIDATION_WINDOW_SECONDS >= 60
        assert EventConsolidationService.CONSOLIDATION_WINDOW_SECONDS <= 600

    def test_idempotency_window_is_reasonable(self) -> None:
        """Test that idempotency window is a reasonable value.

        Multiple events from same Stripe action arrive within seconds,
        but we use 5 minutes to handle any delays.
        """
        assert EventConsolidationService.IDEMPOTENCY_WINDOW_SECONDS >= 60
        assert EventConsolidationService.IDEMPOTENCY_WINDOW_SECONDS <= 600

    def test_never_suppress_includes_critical_events(self) -> None:
        """Test that critical events are in NEVER_SUPPRESS."""
        never_suppress = EventConsolidationService.NEVER_SUPPRESS

        assert "payment_failure" in never_suppress
        assert "payment_action_required" in never_suppress
        assert "trial_ending" in never_suppress

    def test_primary_events_defined(self) -> None:
        """Test that primary events are properly defined."""
        primary = EventConsolidationService.PRIMARY_EVENTS

        assert "subscription_created" in primary
        assert "payment_success" in primary["subscription_created"]
        assert "invoice_paid" in primary["subscription_created"]

    def test_shopify_order_created_in_primary_events(self) -> None:
        """Test that Shopify order_created is defined as a primary event."""
        primary = EventConsolidationService.PRIMARY_EVENTS

        assert "order_created" in primary
        assert "payment_success" in primary["order_created"]
