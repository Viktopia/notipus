"""Tests for Stripe billing implementation.

This module contains tests for the Stripe billing features including:
- Checkout session creation
- Customer portal session creation
- Price fetching from Stripe
- Webhook handlers for checkout and billing events
"""

from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest
from core.services.stripe import StripeAPI, _safe_getattr
from webhooks.services.billing import BillingService


class TestSafeGetattr:
    """Tests for the _safe_getattr helper function.

    The Stripe SDK's __getattr__ raises KeyError instead of AttributeError
    for missing attributes on certain object types. This test class ensures
    _safe_getattr handles both exceptions correctly.
    """

    def test_returns_attribute_value_when_exists(self) -> None:
        """Test that _safe_getattr returns attribute value when it exists."""
        obj = MagicMock()
        obj.test_attr = "test_value"
        result = _safe_getattr(obj, "test_attr")
        assert result == "test_value"

    def test_returns_default_on_attribute_error(self) -> None:
        """Test that _safe_getattr returns default when attribute doesn't exist."""

        class SimpleObject:
            pass

        obj = SimpleObject()
        result = _safe_getattr(obj, "missing_attr", "default_value")
        assert result == "default_value"

    def test_returns_none_as_default(self) -> None:
        """Test that _safe_getattr returns None as default when not specified."""

        class SimpleObject:
            pass

        obj = SimpleObject()
        result = _safe_getattr(obj, "missing_attr")
        assert result is None

    def test_returns_default_on_key_error(self) -> None:
        """Test that _safe_getattr handles KeyError from Stripe-like objects.

        This simulates the Stripe SDK behavior where __getattr__ raises
        KeyError instead of AttributeError for missing attributes.
        """

        class StripeStyleObject:
            """Simulates Stripe SDK object that raises KeyError."""

            def __getattr__(self, name: str) -> Any:
                raise KeyError(name)

        obj = StripeStyleObject()
        result = _safe_getattr(obj, "current_period_start", "default")
        assert result == "default"

    def test_returns_none_on_key_error_without_default(self) -> None:
        """Test that _safe_getattr returns None on KeyError when no default."""

        class StripeStyleObject:
            """Simulates Stripe SDK object that raises KeyError."""

            def __getattr__(self, name: str) -> Any:
                raise KeyError(name)

        obj = StripeStyleObject()
        result = _safe_getattr(obj, "current_period_start")
        assert result is None


class TestStripeAPICheckout:
    """Tests for Stripe Checkout Session functionality."""

    @pytest.fixture
    def stripe_api(self) -> StripeAPI:
        """Create a StripeAPI instance for testing.

        Returns:
            Configured StripeAPI instance.
        """
        return StripeAPI()

    @pytest.fixture
    def mock_workspace(self) -> MagicMock:
        """Create a mock workspace for testing.

        Returns:
            Mock workspace with standard attributes.
        """
        workspace = MagicMock()
        workspace.id = 1
        workspace.uuid = "test-uuid-1234"
        workspace.name = "Test Workspace"
        workspace.stripe_customer_id = "cus_test123"
        workspace.members.exists.return_value = True
        first_member = MagicMock()
        first_member.user = MagicMock(email="test@example.com")
        workspace.members.first.return_value = first_member
        return workspace

    @patch("core.services.stripe.stripe.checkout.Session.create")
    def test_create_checkout_session_success(
        self, mock_create: MagicMock, stripe_api: StripeAPI
    ) -> None:
        """Test successful checkout session creation.

        Args:
            mock_create: Mock for Stripe checkout session create.
            stripe_api: StripeAPI fixture.
        """
        mock_session = Mock()
        mock_session.id = "cs_test123"
        mock_session.url = "https://checkout.stripe.com/pay/cs_test123"
        mock_session.customer = "cus_test123"
        mock_session.status = "open"
        mock_create.return_value = mock_session

        result = stripe_api.create_checkout_session(
            customer_id="cus_test123",
            price_id="price_test123",
        )

        assert result is not None
        assert result["id"] == "cs_test123"
        assert result["url"] == "https://checkout.stripe.com/pay/cs_test123"
        assert result["customer"] == "cus_test123"
        mock_create.assert_called_once()

    @patch("core.services.stripe.stripe.checkout.Session.create")
    def test_create_checkout_session_with_metadata(
        self, mock_create: MagicMock, stripe_api: StripeAPI
    ) -> None:
        """Test checkout session creation with metadata.

        Args:
            mock_create: Mock for Stripe checkout session create.
            stripe_api: StripeAPI fixture.
        """
        mock_session = Mock()
        mock_session.id = "cs_test123"
        mock_session.url = "https://checkout.stripe.com/pay/cs_test123"
        mock_session.customer = "cus_test123"
        mock_session.status = "open"
        mock_create.return_value = mock_session

        metadata = {"organization_id": "1", "plan_name": "pro"}
        result = stripe_api.create_checkout_session(
            customer_id="cus_test123",
            price_id="price_test123",
            metadata=metadata,
        )

        assert result is not None
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["metadata"] == metadata

    @patch("core.services.stripe.stripe.checkout.Session.create")
    def test_create_checkout_session_stripe_error(
        self, mock_create: MagicMock, stripe_api: StripeAPI
    ) -> None:
        """Test checkout session creation with Stripe error.

        Args:
            mock_create: Mock for Stripe checkout session create.
            stripe_api: StripeAPI fixture.
        """
        from stripe import StripeError

        mock_create.side_effect = StripeError("Test error")

        result = stripe_api.create_checkout_session(
            customer_id="cus_test123",
            price_id="price_test123",
        )

        assert result is None

    @patch("core.services.stripe.stripe.checkout.Session.create")
    def test_create_checkout_session_with_trial_period(
        self, mock_create: MagicMock, stripe_api: StripeAPI
    ) -> None:
        """Test checkout session creation with trial period.

        Verifies that trial_period_days is passed to Stripe subscription_data.

        Args:
            mock_create: Mock for Stripe checkout session create.
            stripe_api: StripeAPI fixture.
        """
        mock_session = Mock()
        mock_session.id = "cs_test123"
        mock_session.url = "https://checkout.stripe.com/pay/cs_test123"
        mock_session.customer = "cus_test123"
        mock_session.status = "open"
        mock_create.return_value = mock_session

        result = stripe_api.create_checkout_session(
            customer_id="cus_test123",
            price_id="price_test123",
            trial_period_days=14,
        )

        assert result is not None
        call_kwargs = mock_create.call_args[1]
        assert "subscription_data" in call_kwargs
        assert call_kwargs["subscription_data"]["trial_period_days"] == 14

    @patch("core.services.stripe.stripe.checkout.Session.create")
    def test_create_checkout_session_with_trial_and_metadata(
        self, mock_create: MagicMock, stripe_api: StripeAPI
    ) -> None:
        """Test checkout session with both trial period and metadata.

        Verifies that subscription_data contains both trial_period_days and metadata.

        Args:
            mock_create: Mock for Stripe checkout session create.
            stripe_api: StripeAPI fixture.
        """
        mock_session = Mock()
        mock_session.id = "cs_test123"
        mock_session.url = "https://checkout.stripe.com/pay/cs_test123"
        mock_session.customer = "cus_test123"
        mock_session.status = "open"
        mock_create.return_value = mock_session

        metadata = {"workspace_id": "123"}
        result = stripe_api.create_checkout_session(
            customer_id="cus_test123",
            price_id="price_test123",
            metadata=metadata,
            trial_period_days=14,
        )

        assert result is not None
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["subscription_data"]["trial_period_days"] == 14
        assert call_kwargs["subscription_data"]["metadata"] == metadata
        assert call_kwargs["metadata"] == metadata


class TestStripeAPIPortal:
    """Tests for Stripe Customer Portal functionality."""

    @pytest.fixture
    def stripe_api(self) -> StripeAPI:
        """Create a StripeAPI instance for testing.

        Returns:
            Configured StripeAPI instance.
        """
        return StripeAPI()

    @patch("core.services.stripe.stripe.billing_portal.Session.create")
    def test_create_portal_session_success(
        self, mock_create: MagicMock, stripe_api: StripeAPI
    ) -> None:
        """Test successful portal session creation.

        Args:
            mock_create: Mock for Stripe billing portal session create.
            stripe_api: StripeAPI fixture.
        """
        mock_session = Mock()
        mock_session.id = "bps_test123"
        mock_session.url = "https://billing.stripe.com/session/bps_test123"
        mock_session.customer = "cus_test123"
        mock_create.return_value = mock_session

        result = stripe_api.create_portal_session(customer_id="cus_test123")

        assert result is not None
        assert result["id"] == "bps_test123"
        assert result["url"] == "https://billing.stripe.com/session/bps_test123"
        mock_create.assert_called_once()

    @patch("core.services.stripe.stripe.billing_portal.Session.create")
    def test_create_portal_session_with_return_url(
        self, mock_create: MagicMock, stripe_api: StripeAPI
    ) -> None:
        """Test portal session creation with custom return URL.

        Args:
            mock_create: Mock for Stripe billing portal session create.
            stripe_api: StripeAPI fixture.
        """
        mock_session = Mock()
        mock_session.id = "bps_test123"
        mock_session.url = "https://billing.stripe.com/session/bps_test123"
        mock_session.customer = "cus_test123"
        mock_create.return_value = mock_session

        return_url = "https://example.com/billing/"
        result = stripe_api.create_portal_session(
            customer_id="cus_test123", return_url=return_url
        )

        assert result is not None
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["return_url"] == return_url

    @patch("core.services.stripe.stripe.billing_portal.Session.create")
    def test_create_portal_session_stripe_error(
        self, mock_create: MagicMock, stripe_api: StripeAPI
    ) -> None:
        """Test portal session creation with Stripe error.

        Args:
            mock_create: Mock for Stripe billing portal session create.
            stripe_api: StripeAPI fixture.
        """
        from stripe import StripeError

        mock_create.side_effect = StripeError("Test error")

        result = stripe_api.create_portal_session(customer_id="cus_test123")

        assert result is None


class TestStripeAPIPrices:
    """Tests for Stripe price fetching functionality."""

    @pytest.fixture
    def stripe_api(self) -> StripeAPI:
        """Create a StripeAPI instance for testing.

        Returns:
            Configured StripeAPI instance.
        """
        return StripeAPI()

    @patch("core.services.stripe.stripe.Price.list")
    def test_list_prices_success(
        self, mock_list: MagicMock, stripe_api: StripeAPI
    ) -> None:
        """Test successful price listing.

        Args:
            mock_list: Mock for Stripe price list.
            stripe_api: StripeAPI fixture.
        """
        mock_product = Mock()
        mock_product.id = "prod_test123"
        mock_product.name = "Pro Plan"
        mock_product.description = "Professional plan"
        mock_product.active = True
        mock_product.metadata = {"features": '["Feature 1", "Feature 2"]'}

        mock_price = Mock()
        mock_price.id = "price_test123"
        mock_price.product = mock_product
        mock_price.unit_amount = 9900
        mock_price.currency = "usd"
        mock_price.recurring = Mock(interval="month", interval_count=1)

        mock_list.return_value = Mock(data=[mock_price])

        result = stripe_api.list_prices()

        assert len(result) == 1
        assert result[0]["id"] == "price_test123"
        assert result[0]["product_name"] == "Pro Plan"
        assert result[0]["unit_amount"] == 9900

    @patch("core.services.stripe.stripe.Price.list")
    def test_list_prices_filters_inactive_products(
        self, mock_list: MagicMock, stripe_api: StripeAPI
    ) -> None:
        """Test that inactive products are filtered out.

        Args:
            mock_list: Mock for Stripe price list.
            stripe_api: StripeAPI fixture.
        """
        mock_product = Mock()
        mock_product.id = "prod_test123"
        mock_product.active = False

        mock_price = Mock()
        mock_price.id = "price_test123"
        mock_price.product = mock_product

        mock_list.return_value = Mock(data=[mock_price])

        result = stripe_api.list_prices(active_only=True)

        assert len(result) == 0

    @patch("core.services.stripe.stripe.Price.list")
    def test_list_prices_stripe_error(
        self, mock_list: MagicMock, stripe_api: StripeAPI
    ) -> None:
        """Test price listing with Stripe error.

        Args:
            mock_list: Mock for Stripe price list.
            stripe_api: StripeAPI fixture.
        """
        from stripe import StripeError

        mock_list.side_effect = StripeError("Test error")

        result = stripe_api.list_prices()

        assert result == []


class TestStripeAPIGetOrCreateCustomer:
    """Tests for get_or_create_customer functionality."""

    @pytest.fixture
    def stripe_api(self) -> StripeAPI:
        """Create a StripeAPI instance for testing.

        Returns:
            Configured StripeAPI instance.
        """
        return StripeAPI()

    @pytest.fixture
    def mock_workspace(self) -> MagicMock:
        """Create a mock workspace for testing.

        Returns:
            Mock workspace with standard attributes.
        """
        workspace = MagicMock()
        workspace.id = 1
        workspace.uuid = "test-uuid-1234"
        workspace.name = "Test Workspace"
        workspace.stripe_customer_id = ""
        workspace.members.exists.return_value = True
        first_member = MagicMock()
        first_member.user = MagicMock(email="test@example.com")
        workspace.members.first.return_value = first_member
        return workspace

    @patch("core.services.stripe.stripe.Customer.create")
    def test_creates_new_customer_when_none_exists(
        self,
        mock_create: MagicMock,
        stripe_api: StripeAPI,
        mock_workspace: MagicMock,
    ) -> None:
        """Test customer creation when workspace has no Stripe customer.

        Args:
            mock_create: Mock for Stripe customer create.
            stripe_api: StripeAPI fixture.
            mock_workspace: Mock workspace fixture.
        """
        mock_customer = Mock()
        mock_customer.id = "cus_new123"
        mock_customer.to_dict.return_value = {"id": "cus_new123"}
        mock_create.return_value = mock_customer

        result = stripe_api.get_or_create_customer(mock_workspace)

        assert result is not None
        assert result["id"] == "cus_new123"
        mock_create.assert_called_once()
        mock_workspace.save.assert_called_once()

    @patch("core.services.stripe.stripe.Customer.retrieve")
    def test_retrieves_existing_customer(
        self,
        mock_retrieve: MagicMock,
        stripe_api: StripeAPI,
        mock_workspace: MagicMock,
    ) -> None:
        """Test retrieval of existing Stripe customer.

        Args:
            mock_retrieve: Mock for Stripe customer retrieve.
            stripe_api: StripeAPI fixture.
            mock_workspace: Mock workspace fixture.
        """
        mock_workspace.stripe_customer_id = "cus_existing123"

        mock_customer = Mock()
        mock_customer.id = "cus_existing123"
        mock_customer.deleted = False
        mock_customer.to_dict.return_value = {"id": "cus_existing123"}
        mock_retrieve.return_value = mock_customer

        result = stripe_api.get_or_create_customer(mock_workspace)

        assert result is not None
        assert result["id"] == "cus_existing123"
        mock_retrieve.assert_called_once_with("cus_existing123")


class TestBillingServiceWebhooks:
    """Tests for billing service webhook handlers."""

    def test_handle_checkout_completed_success(self) -> None:
        """Test successful checkout completed handler."""
        session_data: dict[str, Any] = {
            "customer": "cus_test123",
            "subscription": "sub_test123",
            "metadata": {
                "organization_id": "1",
                "plan_name": "pro",
            },
        }

        with patch.object(
            BillingService, "_get_customer_id", return_value="cus_test123"
        ):
            with patch("core.models.Workspace.objects.filter") as mock_filter:
                mock_filter.return_value.update.return_value = 1
                # This should not raise
                BillingService.handle_checkout_completed(session_data)
                mock_filter.assert_called()

    def test_handle_checkout_completed_missing_customer(self) -> None:
        """Test checkout completed with missing customer ID."""
        session_data: dict[str, Any] = {
            "subscription": "sub_test123",
            "metadata": {"plan_name": "pro"},
        }

        # Should not raise, just log error
        BillingService.handle_checkout_completed(session_data)

    def test_handle_trial_ending(self) -> None:
        """Test trial ending handler."""
        subscription_data: dict[str, Any] = {
            "customer": "cus_test123",
            "trial_end": 1704067200,
        }

        with patch("core.models.Workspace.objects.filter") as mock_filter:
            mock_ws = MagicMock(name="Test Workspace")
            mock_filter.return_value.first.return_value = mock_ws
            # Should not raise
            BillingService.handle_trial_ending(subscription_data)

    def test_handle_invoice_paid(self) -> None:
        """Test invoice paid handler."""
        invoice_data: dict[str, Any] = {
            "customer": "cus_test123",
            "period_end": 1704067200,
        }

        with patch("core.models.Workspace.objects.filter") as mock_filter:
            mock_filter.return_value.update.return_value = 1
            BillingService.handle_invoice_paid(invoice_data)
            mock_filter.assert_called_once_with(stripe_customer_id="cus_test123")

    def test_handle_payment_action_required(self) -> None:
        """Test payment action required handler."""
        invoice_data: dict[str, Any] = {
            "customer": "cus_test123",
            "hosted_invoice_url": "https://invoice.stripe.com/i/test123",
        }

        with patch("core.models.Workspace.objects.filter") as mock_filter:
            mock_ws = MagicMock(name="Test Workspace")
            mock_filter.return_value.first.return_value = mock_ws
            # Should not raise
            BillingService.handle_payment_action_required(invoice_data)


class TestStripeAPIInvoices:
    """Tests for Stripe invoice fetching functionality."""

    @pytest.fixture
    def stripe_api(self) -> StripeAPI:
        """Create a StripeAPI instance for testing.

        Returns:
            Configured StripeAPI instance.
        """
        return StripeAPI()

    @patch("core.services.stripe.stripe.Invoice.list")
    def test_get_invoices_success(
        self, mock_list: MagicMock, stripe_api: StripeAPI
    ) -> None:
        """Test successful invoice retrieval.

        Args:
            mock_list: Mock for Stripe invoice list.
            stripe_api: StripeAPI fixture.
        """
        mock_invoice = Mock()
        mock_invoice.id = "in_test123"
        mock_invoice.number = "INV-001"
        mock_invoice.status = "paid"
        mock_invoice.amount_due = 9900
        mock_invoice.amount_paid = 9900
        mock_invoice.currency = "usd"
        mock_invoice.created = 1704067200
        mock_invoice.period_start = 1704067200
        mock_invoice.period_end = 1706745600
        mock_invoice.hosted_invoice_url = "https://invoice.stripe.com/i/test123"
        mock_invoice.invoice_pdf = "https://invoice.stripe.com/i/test123/pdf"

        mock_list.return_value = Mock(data=[mock_invoice])

        result = stripe_api.get_invoices("cus_test123")

        assert len(result) == 1
        assert result[0]["id"] == "in_test123"
        assert result[0]["number"] == "INV-001"
        assert result[0]["amount_paid"] == 9900

    @patch("core.services.stripe.stripe.Invoice.list")
    def test_get_invoices_stripe_error(
        self, mock_list: MagicMock, stripe_api: StripeAPI
    ) -> None:
        """Test invoice retrieval with Stripe error.

        Args:
            mock_list: Mock for Stripe invoice list.
            stripe_api: StripeAPI fixture.
        """
        from stripe import StripeError

        mock_list.side_effect = StripeError("Test error")

        result = stripe_api.get_invoices("cus_test123")

        assert result == []


class TestStripeAPISubscriptions:
    """Tests for Stripe subscription fetching functionality."""

    @pytest.fixture
    def stripe_api(self) -> StripeAPI:
        """Create a StripeAPI instance for testing.

        Returns:
            Configured StripeAPI instance.
        """
        return StripeAPI()

    @patch("core.services.stripe.stripe.Subscription.list")
    def test_get_customer_subscriptions_success(
        self, mock_list: MagicMock, stripe_api: StripeAPI
    ) -> None:
        """Test successful subscription retrieval.

        Args:
            mock_list: Mock for Stripe subscription list.
            stripe_api: StripeAPI fixture.
        """
        mock_product = Mock()
        mock_product.name = "Pro Plan"

        mock_price = Mock()
        mock_price.id = "price_test123"
        mock_price.product = mock_product
        mock_price.unit_amount = 9900
        mock_price.currency = "usd"

        mock_item = Mock()
        mock_item.price = mock_price
        mock_item.quantity = 1

        mock_subscription = Mock()
        mock_subscription.id = "sub_test123"
        mock_subscription.status = "active"
        mock_subscription.current_period_start = 1704067200
        mock_subscription.current_period_end = 1706745600
        mock_subscription.cancel_at_period_end = False
        mock_subscription.canceled_at = None
        mock_subscription.items = Mock(data=[mock_item])

        mock_list.return_value = Mock(data=[mock_subscription])

        result = stripe_api.get_customer_subscriptions("cus_test123")

        assert len(result) == 1
        assert result[0]["id"] == "sub_test123"
        assert result[0]["status"] == "active"

    @patch("core.services.stripe.stripe.Subscription.list")
    def test_get_customer_subscriptions_stripe_error(
        self, mock_list: MagicMock, stripe_api: StripeAPI
    ) -> None:
        """Test subscription retrieval with Stripe error.

        Args:
            mock_list: Mock for Stripe subscription list.
            stripe_api: StripeAPI fixture.
        """
        from stripe import StripeError

        mock_list.side_effect = StripeError("Test error")

        result = stripe_api.get_customer_subscriptions("cus_test123")

        assert result == []


class TestStripeAPIArchive:
    """Tests for Stripe product and price archiving functionality."""

    @pytest.fixture
    def stripe_api(self) -> StripeAPI:
        """Create a StripeAPI instance for testing.

        Returns:
            Configured StripeAPI instance.
        """
        return StripeAPI()

    @patch("core.services.stripe.stripe.Product.modify")
    def test_archive_product_success(
        self, mock_modify: MagicMock, stripe_api: StripeAPI
    ) -> None:
        """Test successful product archiving.

        Args:
            mock_modify: Mock for Stripe product modify.
            stripe_api: StripeAPI fixture.
        """
        mock_modify.return_value = Mock()

        result = stripe_api.archive_product("prod_test123")

        assert result is True
        mock_modify.assert_called_once_with("prod_test123", active=False)

    @patch("core.services.stripe.stripe.Product.modify")
    def test_archive_product_stripe_error(
        self, mock_modify: MagicMock, stripe_api: StripeAPI
    ) -> None:
        """Test product archiving with Stripe error.

        Args:
            mock_modify: Mock for Stripe product modify.
            stripe_api: StripeAPI fixture.
        """
        from stripe import StripeError

        mock_modify.side_effect = StripeError("Test error")

        result = stripe_api.archive_product("prod_test123")

        assert result is False

    @patch("core.services.stripe.stripe.Price.modify")
    def test_archive_price_success(
        self, mock_modify: MagicMock, stripe_api: StripeAPI
    ) -> None:
        """Test successful price archiving.

        Args:
            mock_modify: Mock for Stripe price modify.
            stripe_api: StripeAPI fixture.
        """
        mock_modify.return_value = Mock()

        result = stripe_api.archive_price("price_test123")

        assert result is True
        mock_modify.assert_called_once_with("price_test123", active=False)

    @patch("core.services.stripe.stripe.Price.modify")
    def test_archive_price_stripe_error(
        self, mock_modify: MagicMock, stripe_api: StripeAPI
    ) -> None:
        """Test price archiving with Stripe error.

        Args:
            mock_modify: Mock for Stripe price modify.
            stripe_api: StripeAPI fixture.
        """
        from stripe import StripeError

        mock_modify.side_effect = StripeError("Test error")

        result = stripe_api.archive_price("price_test123")

        assert result is False

    @patch("core.services.stripe.stripe.Price.list")
    def test_list_prices_for_product_success(
        self, mock_list: MagicMock, stripe_api: StripeAPI
    ) -> None:
        """Test successful price listing for a product.

        Args:
            mock_list: Mock for Stripe price list.
            stripe_api: StripeAPI fixture.
        """
        mock_price = Mock()
        mock_price.id = "price_test123"
        mock_price.product = "prod_test123"
        mock_price.unit_amount = 2900
        mock_price.currency = "usd"
        mock_price.lookup_key = "basic_monthly"
        mock_price.active = True
        mock_price.recurring = Mock(interval="month", interval_count=1)

        mock_list.return_value = Mock(data=[mock_price])

        result = stripe_api.list_prices_for_product("prod_test123")

        assert len(result) == 1
        assert result[0]["id"] == "price_test123"
        assert result[0]["unit_amount"] == 2900
        assert result[0]["recurring"]["interval"] == "month"
        mock_list.assert_called_once_with(
            product="prod_test123", limit=100, active=True
        )

    @patch("core.services.stripe.stripe.Price.list")
    def test_list_prices_for_product_stripe_error(
        self, mock_list: MagicMock, stripe_api: StripeAPI
    ) -> None:
        """Test price listing with Stripe error.

        Args:
            mock_list: Mock for Stripe price list.
            stripe_api: StripeAPI fixture.
        """
        from stripe import StripeError

        mock_list.side_effect = StripeError("Test error")

        result = stripe_api.list_prices_for_product("prod_test123")

        assert result == []
