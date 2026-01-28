"""Tests for pending event queue service.

This module tests the PendingEventQueue which implements delayed processing
of webhook events to allow related events to be aggregated before sending
a single notification.
"""

import threading
from unittest.mock import MagicMock, patch

import pytest
from webhooks.services.pending_event_queue import PendingEventQueue


class TestPendingEventQueueStorage:
    """Test event storage functionality."""

    @pytest.fixture
    def queue(self) -> PendingEventQueue:
        """Create a fresh queue instance for each test."""
        queue = PendingEventQueue()
        queue.DELAY_SECONDS = 0.1  # Short delay for tests
        return queue

    @pytest.fixture
    def mock_cache(self):
        """Mock Django cache."""
        cache_data: dict = {}

        def mock_get(key, default=None):
            return cache_data.get(key, default)

        def mock_set(key, value, timeout=None):
            cache_data[key] = value

        def mock_delete(key):
            cache_data.pop(key, None)

        with patch("webhooks.services.pending_event_queue.cache") as mock:
            mock.get = mock_get
            mock.set = mock_set
            mock.delete = mock_delete
            yield mock

    def test_store_event_creates_new_list(
        self, queue: PendingEventQueue, mock_cache
    ) -> None:
        """Test that storing first event creates a new list."""
        event_data = {"type": "subscription_created", "customer_id": "cus_123"}
        customer_data = {"email": "test@example.com"}

        queue._store_event("idem_key", "ws_123", event_data, customer_data)

        key = "pending_webhook:ws_123:idem_key"
        stored = mock_cache.get(key)
        assert stored is not None
        assert len(stored) == 1
        # Check original fields are present (plus _queued_at timestamp)
        assert stored[0]["event_data"]["type"] == event_data["type"]
        assert stored[0]["event_data"]["customer_id"] == event_data["customer_id"]
        # Timestamp added for orphan recovery
        assert "_queued_at" in stored[0]["event_data"]
        assert stored[0]["customer_data"] == customer_data

    def test_store_event_appends_to_existing(
        self, queue: PendingEventQueue, mock_cache
    ) -> None:
        """Test that storing second event appends to existing list."""
        event1 = {"type": "subscription_created", "customer_id": "cus_123"}
        event2 = {"type": "invoice_paid", "customer_id": "cus_123"}
        customer1 = {"email": ""}
        customer2 = {"email": "found@example.com"}

        queue._store_event("idem_key", "ws_123", event1, customer1)
        queue._store_event("idem_key", "ws_123", event2, customer2)

        key = "pending_webhook:ws_123:idem_key"
        stored = mock_cache.get(key)
        assert len(stored) == 2


class TestPendingEventQueueAggregation:
    """Test event aggregation logic."""

    @pytest.fixture
    def queue(self) -> PendingEventQueue:
        """Create a fresh queue instance."""
        return PendingEventQueue()

    def test_aggregate_takes_email_from_invoice_event(
        self, queue: PendingEventQueue
    ) -> None:
        """Test that email is extracted from invoice events."""
        stored_items = [
            {
                "event_data": {
                    "type": "subscription_created",
                    "customer_id": "cus_123",
                },
                "customer_data": {"email": ""},
            },
            {
                "event_data": {
                    "type": "invoice_paid",
                    "customer_id": "cus_123",
                    "customer_email": "from_invoice@example.com",
                },
                "customer_data": {"email": "from_invoice@example.com"},
            },
        ]

        event, customer = queue._aggregate_events(stored_items)

        assert customer["email"] == "from_invoice@example.com"

    def test_aggregate_prefers_subscription_type(
        self, queue: PendingEventQueue
    ) -> None:
        """Test that subscription_created type is preferred over invoice."""
        stored_items = [
            {
                "event_data": {"type": "invoice_paid", "customer_id": "cus_123"},
                "customer_data": {"email": "test@example.com"},
            },
            {
                "event_data": {
                    "type": "subscription_created",
                    "customer_id": "cus_123",
                },
                "customer_data": {"email": ""},
            },
        ]

        event, customer = queue._aggregate_events(stored_items)

        assert event["type"] == "subscription_created"

    def test_aggregate_prefers_trial_started_type(
        self, queue: PendingEventQueue
    ) -> None:
        """Test that trial_started type is preferred over subscription_created."""
        stored_items = [
            {
                "event_data": {
                    "type": "subscription_created",
                    "customer_id": "cus_123",
                },
                "customer_data": {"email": ""},
            },
            {
                "event_data": {"type": "trial_started", "customer_id": "cus_123"},
                "customer_data": {"email": ""},
            },
        ]

        event, customer = queue._aggregate_events(stored_items)

        assert event["type"] == "trial_started"

    def test_aggregate_empty_list_returns_empty_dicts(
        self, queue: PendingEventQueue
    ) -> None:
        """Test that empty list returns empty dicts."""
        event, customer = queue._aggregate_events([])
        assert event == {}
        assert customer == {}

    def test_aggregate_single_event_returns_as_is(
        self, queue: PendingEventQueue
    ) -> None:
        """Test that single event is returned as-is."""
        stored_items = [
            {
                "event_data": {
                    "type": "subscription_created",
                    "customer_id": "cus_123",
                    "amount": 29.99,
                },
                "customer_data": {"email": "test@example.com", "first_name": "John"},
            },
        ]

        event, customer = queue._aggregate_events(stored_items)

        assert event["type"] == "subscription_created"
        assert event["amount"] == 29.99
        assert customer["email"] == "test@example.com"
        assert customer["first_name"] == "John"

    def test_aggregate_merges_customer_fields(self, queue: PendingEventQueue) -> None:
        """Test that customer fields are merged from multiple events."""
        stored_items = [
            {
                "event_data": {"type": "subscription_created"},
                "customer_data": {"email": "", "first_name": "John", "last_name": ""},
            },
            {
                "event_data": {"type": "invoice_paid"},
                "customer_data": {
                    "email": "john@example.com",
                    "first_name": "",
                    "last_name": "Doe",
                },
            },
        ]

        event, customer = queue._aggregate_events(stored_items)

        assert customer["email"] == "john@example.com"
        assert customer["first_name"] == "John"  # From first event
        assert customer["last_name"] == "Doe"  # From second event

    def test_aggregate_copies_metadata_from_preferred_type(
        self, queue: PendingEventQueue
    ) -> None:
        """Test that metadata is copied from the preferred event type."""
        stored_items = [
            {
                "event_data": {
                    "type": "invoice_paid",
                    "metadata": {"plan": "basic"},
                },
                "customer_data": {},
            },
            {
                "event_data": {
                    "type": "subscription_created",
                    "metadata": {"plan": "pro", "billing_period": "monthly"},
                },
                "customer_data": {},
            },
        ]

        event, customer = queue._aggregate_events(stored_items)

        assert event["type"] == "subscription_created"
        assert event["metadata"]["plan"] == "pro"
        assert event["metadata"]["billing_period"] == "monthly"


class TestPendingEventQueueScheduling:
    """Test timer scheduling functionality."""

    @pytest.fixture
    def queue(self) -> PendingEventQueue:
        """Create a fresh queue instance with short delay."""
        queue = PendingEventQueue()
        queue.DELAY_SECONDS = 0.1  # 100ms for fast tests
        # Clear any existing timers
        with queue._lock:
            queue._active_timers.clear()
        return queue

    def test_schedule_creates_timer(self, queue: PendingEventQueue) -> None:
        """Test that scheduling creates a timer."""
        with patch.object(queue, "_process_events"):
            queue._schedule_processing("idem_key", "ws_123", "stripe", None)

            timer_key = "ws_123:idem_key"
            assert timer_key in queue._active_timers
            assert isinstance(queue._active_timers[timer_key], threading.Timer)

            # Clean up
            queue._active_timers[timer_key].cancel()

    def test_schedule_does_not_duplicate_timer(self, queue: PendingEventQueue) -> None:
        """Test that scheduling twice doesn't create duplicate timers."""
        with patch.object(queue, "_process_events"):
            queue._schedule_processing("idem_key", "ws_123", "stripe", None)
            first_timer = queue._active_timers["ws_123:idem_key"]

            queue._schedule_processing("idem_key", "ws_123", "stripe", None)
            second_timer = queue._active_timers["ws_123:idem_key"]

            assert first_timer is second_timer

            # Clean up
            first_timer.cancel()


class TestPendingEventQueueIntegration:
    """Integration tests for the full queue flow."""

    @pytest.fixture
    def queue(self) -> PendingEventQueue:
        """Create a fresh queue instance with short delay."""
        queue = PendingEventQueue()
        queue.DELAY_SECONDS = 0.2  # 200ms for tests
        with queue._lock:
            queue._active_timers.clear()
        return queue

    @pytest.fixture
    def mock_cache(self):
        """Mock Django cache."""
        cache_data: dict = {}

        def mock_get(key, default=None):
            return cache_data.get(key, default)

        def mock_set(key, value, timeout=None):
            cache_data[key] = value

        def mock_delete(key):
            cache_data.pop(key, None)

        with patch("webhooks.services.pending_event_queue.cache") as mock:
            mock.get = mock_get
            mock.set = mock_set
            mock.delete = mock_delete
            yield mock

    def test_queue_event_stores_and_schedules(
        self, queue: PendingEventQueue, mock_cache
    ) -> None:
        """Test that queue_event both stores and schedules."""
        event_data = {"type": "subscription_created", "customer_id": "cus_123"}
        customer_data = {"email": "test@example.com"}

        with patch.object(queue, "_process_events"):
            queue.queue_event(
                idempotency_key="idem_123",
                workspace_id="ws_456",
                event_data=event_data,
                customer_data=customer_data,
                provider_name="stripe",
                workspace=None,
            )

        # Check event was stored
        key = "pending_webhook:ws_456:idem_123"
        stored = mock_cache.get(key)
        assert stored is not None
        assert len(stored) == 1

        # Check timer was scheduled
        assert "ws_456:idem_123" in queue._active_timers

        # Clean up
        queue._active_timers["ws_456:idem_123"].cancel()

    def test_multiple_events_same_key_aggregated(
        self, queue: PendingEventQueue, mock_cache
    ) -> None:
        """Test that multiple events with same key are aggregated."""
        with patch.object(queue, "_process_events"):
            # First event (subscription.created - no email)
            queue.queue_event(
                idempotency_key="idem_123",
                workspace_id="ws_456",
                event_data={
                    "type": "subscription_created",
                    "customer_id": "cus_123",
                },
                customer_data={"email": ""},
                provider_name="stripe",
                workspace=None,
            )

            # Second event (invoice.paid - has email)
            queue.queue_event(
                idempotency_key="idem_123",
                workspace_id="ws_456",
                event_data={
                    "type": "invoice_paid",
                    "customer_id": "cus_123",
                },
                customer_data={"email": "found@example.com"},
                provider_name="stripe",
                workspace=None,
            )

        # Check both events were stored
        key = "pending_webhook:ws_456:idem_123"
        stored = mock_cache.get(key)
        assert len(stored) == 2

        # Clean up
        queue._active_timers["ws_456:idem_123"].cancel()


class TestPendingEventQueueProcessing:
    """Test event processing and notification sending."""

    @pytest.fixture
    def queue(self) -> PendingEventQueue:
        """Create a fresh queue instance."""
        queue = PendingEventQueue()
        with queue._lock:
            queue._active_timers.clear()
        return queue

    def test_process_events_sends_notification(self, queue: PendingEventQueue) -> None:
        """Test that processing sends a notification."""
        stored_items = [
            {
                "event_data": {
                    "type": "subscription_created",
                    "customer_id": "cus_123",
                    "amount": 29.99,
                },
                "customer_data": {"email": "test@example.com"},
            },
        ]

        with patch("webhooks.services.pending_event_queue.cache") as mock_cache:
            mock_cache.get.return_value = stored_items
            mock_cache.add.return_value = True  # Acquire lock successfully

            with patch.object(
                queue, "_send_notification", return_value=True
            ) as mock_send:
                queue._process_events("idem_123", "ws_456", "stripe", None)

                mock_send.assert_called_once()
                call_args = mock_send.call_args
                assert call_args[0][0]["type"] == "subscription_created"
                assert call_args[0][1]["email"] == "test@example.com"

    def test_process_events_cleans_up_cache(self, queue: PendingEventQueue) -> None:
        """Test that processing deletes events from cache after success."""
        stored_items = [
            {
                "event_data": {"type": "subscription_created"},
                "customer_data": {"email": "test@example.com"},
            },
        ]

        with patch("webhooks.services.pending_event_queue.cache") as mock_cache:
            mock_cache.get.return_value = stored_items
            mock_cache.add.return_value = True  # Acquire lock

            with patch.object(queue, "_send_notification", return_value=True):
                queue._process_events("idem_123", "ws_456", "stripe", None)

                mock_cache.delete.assert_any_call("pending_webhook:ws_456:idem_123")

    def test_process_events_does_not_delete_on_failure(
        self, queue: PendingEventQueue
    ) -> None:
        """Test that events are NOT deleted if notification fails."""
        stored_items = [
            {
                "event_data": {"type": "subscription_created"},
                "customer_data": {"email": "test@example.com"},
            },
        ]

        with patch("webhooks.services.pending_event_queue.cache") as mock_cache:
            mock_cache.get.return_value = stored_items
            mock_cache.add.return_value = True  # Acquire lock

            with patch.object(queue, "_send_notification", return_value=False):
                queue._process_events("idem_123", "ws_456", "stripe", None)

                # Should NOT delete the events - they should remain for retry
                delete_calls = [
                    call
                    for call in mock_cache.delete.call_args_list
                    if "pending_webhook" in str(call)
                ]
                assert len(delete_calls) == 0

    def test_process_events_removes_timer_reference(
        self, queue: PendingEventQueue
    ) -> None:
        """Test that processing removes the timer reference."""
        # Add a fake timer reference
        timer_key = "ws_456:idem_123"
        queue._active_timers[timer_key] = MagicMock()

        with patch("webhooks.services.pending_event_queue.cache") as mock_cache:
            mock_cache.get.return_value = []
            mock_cache.add.return_value = True  # Acquire lock

            queue._process_events("idem_123", "ws_456", "stripe", None)

            assert timer_key not in queue._active_timers

    def test_process_events_handles_empty_cache(self, queue: PendingEventQueue) -> None:
        """Test that processing handles missing/expired events gracefully."""
        with patch("webhooks.services.pending_event_queue.cache") as mock_cache:
            mock_cache.get.return_value = []
            mock_cache.add.return_value = True  # Acquire lock

            with patch.object(queue, "_send_notification") as mock_send:
                # Should not raise
                queue._process_events("idem_123", "ws_456", "stripe", None)

                # Should not send notification
                mock_send.assert_not_called()

    def test_process_events_skips_if_lock_not_acquired(
        self, queue: PendingEventQueue
    ) -> None:
        """Test that processing is skipped if another process has the lock."""
        stored_items = [
            {
                "event_data": {"type": "subscription_created"},
                "customer_data": {"email": "test@example.com"},
            },
        ]

        with patch("webhooks.services.pending_event_queue.cache") as mock_cache:
            mock_cache.get.return_value = stored_items
            mock_cache.add.return_value = False  # Lock NOT acquired

            with patch.object(queue, "_send_notification") as mock_send:
                queue._process_events("idem_123", "ws_456", "stripe", None)

                # Should not send - another process has the lock
                mock_send.assert_not_called()


class TestRealisticScenarios:
    """Test realistic webhook scenarios based on production data."""

    @pytest.fixture
    def queue(self) -> PendingEventQueue:
        """Create a fresh queue instance."""
        return PendingEventQueue()

    def test_stripe_subscription_flow_aggregation(
        self, queue: PendingEventQueue
    ) -> None:
        """Test aggregation of realistic Stripe subscription events.

        Simulates the actual production scenario:
        - subscription.created at T+0ms (no email)
        - invoice.paid at T+751ms (has email)
        - invoice.payment_succeeded at T+967ms (has email)

        All share the same idempotency_key.
        """
        stored_items = [
            {
                "event_data": {
                    "type": "trial_started",  # Transformed from subscription_created
                    "customer_id": "cus_TsAte3VpFw5ucr",
                    "amount": 0,
                    "metadata": {"is_trial": True, "trial_days": 14},
                },
                "customer_data": {
                    "email": "",
                    "first_name": "",
                    "last_name": "",
                },
            },
            {
                "event_data": {
                    "type": "invoice_paid",
                    "customer_id": "cus_TsAte3VpFw5ucr",
                    "customer_email": "senitew931@gamening.com",
                    "amount": 0,
                },
                "customer_data": {
                    "email": "senitew931@gamening.com",
                    "first_name": "",
                    "last_name": "",
                },
            },
            {
                "event_data": {
                    "type": "payment_success",
                    "customer_id": "cus_TsAte3VpFw5ucr",
                    "customer_email": "senitew931@gamening.com",
                    "amount": 0,
                },
                "customer_data": {
                    "email": "senitew931@gamening.com",
                    "first_name": "",
                    "last_name": "",
                },
            },
        ]

        event, customer = queue._aggregate_events(stored_items)

        # Should have email from invoice events
        assert customer["email"] == "senitew931@gamening.com"

        # Should have trial_started type (highest priority)
        assert event["type"] == "trial_started"

        # Should have trial metadata
        assert event["metadata"]["is_trial"] is True
        assert event["metadata"]["trial_days"] == 14


class TestOrphanRecovery:
    """Test orphaned event recovery on server startup."""

    @pytest.fixture
    def queue(self) -> PendingEventQueue:
        """Create a fresh queue instance."""
        return PendingEventQueue()

    def test_is_orphaned_returns_true_for_old_events(
        self, queue: PendingEventQueue
    ) -> None:
        """Test that old events are identified as orphaned."""
        import time

        from webhooks.services.pending_event_queue import ORPHAN_MIN_AGE_SECONDS

        # 10s older than threshold
        old_timestamp = time.time() - ORPHAN_MIN_AGE_SECONDS - 10

        stored_items = [
            {
                "event_data": {
                    "type": "subscription_created",
                    "_queued_at": old_timestamp,
                },
                "customer_data": {},
            }
        ]

        assert queue._is_orphaned(stored_items) is True

    def test_is_orphaned_returns_false_for_recent_events(
        self, queue: PendingEventQueue
    ) -> None:
        """Test that recent events are not identified as orphaned."""
        import time

        recent_timestamp = time.time() - 5  # Only 5 seconds old

        stored_items = [
            {
                "event_data": {
                    "type": "subscription_created",
                    "_queued_at": recent_timestamp,
                },
                "customer_data": {},
            }
        ]

        assert queue._is_orphaned(stored_items) is False

    def test_is_orphaned_returns_true_for_missing_timestamp(
        self, queue: PendingEventQueue
    ) -> None:
        """Test that events without timestamp are assumed orphaned."""
        stored_items = [
            {
                "event_data": {"type": "subscription_created"},
                "customer_data": {},
            }
        ]

        assert queue._is_orphaned(stored_items) is True

    def test_is_orphaned_returns_false_for_empty_list(
        self, queue: PendingEventQueue
    ) -> None:
        """Test that empty list returns False."""
        assert queue._is_orphaned([]) is False

    def test_get_redis_client_returns_none_on_error(
        self, queue: PendingEventQueue
    ) -> None:
        """Test that _get_redis_client handles errors gracefully."""
        with patch("webhooks.services.pending_event_queue.cache") as mock_cache:
            mock_cache.client.get_client.side_effect = AttributeError("No client")

            result = queue._get_redis_client()

            assert result is None

    def test_recover_orphaned_events_returns_zero_when_no_client(
        self, queue: PendingEventQueue
    ) -> None:
        """Test that recovery returns 0 when Redis client unavailable."""
        with patch.object(queue, "_get_redis_client", return_value=None):
            result = queue.recover_orphaned_events()
            assert result == 0

    def test_recover_single_event_processes_orphaned_event(
        self, queue: PendingEventQueue
    ) -> None:
        """Test that a single orphaned event is processed."""
        import time

        old_timestamp = time.time() - 60  # 1 minute old

        stored_items = [
            {
                "event_data": {
                    "type": "subscription_created",
                    "customer_id": "cus_123",
                    "_queued_at": old_timestamp,
                },
                "customer_data": {"email": "test@example.com"},
            }
        ]

        with patch("webhooks.services.pending_event_queue.cache") as mock_cache:
            mock_cache.get.return_value = stored_items

            with patch.object(queue, "_process_events") as mock_process:
                # Use "global" workspace to avoid DB lookup
                result = queue._recover_single_event(
                    "pending_webhook:global:idem_key_abc"
                )

                assert result is True
                mock_process.assert_called_once_with(
                    idempotency_key="idem_key_abc",
                    workspace_id="global",
                    provider_name="stripe",
                    workspace=None,
                )

    def test_recover_single_event_skips_recent_events(
        self, queue: PendingEventQueue
    ) -> None:
        """Test that recent events are skipped during recovery."""
        import time

        recent_timestamp = time.time() - 5  # Only 5 seconds old

        stored_items = [
            {
                "event_data": {
                    "type": "subscription_created",
                    "_queued_at": recent_timestamp,
                },
                "customer_data": {},
            }
        ]

        with patch("webhooks.services.pending_event_queue.cache") as mock_cache:
            mock_cache.get.return_value = stored_items

            with patch.object(queue, "_process_events") as mock_process:
                # Use "global" workspace to avoid DB lookup
                result = queue._recover_single_event(
                    "pending_webhook:global:idem_key_abc"
                )

                assert result is False
                mock_process.assert_not_called()

    def test_recover_single_event_handles_invalid_key_format(
        self, queue: PendingEventQueue
    ) -> None:
        """Test that invalid key formats are handled gracefully."""
        result = queue._recover_single_event("invalid_key")
        assert result is False

        result = queue._recover_single_event("only:two")
        assert result is False

        with patch("webhooks.services.pending_event_queue.cache") as mock_cache:
            mock_cache.get.return_value = None
            # Valid format but no data in cache
            result = queue._recover_single_event("pending_webhook:global:key")
            assert result is False
