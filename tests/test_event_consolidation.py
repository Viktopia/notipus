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
        result = service.should_send_notification(
            event_type="payment_success",
            customer_id="cus_789",
            workspace_id="ws_456",
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
        result = service.should_send_notification(
            event_type="payment_success",
            customer_id="cus_123",
            workspace_id="ws_other",
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
        """Test that empty customer_id always allows notification."""
        result = service.should_send_notification(
            event_type="payment_success",
            customer_id="",
            workspace_id="ws_456",
        )

        assert result is True

    def test_empty_workspace_id_allows_notification(
        self, service: EventConsolidationService, mock_cache
    ) -> None:
        """Test that empty workspace_id always allows notification."""
        result = service.should_send_notification(
            event_type="payment_success",
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
        # Process a non-primary event
        service.should_send_notification(
            event_type="payment_success",
            customer_id="cus_123",
            workspace_id="ws_456",
        )

        # Another payment_success should still go through
        result = service.should_send_notification(
            event_type="payment_success",
            customer_id="cus_123",
            workspace_id="ws_456",
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


class TestEventConsolidationConstants:
    """Test EventConsolidationService constants."""

    def test_consolidation_window_is_reasonable(self) -> None:
        """Test that consolidation window is a reasonable value."""
        assert EventConsolidationService.CONSOLIDATION_WINDOW_SECONDS >= 5
        assert EventConsolidationService.CONSOLIDATION_WINDOW_SECONDS <= 30

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
