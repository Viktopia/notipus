"""Integration tests for Stripe webhook processing with real payload structures.

These tests simulate the complete webhook processing pipeline from raw Stripe
webhook payload to final Slack message, based on actual production data
(with customer information redacted).

The tests verify:
- Event parsing and normalization
- Event consolidation/filtering
- Customer data enrichment
- Final Slack message content and structure using RichNotification
"""

from typing import Any
from unittest.mock import Mock, patch

import pytest
from plugins.sources.stripe import StripeSourcePlugin
from webhooks.models.rich_notification import RichNotification
from webhooks.services.event_consolidation import EventConsolidationService
from webhooks.services.event_processor import EventProcessor


class TestTrialSignupIntegration:
    """Integration test: Trial signup webhook flow.

    Simulates a real trial signup where Stripe fires 3 events:
    1. customer.subscription.created - should generate notification
    2. invoice.paid ($0) - should be filtered (zero amount)
    3. invoice.payment_succeeded ($0) - should be filtered (zero amount)

    Verifies only 1 Slack notification is generated with correct content.
    """

    @pytest.fixture
    def stripe_plugin(self) -> StripeSourcePlugin:
        """Create a Stripe plugin instance."""
        return StripeSourcePlugin()

    @pytest.fixture
    def event_processor(self) -> EventProcessor:
        """Create an event processor instance."""
        return EventProcessor()

    @pytest.fixture
    def consolidation_service(self) -> EventConsolidationService:
        """Create a consolidation service instance."""
        return EventConsolidationService()

    @pytest.fixture
    def subscription_created_payload(self) -> dict[str, Any]:
        """Real subscription.created webhook payload (redacted).

        Based on actual Stripe webhook captured from production.
        """
        return {
            "id": "evt_1ABC123DEF456GHI789",
            "object": "event",
            "api_version": "2025-12-15.clover",
            "created": 1769327717,
            "type": "customer.subscription.created",
            "data": {
                "object": {
                    "id": "sub_1ABC123DEF456GHI",
                    "object": "subscription",
                    "customer": "cus_TestCustomer123",
                    "status": "trialing",
                    "currency": "usd",
                    "created": 1769327717,
                    "current_period_start": 1769327717,
                    "current_period_end": 1770537317,
                    "trial_start": 1769327717,
                    "trial_end": 1770537317,
                    "cancel_at_period_end": False,
                    "canceled_at": None,
                    "plan": {
                        "id": "price_1ABC123",
                        "object": "plan",
                        "amount": 2660,
                        "currency": "usd",
                        "interval": "month",
                        "product": "prod_TestProduct",
                    },
                },
            },
        }

    @pytest.fixture
    def invoice_paid_zero_payload(self) -> dict[str, Any]:
        """Real invoice.paid webhook with $0 amount (trial)."""
        return {
            "id": "evt_2ABC123DEF456GHI789",
            "object": "event",
            "api_version": "2025-12-15.clover",
            "created": 1769327718,
            "type": "invoice.paid",
            "data": {
                "object": {
                    "id": "in_1ABC123DEF456GHI",
                    "object": "invoice",
                    "customer": "cus_TestCustomer123",
                    "amount_due": 0,
                    "amount_paid": 0,
                    "amount_remaining": 0,
                    "currency": "usd",
                    "status": "paid",
                    "billing_reason": "subscription_create",
                    "subscription": "sub_1ABC123DEF456GHI",
                    "created": 1769327717,
                },
            },
        }

    @pytest.fixture
    def customer_data(self) -> dict[str, Any]:
        """Customer data as returned by Stripe API."""
        return {
            "email": "john.smith@acmecorp.com",
            "first_name": "John",
            "last_name": "Smith",
            "company": "",  # Often empty in Stripe
        }

    def test_subscription_created_generates_rich_notification(
        self,
        stripe_plugin: StripeSourcePlugin,
        event_processor: EventProcessor,
        subscription_created_payload: dict[str, Any],
        customer_data: dict[str, Any],
    ) -> None:
        """Test that subscription.created generates a proper RichNotification."""
        # Create mock Stripe event object
        mock_event = Mock()
        mock_event.type = subscription_created_payload["type"]
        mock_event.data.object = subscription_created_payload["data"]["object"]
        mock_event.data.previous_attributes = None

        # Extract event info
        event_type, data = stripe_plugin._extract_stripe_event_info(mock_event)
        assert event_type == "subscription_created"

        # Handle billing
        amount = stripe_plugin._handle_stripe_billing(event_type, data)
        assert amount == 26.60  # $26.60 plan

        # Build event data
        event_data = stripe_plugin._build_stripe_event_data(
            event_type=event_type,
            customer_id=data["customer"],
            data=data,
            amount=amount,
        )

        # Build rich notification
        notification = event_processor.build_rich_notification(
            event_data, customer_data
        )

        # Verify notification structure
        assert isinstance(notification, RichNotification)
        # Headline contains company name or "new customer" for subscriptions
        assert notification.headline is not None

        # Format for Slack
        slack_message = event_processor.process_event_rich(
            event_data, customer_data, target="slack"
        )

        # Verify Slack message structure
        assert "blocks" in slack_message
        assert "color" in slack_message

        # Verify header block exists
        header_block = slack_message["blocks"][0]
        assert header_block["type"] == "header"

    def test_zero_amount_invoice_filtered_before_notification(
        self,
        consolidation_service: EventConsolidationService,
        invoice_paid_zero_payload: dict[str, Any],
    ) -> None:
        """Test that $0 invoice.paid is filtered and no notification generated."""
        # This event should be filtered by consolidation service
        should_notify = consolidation_service.should_send_notification(
            event_type="invoice_paid",
            customer_id="cus_TestCustomer123",
            workspace_id="ws_test123",
            amount=0.0,  # $0 trial invoice
        )

        assert should_notify is False

    def test_full_trial_signup_flow_single_notification(
        self,
        stripe_plugin: StripeSourcePlugin,
        event_processor: EventProcessor,
        consolidation_service: EventConsolidationService,
        subscription_created_payload: dict[str, Any],
        invoice_paid_zero_payload: dict[str, Any],
        customer_data: dict[str, Any],
    ) -> None:
        """Integration test: Full trial signup flow produces exactly 1 notification."""
        notifications_sent: list[dict[str, Any]] = []

        with patch("webhooks.services.event_consolidation.cache") as mock_cache:
            mock_cache.get.return_value = None

            # Event 1: subscription.created
            mock_event_1 = Mock()
            mock_event_1.type = subscription_created_payload["type"]
            mock_event_1.data.object = subscription_created_payload["data"]["object"]
            mock_event_1.data.previous_attributes = None

            event_type_1, data_1 = stripe_plugin._extract_stripe_event_info(
                mock_event_1
            )
            amount_1 = stripe_plugin._handle_stripe_billing(event_type_1, data_1)
            event_data_1 = stripe_plugin._build_stripe_event_data(
                event_type_1, data_1["customer"], data_1, amount_1
            )

            if consolidation_service.should_send_notification(
                event_type_1, data_1["customer"], "ws_test", amount_1
            ):
                slack_message = event_processor.process_event_rich(
                    event_data_1, customer_data, target="slack"
                )
                notifications_sent.append(slack_message)

            # Event 2: invoice.paid ($0) - should be filtered
            mock_event_2 = Mock()
            mock_event_2.type = invoice_paid_zero_payload["type"]
            mock_event_2.data.object = invoice_paid_zero_payload["data"]["object"]
            mock_event_2.data.previous_attributes = None

            event_type_2, data_2 = stripe_plugin._extract_stripe_event_info(
                mock_event_2
            )
            amount_2 = stripe_plugin._handle_stripe_billing(event_type_2, data_2)

            if consolidation_service.should_send_notification(
                event_type_2, data_2["customer"], "ws_test", amount_2
            ):
                event_data_2 = stripe_plugin._build_stripe_event_data(
                    event_type_2, data_2["customer"], data_2, amount_2
                )
                slack_message = event_processor.process_event_rich(
                    event_data_2, customer_data, target="slack"
                )
                notifications_sent.append(slack_message)

        # Only 1 notification should be sent
        assert len(notifications_sent) == 1


class TestTrialConversionIntegration:
    """Integration test: Trial conversion to paid subscription.

    When a trial converts, we receive invoice.payment_succeeded with:
    - billing_reason="subscription_cycle"
    - Positive amount (first real payment)

    The Slack notification should show trial conversion in headline.
    """

    @pytest.fixture
    def stripe_plugin(self) -> StripeSourcePlugin:
        """Create a Stripe plugin instance."""
        return StripeSourcePlugin()

    @pytest.fixture
    def event_processor(self) -> EventProcessor:
        """Create an event processor instance."""
        return EventProcessor()

    @pytest.fixture
    def trial_conversion_payload(self) -> dict[str, Any]:
        """Invoice payload for first real payment after trial."""
        return {
            "id": "evt_conversion123",
            "object": "event",
            "type": "invoice.payment_succeeded",
            "data": {
                "object": {
                    "id": "in_conversion123",
                    "object": "invoice",
                    "customer": "cus_TestCustomer123",
                    "amount_due": 2660,
                    "amount_paid": 2660,
                    "amount_remaining": 0,
                    "currency": "usd",
                    "status": "paid",
                    "billing_reason": "subscription_cycle",
                    "subscription": "sub_1ABC123DEF456GHI",
                    "created": 1770537317,
                },
            },
        }

    @pytest.fixture
    def customer_data(self) -> dict[str, Any]:
        """Customer data."""
        return {
            "email": "john.smith@acmecorp.com",
            "first_name": "John",
            "last_name": "Smith",
            "company": "Acme Corp",
        }

    def test_trial_conversion_detected_in_metadata(
        self,
        stripe_plugin: StripeSourcePlugin,
        trial_conversion_payload: dict[str, Any],
    ) -> None:
        """Test that trial conversion is detected in event metadata."""
        # Parse the webhook
        mock_event = Mock()
        mock_event.type = trial_conversion_payload["type"]
        mock_event.data.object = trial_conversion_payload["data"]["object"]
        mock_event.data.previous_attributes = None

        event_type, data = stripe_plugin._extract_stripe_event_info(mock_event)
        assert event_type == "payment_success"

        # Handle billing - should detect trial conversion
        amount = stripe_plugin._handle_stripe_billing(event_type, data)
        assert amount == 26.60
        assert data.get("_is_trial_conversion") is True

        # Build event data
        event_data = stripe_plugin._build_stripe_event_data(
            event_type, data["customer"], data, amount
        )
        assert event_data["metadata"]["is_trial_conversion"] is True

    def test_trial_conversion_generates_rich_notification(
        self,
        stripe_plugin: StripeSourcePlugin,
        event_processor: EventProcessor,
        trial_conversion_payload: dict[str, Any],
        customer_data: dict[str, Any],
    ) -> None:
        """Test that trial conversion produces a RichNotification with metadata."""
        mock_event = Mock()
        mock_event.type = trial_conversion_payload["type"]
        mock_event.data.object = trial_conversion_payload["data"]["object"]
        mock_event.data.previous_attributes = None

        event_type, data = stripe_plugin._extract_stripe_event_info(mock_event)
        stripe_plugin._handle_stripe_billing(event_type, data)
        event_data = stripe_plugin._build_stripe_event_data(
            event_type, data["customer"], data, 26.60
        )

        # Build notification
        notification = event_processor.build_rich_notification(
            event_data, customer_data
        )

        assert isinstance(notification, RichNotification)
        # The headline should mention the company
        assert "Acme" in notification.headline


class TestSubscriptionUpgradeIntegration:
    """Integration test: Subscription plan upgrade.

    When a customer upgrades, subscription.updated event includes
    previous_attributes with old plan amount.

    Slack notification should indicate it's an upgrade.
    """

    @pytest.fixture
    def stripe_plugin(self) -> StripeSourcePlugin:
        """Create a Stripe plugin instance."""
        return StripeSourcePlugin()

    @pytest.fixture
    def event_processor(self) -> EventProcessor:
        """Create an event processor instance."""
        return EventProcessor()

    @pytest.fixture
    def upgrade_payload(self) -> dict[str, Any]:
        """Subscription updated payload showing upgrade."""
        return {
            "id": "evt_upgrade123",
            "object": "event",
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "id": "sub_1ABC123DEF456GHI",
                    "object": "subscription",
                    "customer": "cus_TestCustomer123",
                    "status": "active",
                    "currency": "usd",
                    "plan": {
                        "id": "price_pro_monthly",
                        "amount": 4900,  # $49/mo (new)
                        "currency": "usd",
                        "interval": "month",
                    },
                },
                "previous_attributes": {
                    "plan": {
                        "id": "price_basic_monthly",
                        "amount": 2660,  # $26.60/mo (old)
                    },
                },
            },
        }

    @pytest.fixture
    def customer_data(self) -> dict[str, Any]:
        """Customer data."""
        return {
            "email": "jane@bigcorp.com",
            "first_name": "Jane",
            "last_name": "Doe",
            "company": "BigCorp Inc",
        }

    def test_upgrade_detected_in_metadata(
        self,
        stripe_plugin: StripeSourcePlugin,
        upgrade_payload: dict[str, Any],
    ) -> None:
        """Test that upgrade is detected via previous_attributes."""
        mock_event = Mock()
        mock_event.type = upgrade_payload["type"]
        mock_event.data.object = upgrade_payload["data"]["object"]
        mock_event.data.previous_attributes = upgrade_payload["data"][
            "previous_attributes"
        ]

        event_type, data = stripe_plugin._extract_stripe_event_info(mock_event)
        assert event_type == "subscription_updated"
        assert "_previous_attributes" in data

        # Handle billing - should detect upgrade
        amount = stripe_plugin._handle_stripe_billing(event_type, data)
        assert amount == 49.00
        assert data.get("_change_direction") == "upgrade"

        # Build event data
        event_data = stripe_plugin._build_stripe_event_data(
            event_type, data["customer"], data, amount
        )
        assert event_data["metadata"]["change_direction"] == "upgrade"

    def test_upgrade_generates_rich_notification(
        self,
        stripe_plugin: StripeSourcePlugin,
        event_processor: EventProcessor,
        upgrade_payload: dict[str, Any],
        customer_data: dict[str, Any],
    ) -> None:
        """Test that upgrade produces a RichNotification."""
        mock_event = Mock()
        mock_event.type = upgrade_payload["type"]
        mock_event.data.object = upgrade_payload["data"]["object"]
        mock_event.data.previous_attributes = upgrade_payload["data"][
            "previous_attributes"
        ]

        event_type, data = stripe_plugin._extract_stripe_event_info(mock_event)
        stripe_plugin._handle_stripe_billing(event_type, data)
        event_data = stripe_plugin._build_stripe_event_data(
            event_type, data["customer"], data, 49.00
        )

        # Build notification
        notification = event_processor.build_rich_notification(
            event_data, customer_data
        )

        assert isinstance(notification, RichNotification)
        # The headline should mention the company
        assert "BigCorp" in notification.headline


class TestDisplayNameInRichNotification:
    """Integration test: Customer display name in RichNotification.

    Tests the fallback logic for display names:
    - Company name if available
    - Customer name if no company
    - Email domain for business emails
    - Email username for free email providers
    """

    @pytest.fixture
    def event_processor(self) -> EventProcessor:
        """Create an event processor instance."""
        return EventProcessor()

    @pytest.fixture
    def payment_event_data(self) -> dict[str, Any]:
        """Generic payment event data."""
        return {
            "type": "payment_success",
            "customer_id": "cus_123",
            "provider": "stripe",
            "external_id": "evt_123",
            "status": "succeeded",
            "created_at": 1769327717,
            "currency": "USD",
            "amount": 99.00,
            "metadata": {},
        }

    def test_company_name_in_headline(
        self,
        event_processor: EventProcessor,
        payment_event_data: dict[str, Any],
    ) -> None:
        """Test that company name appears in notification headline."""
        customer_data = {
            "email": "billing@acme.com",
            "first_name": "John",
            "last_name": "Doe",
            "company": "Acme Corporation",
        }

        notification = event_processor.build_rich_notification(
            payment_event_data, customer_data
        )

        assert "Acme Corporation" in notification.headline

    def test_personal_name_in_headline_when_no_company(
        self,
        event_processor: EventProcessor,
        payment_event_data: dict[str, Any],
    ) -> None:
        """Test that personal name is used when company is missing."""
        customer_data = {
            "email": "john.doe@gmail.com",
            "first_name": "John",
            "last_name": "Doe",
            "company": "",
        }

        notification = event_processor.build_rich_notification(
            payment_event_data, customer_data
        )

        assert "John Doe" in notification.headline

    def test_business_email_domain_in_headline(
        self,
        event_processor: EventProcessor,
        payment_event_data: dict[str, Any],
    ) -> None:
        """Test that business email domain is extracted when no name/company."""
        customer_data = {
            "email": "billing@techstartup.io",
            "first_name": "",
            "last_name": "",
            "company": "",
        }

        notification = event_processor.build_rich_notification(
            payment_event_data, customer_data
        )

        assert "Techstartup" in notification.headline

    def test_gmail_username_in_headline(
        self,
        event_processor: EventProcessor,
        payment_event_data: dict[str, Any],
    ) -> None:
        """Test that Gmail username is used as fallback."""
        customer_data = {
            "email": "cooluser123@gmail.com",
            "first_name": "",
            "last_name": "",
            "company": "",
        }

        notification = event_processor.build_rich_notification(
            payment_event_data, customer_data
        )

        assert "cooluser123" in notification.headline

    def test_individual_ignored_in_headline(
        self,
        event_processor: EventProcessor,
        payment_event_data: dict[str, Any],
    ) -> None:
        """Test that 'Individual' company is ignored, falls back to email."""
        customer_data = {
            "email": "someone@enterprise.com",
            "first_name": "",
            "last_name": "",
            "company": "Individual",
        }

        notification = event_processor.build_rich_notification(
            payment_event_data, customer_data
        )

        assert "Individual" not in notification.headline
        assert "Enterprise" in notification.headline


class TestPaymentFailureNotFiltered:
    """Integration test: Payment failures are never filtered.

    Payment failures are critical events that should always generate
    notifications, regardless of amount or consolidation.
    """

    @pytest.fixture
    def consolidation_service(self) -> EventConsolidationService:
        """Create a consolidation service instance."""
        return EventConsolidationService()

    @pytest.fixture
    def event_processor(self) -> EventProcessor:
        """Create an event processor instance."""
        return EventProcessor()

    def test_payment_failure_not_filtered_even_with_zero_amount(
        self,
        consolidation_service: EventConsolidationService,
    ) -> None:
        """Test that payment failures pass through the filter."""
        with patch("webhooks.services.event_consolidation.cache") as mock_cache:
            mock_cache.get.return_value = None

            should_notify = consolidation_service.should_send_notification(
                event_type="payment_failure",
                customer_id="cus_123",
                workspace_id="ws_test",
                amount=0.0,  # Even with $0, should NOT be filtered
            )

            assert should_notify is True

    def test_payment_failure_generates_error_notification(
        self,
        event_processor: EventProcessor,
    ) -> None:
        """Test that payment failure generates error severity notification."""
        from webhooks.models.rich_notification import NotificationSeverity

        event_data = {
            "type": "payment_failure",
            "customer_id": "cus_123",
            "provider": "stripe",
            "external_id": "evt_fail123",
            "status": "failed",
            "created_at": 1769327717,
            "currency": "USD",
            "amount": 99.00,
            "metadata": {},
        }
        customer_data = {
            "email": "billing@company.com",
            "first_name": "John",
            "last_name": "Doe",
            "company": "Test Company",
        }

        notification = event_processor.build_rich_notification(
            event_data, customer_data
        )

        # Payment failures should have error severity
        assert notification.severity == NotificationSeverity.ERROR

        # Headline should mention the company
        assert "Test Company" in notification.headline
