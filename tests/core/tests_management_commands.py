"""Tests for management commands.

This module contains comprehensive tests for the setup_stripe_plans management
command, including dry-run mode, force mode, and plan filtering.
"""

from decimal import Decimal
from io import StringIO
from unittest.mock import MagicMock, Mock, patch

import pytest
from core.models import Plan
from django.core.management import call_command
from django.core.management.base import CommandError


@pytest.fixture
def sample_plan(db) -> Plan:
    """Create a sample paid plan for testing.

    Args:
        db: Database access fixture from pytest-django.

    Returns:
        A Plan instance with sample data.
    """
    # Delete any existing plans to avoid unique constraint violations
    Plan.objects.all().delete()
    return Plan.objects.create(
        name="basic",
        display_name="Basic Plan",
        description="A basic plan for small teams",
        price_monthly=Decimal("29.00"),
        price_yearly=Decimal("290.00"),
        max_users=5,
        max_integrations=10,
        max_monthly_notifications=10000,
        features=["Feature 1", "Feature 2"],
        is_active=True,
    )


@pytest.fixture
def sample_plans(db) -> list[Plan]:
    """Create multiple sample plans for testing.

    Args:
        db: Database access fixture from pytest-django.

    Returns:
        List of Plan instances.
    """
    # Delete any existing plans to avoid unique constraint violations
    Plan.objects.all().delete()
    plans = [
        Plan.objects.create(
            name="basic",
            display_name="Basic Plan",
            description="Basic plan",
            price_monthly=Decimal("29.00"),
            price_yearly=Decimal("290.00"),
            max_users=5,
            max_integrations=10,
            max_monthly_notifications=10000,
            features=["Feature 1"],
            is_active=True,
        ),
        Plan.objects.create(
            name="pro",
            display_name="Pro Plan",
            description="Pro plan",
            price_monthly=Decimal("99.00"),
            price_yearly=Decimal("990.00"),
            max_users=25,
            max_integrations=50,
            max_monthly_notifications=100000,
            features=["Feature 1", "Feature 2"],
            is_active=True,
        ),
        Plan.objects.create(
            name="enterprise",
            display_name="Enterprise Plan",
            description="Enterprise plan",
            price_monthly=Decimal("299.00"),
            price_yearly=Decimal("2990.00"),
            max_users=100,
            max_integrations=200,
            max_monthly_notifications=1000000,
            features=["Feature 1", "Feature 2", "Feature 3"],
            is_active=True,
        ),
    ]
    return plans


@pytest.fixture
def free_plan(db) -> Plan:
    """Create a free plan for testing.

    Args:
        db: Database access fixture from pytest-django.

    Returns:
        A Plan instance with zero price.
    """
    # Delete any existing plans to avoid unique constraint violations
    Plan.objects.all().delete()
    return Plan.objects.create(
        name="free",
        display_name="Free Plan",
        description="Free tier",
        price_monthly=Decimal("0.00"),
        price_yearly=Decimal("0.00"),
        max_users=1,
        max_integrations=1,
        max_monthly_notifications=20,
        features=[],
        is_active=True,
    )


@pytest.fixture
def mock_stripe_api() -> MagicMock:
    """Create a mock StripeAPI instance.

    Returns:
        MagicMock configured for StripeAPI.
    """
    mock = MagicMock()
    mock.get_account_info.return_value = {"id": "acct_test123"}
    mock.get_product_by_metadata.return_value = None
    mock.get_price_by_lookup_key.return_value = None
    mock.create_product.return_value = {
        "id": "prod_test123",
        "name": "Test Product",
        "description": "Test description",
        "metadata": {},
        "active": True,
    }
    mock.create_price.return_value = {
        "id": "price_test123",
        "product": "prod_test123",
        "unit_amount": 2900,
        "currency": "usd",
        "recurring": {"interval": "month", "interval_count": 1},
        "lookup_key": "basic_monthly",
        "active": True,
    }
    return mock


class TestSetupStripePlansCommand:
    """Tests for the setup_stripe_plans management command."""

    @patch("core.management.commands.setup_stripe_plans.StripeAPI")
    def test_command_fails_without_stripe_connection(
        self,
        mock_stripe_class: MagicMock,
        sample_plan: Plan,
    ) -> None:
        """Test that command fails if Stripe connection fails.

        Args:
            mock_stripe_class: Mock for StripeAPI class.
            sample_plan: Sample plan fixture.
        """
        mock_api = MagicMock()
        mock_api.get_account_info.return_value = None
        mock_stripe_class.return_value = mock_api

        out = StringIO()

        with pytest.raises(CommandError) as exc_info:
            call_command("setup_stripe_plans", stdout=out)

        assert "Failed to connect to Stripe" in str(exc_info.value)

    @patch("core.management.commands.setup_stripe_plans.StripeAPI")
    def test_command_dry_run_no_changes(
        self,
        mock_stripe_class: MagicMock,
        mock_stripe_api: MagicMock,
        sample_plan: Plan,
    ) -> None:
        """Test that dry-run mode doesn't make any changes.

        Args:
            mock_stripe_class: Mock for StripeAPI class.
            mock_stripe_api: Mock StripeAPI instance.
            sample_plan: Sample plan fixture.
        """
        mock_stripe_class.return_value = mock_stripe_api

        out = StringIO()
        call_command("setup_stripe_plans", "--dry-run", stdout=out)

        output = out.getvalue()

        # Verify dry run message appears
        assert "DRY RUN MODE" in output

        # Verify no Stripe API calls were made for creation
        mock_stripe_api.create_product.assert_not_called()
        mock_stripe_api.create_price.assert_not_called()

        # Verify plan was not updated
        sample_plan.refresh_from_db()
        assert sample_plan.stripe_price_id_monthly == ""
        assert sample_plan.stripe_price_id_yearly == ""

    @patch("core.management.commands.setup_stripe_plans.StripeAPI")
    def test_command_creates_product_and_prices(
        self,
        mock_stripe_class: MagicMock,
        mock_stripe_api: MagicMock,
        sample_plan: Plan,
    ) -> None:
        """Test that command creates product and prices in Stripe.

        Args:
            mock_stripe_class: Mock for StripeAPI class.
            mock_stripe_api: Mock StripeAPI instance.
            sample_plan: Sample plan fixture.
        """
        # Configure mock to return different price IDs for monthly/yearly
        mock_stripe_api.create_price.side_effect = [
            {
                "id": "price_monthly_123",
                "product": "prod_test123",
                "unit_amount": 2900,
                "currency": "usd",
                "recurring": {"interval": "month", "interval_count": 1},
                "lookup_key": "basic_monthly",
                "active": True,
            },
            {
                "id": "price_yearly_456",
                "product": "prod_test123",
                "unit_amount": 29000,
                "currency": "usd",
                "recurring": {"interval": "year", "interval_count": 1},
                "lookup_key": "basic_yearly",
                "active": True,
            },
        ]
        mock_stripe_class.return_value = mock_stripe_api

        out = StringIO()
        call_command("setup_stripe_plans", stdout=out)

        output = out.getvalue()

        # Verify product was created
        mock_stripe_api.create_product.assert_called_once()
        call_args = mock_stripe_api.create_product.call_args
        assert call_args.kwargs["name"] == "Basic Plan"
        assert "basic" in call_args.kwargs["metadata"]["plan_name"]

        # Verify both prices were created
        assert mock_stripe_api.create_price.call_count == 2

        # Verify plan was updated
        sample_plan.refresh_from_db()
        assert sample_plan.stripe_price_id_monthly == "price_monthly_123"
        assert sample_plan.stripe_price_id_yearly == "price_yearly_456"

        # Verify summary
        assert "Created 1 product" in output
        assert "Created 2 price" in output

    @patch("core.management.commands.setup_stripe_plans.StripeAPI")
    def test_command_skips_free_plans(
        self,
        mock_stripe_class: MagicMock,
        mock_stripe_api: MagicMock,
        free_plan: Plan,
    ) -> None:
        """Test that command skips free plans (price_monthly = 0).

        Args:
            mock_stripe_class: Mock for StripeAPI class.
            mock_stripe_api: Mock StripeAPI instance.
            free_plan: Free plan fixture.
        """
        mock_stripe_class.return_value = mock_stripe_api

        out = StringIO()
        call_command("setup_stripe_plans", stdout=out)

        output = out.getvalue()

        # Verify no plans were processed
        assert "No paid plans found" in output
        mock_stripe_api.create_product.assert_not_called()
        mock_stripe_api.create_price.assert_not_called()

    @patch("core.management.commands.setup_stripe_plans.StripeAPI")
    def test_command_filters_by_plan_name(
        self,
        mock_stripe_class: MagicMock,
        mock_stripe_api: MagicMock,
        sample_plans: list[Plan],
    ) -> None:
        """Test that --plan option filters to specific plan.

        Args:
            mock_stripe_class: Mock for StripeAPI class.
            mock_stripe_api: Mock StripeAPI instance.
            sample_plans: Multiple sample plans fixture.
        """
        mock_stripe_api.create_price.side_effect = [
            {
                "id": "price_pro_monthly",
                "product": "prod_pro",
                "unit_amount": 9900,
                "currency": "usd",
                "recurring": {"interval": "month", "interval_count": 1},
                "lookup_key": "pro_monthly",
                "active": True,
            },
            {
                "id": "price_pro_yearly",
                "product": "prod_pro",
                "unit_amount": 99000,
                "currency": "usd",
                "recurring": {"interval": "year", "interval_count": 1},
                "lookup_key": "pro_yearly",
                "active": True,
            },
        ]
        mock_stripe_class.return_value = mock_stripe_api

        out = StringIO()
        call_command("setup_stripe_plans", "--plan", "pro", stdout=out)

        output = out.getvalue()

        # Verify only pro plan was processed
        assert "Found 1 plan" in output
        assert "Pro Plan" in output
        mock_stripe_api.create_product.assert_called_once()

        # Verify only pro plan was updated
        pro_plan = Plan.objects.get(name="pro")
        basic_plan = Plan.objects.get(name="basic")

        assert pro_plan.stripe_price_id_monthly == "price_pro_monthly"
        assert basic_plan.stripe_price_id_monthly == ""

    @patch("core.management.commands.setup_stripe_plans.StripeAPI")
    def test_command_invalid_plan_name(
        self,
        mock_stripe_class: MagicMock,
        mock_stripe_api: MagicMock,
        sample_plan: Plan,
    ) -> None:
        """Test that command fails with invalid plan name.

        Args:
            mock_stripe_class: Mock for StripeAPI class.
            mock_stripe_api: Mock StripeAPI instance.
            sample_plan: Sample plan fixture.
        """
        mock_stripe_class.return_value = mock_stripe_api

        out = StringIO()

        with pytest.raises(CommandError) as exc_info:
            call_command("setup_stripe_plans", "--plan", "nonexistent", stdout=out)

        assert "not found" in str(exc_info.value)

    @patch("core.management.commands.setup_stripe_plans.StripeAPI")
    def test_command_skips_existing_prices(
        self,
        mock_stripe_class: MagicMock,
        mock_stripe_api: MagicMock,
        sample_plan: Plan,
    ) -> None:
        """Test that command skips plans with existing Stripe prices.

        Args:
            mock_stripe_class: Mock for StripeAPI class.
            mock_stripe_api: Mock StripeAPI instance.
            sample_plan: Sample plan fixture.
        """
        # Set up plan with existing Stripe IDs
        sample_plan.stripe_price_id_monthly = "price_existing_monthly"
        sample_plan.stripe_price_id_yearly = "price_existing_yearly"
        sample_plan.save()

        # Mock that prices exist in Stripe
        mock_stripe_api.get_price_by_lookup_key.return_value = {
            "id": "price_existing_monthly",
            "product_id": "prod_existing",
            "unit_amount": 2900,
            "currency": "usd",
        }
        mock_stripe_class.return_value = mock_stripe_api

        out = StringIO()
        call_command("setup_stripe_plans", stdout=out)

        output = out.getvalue()

        # Verify plan was skipped
        assert "Skipping" in output
        assert "Skipped 1 plan" in output
        mock_stripe_api.create_product.assert_not_called()
        mock_stripe_api.create_price.assert_not_called()

    @patch("core.management.commands.setup_stripe_plans.StripeAPI")
    def test_command_force_recreates_prices(
        self,
        mock_stripe_class: MagicMock,
        mock_stripe_api: MagicMock,
        sample_plan: Plan,
    ) -> None:
        """Test that --force option recreates prices even if they exist.

        Args:
            mock_stripe_class: Mock for StripeAPI class.
            mock_stripe_api: Mock StripeAPI instance.
            sample_plan: Sample plan fixture.
        """
        # Set up plan with existing Stripe IDs
        sample_plan.stripe_price_id_monthly = "price_old_monthly"
        sample_plan.stripe_price_id_yearly = "price_old_yearly"
        sample_plan.save()

        mock_stripe_api.create_price.side_effect = [
            {
                "id": "price_new_monthly",
                "product": "prod_test123",
                "unit_amount": 2900,
                "currency": "usd",
                "recurring": {"interval": "month", "interval_count": 1},
                "lookup_key": "basic_monthly",
                "active": True,
            },
            {
                "id": "price_new_yearly",
                "product": "prod_test123",
                "unit_amount": 29000,
                "currency": "usd",
                "recurring": {"interval": "year", "interval_count": 1},
                "lookup_key": "basic_yearly",
                "active": True,
            },
        ]
        mock_stripe_class.return_value = mock_stripe_api

        out = StringIO()
        call_command("setup_stripe_plans", "--force", stdout=out)

        # Verify prices were recreated
        assert mock_stripe_api.create_price.call_count == 2

        # Verify plan was updated with new IDs
        sample_plan.refresh_from_db()
        assert sample_plan.stripe_price_id_monthly == "price_new_monthly"
        assert sample_plan.stripe_price_id_yearly == "price_new_yearly"

    @patch("core.management.commands.setup_stripe_plans.StripeAPI")
    def test_command_uses_existing_product(
        self,
        mock_stripe_class: MagicMock,
        mock_stripe_api: MagicMock,
        sample_plan: Plan,
    ) -> None:
        """Test that command reuses existing Stripe product.

        Args:
            mock_stripe_class: Mock for StripeAPI class.
            mock_stripe_api: Mock StripeAPI instance.
            sample_plan: Sample plan fixture.
        """
        # Mock that product already exists
        mock_stripe_api.get_product_by_metadata.return_value = {
            "id": "prod_existing",
            "name": "Basic Plan",
            "description": "Existing product",
            "metadata": {"plan_name": "basic"},
            "active": True,
        }
        mock_stripe_api.create_price.side_effect = [
            {
                "id": "price_monthly",
                "product": "prod_existing",
                "unit_amount": 2900,
                "currency": "usd",
                "recurring": {"interval": "month", "interval_count": 1},
                "lookup_key": "basic_monthly",
                "active": True,
            },
            {
                "id": "price_yearly",
                "product": "prod_existing",
                "unit_amount": 29000,
                "currency": "usd",
                "recurring": {"interval": "year", "interval_count": 1},
                "lookup_key": "basic_yearly",
                "active": True,
            },
        ]
        mock_stripe_class.return_value = mock_stripe_api

        out = StringIO()
        call_command("setup_stripe_plans", stdout=out)

        output = out.getvalue()

        # Verify existing product was found
        assert "Found existing product" in output

        # Verify no new product was created
        mock_stripe_api.create_product.assert_not_called()

        # Verify prices use existing product ID
        price_calls = mock_stripe_api.create_price.call_args_list
        for call in price_calls:
            assert call.kwargs["product_id"] == "prod_existing"

    @patch("core.management.commands.setup_stripe_plans.StripeAPI")
    def test_command_handles_stripe_errors(
        self,
        mock_stripe_class: MagicMock,
        mock_stripe_api: MagicMock,
        sample_plan: Plan,
    ) -> None:
        """Test that command handles Stripe API errors gracefully.

        Args:
            mock_stripe_class: Mock for StripeAPI class.
            mock_stripe_api: Mock StripeAPI instance.
            sample_plan: Sample plan fixture.
        """
        # Mock product creation failure
        mock_stripe_api.create_product.return_value = None
        mock_stripe_class.return_value = mock_stripe_api

        out = StringIO()
        call_command("setup_stripe_plans", stdout=out)

        output = out.getvalue()

        # Verify error was reported
        assert "Error" in output or "Failed" in output

    @patch("core.management.commands.setup_stripe_plans.StripeAPI")
    def test_command_multiple_plans(
        self,
        mock_stripe_class: MagicMock,
        mock_stripe_api: MagicMock,
        sample_plans: list[Plan],
    ) -> None:
        """Test command processes multiple plans correctly.

        Args:
            mock_stripe_class: Mock for StripeAPI class.
            mock_stripe_api: Mock StripeAPI instance.
            sample_plans: Multiple sample plans fixture.
        """
        # Configure mock to return different IDs for each plan
        product_count = [0]
        price_count = [0]

        def create_product_side_effect(**kwargs):
            product_count[0] += 1
            return {
                "id": f"prod_test_{product_count[0]}",
                "name": kwargs.get("name", "Test"),
                "description": kwargs.get("description", ""),
                "metadata": kwargs.get("metadata", {}),
                "active": True,
            }

        def create_price_side_effect(**kwargs):
            price_count[0] += 1
            interval = kwargs.get("interval", "month")
            return {
                "id": f"price_test_{price_count[0]}",
                "product": kwargs.get("product_id", "prod_test"),
                "unit_amount": kwargs.get("unit_amount", 0),
                "currency": kwargs.get("currency", "usd"),
                "recurring": {"interval": interval, "interval_count": 1},
                "lookup_key": kwargs.get("lookup_key", ""),
                "active": True,
            }

        mock_stripe_api.create_product.side_effect = create_product_side_effect
        mock_stripe_api.create_price.side_effect = create_price_side_effect
        mock_stripe_class.return_value = mock_stripe_api

        out = StringIO()
        call_command("setup_stripe_plans", stdout=out)

        output = out.getvalue()

        # Verify all plans were processed
        assert "Found 3 plan" in output
        assert mock_stripe_api.create_product.call_count == 3
        assert mock_stripe_api.create_price.call_count == 6  # 2 prices per plan

        # Verify all plans were updated
        for plan in sample_plans:
            plan.refresh_from_db()
            assert plan.stripe_price_id_monthly != ""
            assert plan.stripe_price_id_yearly != ""

    @patch("core.management.commands.setup_stripe_plans.StripeAPI")
    def test_command_dry_run_shows_what_would_be_created(
        self,
        mock_stripe_class: MagicMock,
        mock_stripe_api: MagicMock,
        sample_plan: Plan,
    ) -> None:
        """Test that dry-run shows what would be created.

        Args:
            mock_stripe_class: Mock for StripeAPI class.
            mock_stripe_api: Mock StripeAPI instance.
            sample_plan: Sample plan fixture.
        """
        mock_stripe_class.return_value = mock_stripe_api

        out = StringIO()
        call_command("setup_stripe_plans", "--dry-run", stdout=out)

        output = out.getvalue()

        # Verify dry run shows product info
        assert "Would create product" in output
        assert "Basic Plan" in output

        # Verify dry run shows price info
        assert "Would create monthly price" in output
        assert "Would create yearly price" in output
        assert "2900 cents" in output  # $29.00 in cents

    @patch("core.management.commands.setup_stripe_plans.StripeAPI")
    def test_command_defaults_yearly_to_10x_monthly(
        self,
        mock_stripe_class: MagicMock,
        mock_stripe_api: MagicMock,
        db,
    ) -> None:
        """Test that yearly price defaults to 10x monthly if not set.

        Args:
            mock_stripe_class: Mock for StripeAPI class.
            mock_stripe_api: Mock StripeAPI instance.
            db: Database access fixture.
        """
        # Delete any existing plans to avoid unique constraint violations
        Plan.objects.all().delete()
        # Create plan without yearly price
        Plan.objects.create(
            name="test",
            display_name="Test Plan",
            price_monthly=Decimal("49.00"),
            price_yearly=None,  # No yearly price
            is_active=True,
        )

        price_amounts = []

        def create_price_side_effect(**kwargs):
            price_amounts.append(kwargs.get("unit_amount", 0))
            interval = kwargs.get("interval", "month")
            return {
                "id": f"price_{len(price_amounts)}",
                "product": kwargs.get("product_id", "prod_test"),
                "unit_amount": kwargs.get("unit_amount", 0),
                "currency": "usd",
                "recurring": {"interval": interval, "interval_count": 1},
                "lookup_key": kwargs.get("lookup_key", ""),
                "active": True,
            }

        mock_stripe_api.create_price.side_effect = create_price_side_effect
        mock_stripe_class.return_value = mock_stripe_api

        out = StringIO()
        call_command("setup_stripe_plans", stdout=out)

        # Verify monthly is $49 (4900 cents)
        assert 4900 in price_amounts

        # Verify yearly is 10x monthly = $490 (49000 cents)
        assert 49000 in price_amounts


class TestStripeAPINewMethods:
    """Tests for the new StripeAPI methods added for plan setup."""

    @patch("core.services.stripe.stripe.Product.create")
    def test_create_product_success(self, mock_create: MagicMock) -> None:
        """Test successful product creation.

        Args:
            mock_create: Mock for stripe.Product.create.
        """
        from core.services.stripe import StripeAPI

        mock_product = Mock()
        mock_product.id = "prod_test123"
        mock_product.name = "Test Product"
        mock_product.description = "Test description"
        mock_product.metadata = {"plan_name": "test"}
        mock_product.active = True
        mock_create.return_value = mock_product

        api = StripeAPI()
        result = api.create_product(
            name="Test Product",
            description="Test description",
            metadata={"plan_name": "test"},
        )

        assert result is not None
        assert result["id"] == "prod_test123"
        assert result["name"] == "Test Product"
        assert result["metadata"]["plan_name"] == "test"

    @patch("core.services.stripe.stripe.Product.create")
    def test_create_product_stripe_error(self, mock_create: MagicMock) -> None:
        """Test product creation with Stripe error.

        Args:
            mock_create: Mock for stripe.Product.create.
        """
        from core.services.stripe import StripeAPI
        from stripe import StripeError

        mock_create.side_effect = StripeError("API Error")

        api = StripeAPI()
        result = api.create_product(name="Test")

        assert result is None

    @patch("core.services.stripe.stripe.Price.create")
    def test_create_price_success(self, mock_create: MagicMock) -> None:
        """Test successful price creation.

        Args:
            mock_create: Mock for stripe.Price.create.
        """
        from core.services.stripe import StripeAPI

        mock_price = Mock()
        mock_price.id = "price_test123"
        mock_price.product = "prod_test"
        mock_price.unit_amount = 2900
        mock_price.currency = "usd"
        mock_price.recurring = Mock()
        mock_price.recurring.interval = "month"
        mock_price.recurring.interval_count = 1
        mock_price.lookup_key = "test_monthly"
        mock_price.active = True
        mock_create.return_value = mock_price

        api = StripeAPI()
        result = api.create_price(
            product_id="prod_test",
            unit_amount=2900,
            currency="usd",
            interval="month",
            lookup_key="test_monthly",
        )

        assert result is not None
        assert result["id"] == "price_test123"
        assert result["unit_amount"] == 2900
        assert result["lookup_key"] == "test_monthly"

        # Verify lookup key transfer was requested
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["transfer_lookup_key"] is True

    @patch("core.services.stripe.stripe.Price.create")
    def test_create_price_yearly_interval(self, mock_create: MagicMock) -> None:
        """Test price creation with yearly interval.

        Args:
            mock_create: Mock for stripe.Price.create.
        """
        from core.services.stripe import StripeAPI

        mock_price = Mock()
        mock_price.id = "price_yearly"
        mock_price.product = "prod_test"
        mock_price.unit_amount = 29000
        mock_price.currency = "usd"
        mock_price.recurring = Mock()
        mock_price.recurring.interval = "year"
        mock_price.recurring.interval_count = 1
        mock_price.lookup_key = "test_yearly"
        mock_price.active = True
        mock_create.return_value = mock_price

        api = StripeAPI()
        result = api.create_price(
            product_id="prod_test",
            unit_amount=29000,
            interval="year",
            lookup_key="test_yearly",
        )

        assert result is not None
        assert result["recurring"]["interval"] == "year"

        # Verify interval was passed correctly
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["recurring"]["interval"] == "year"

    @patch("core.services.stripe.stripe.Product.list")
    def test_list_products_success(self, mock_list: MagicMock) -> None:
        """Test successful product listing.

        Args:
            mock_list: Mock for stripe.Product.list.
        """
        from core.services.stripe import StripeAPI

        mock_product1 = Mock()
        mock_product1.id = "prod_1"
        mock_product1.name = "Product 1"
        mock_product1.description = "Desc 1"
        mock_product1.metadata = {"plan_name": "basic"}
        mock_product1.active = True

        mock_product2 = Mock()
        mock_product2.id = "prod_2"
        mock_product2.name = "Product 2"
        mock_product2.description = "Desc 2"
        mock_product2.metadata = {}
        mock_product2.active = True

        mock_list.return_value = Mock(data=[mock_product1, mock_product2])

        api = StripeAPI()
        result = api.list_products()

        assert len(result) == 2
        assert result[0]["id"] == "prod_1"
        assert result[1]["id"] == "prod_2"

    @patch("core.services.stripe.stripe.Product.list")
    def test_get_product_by_metadata_found(self, mock_list: MagicMock) -> None:
        """Test finding product by metadata.

        Args:
            mock_list: Mock for stripe.Product.list.
        """
        from core.services.stripe import StripeAPI

        mock_product = Mock()
        mock_product.id = "prod_found"
        mock_product.name = "Found Product"
        mock_product.description = "Description"
        mock_product.metadata = {"plan_name": "basic"}
        mock_product.active = True

        mock_list.return_value = Mock(data=[mock_product])

        api = StripeAPI()
        result = api.get_product_by_metadata("plan_name", "basic")

        assert result is not None
        assert result["id"] == "prod_found"
        assert result["metadata"]["plan_name"] == "basic"

    @patch("core.services.stripe.stripe.Product.list")
    def test_get_product_by_metadata_not_found(self, mock_list: MagicMock) -> None:
        """Test product not found by metadata.

        Args:
            mock_list: Mock for stripe.Product.list.
        """
        from core.services.stripe import StripeAPI

        mock_product = Mock()
        mock_product.metadata = {"plan_name": "pro"}

        mock_list.return_value = Mock(data=[mock_product])

        api = StripeAPI()
        result = api.get_product_by_metadata("plan_name", "basic")

        assert result is None

    @patch("core.services.stripe.stripe.Product.modify")
    def test_update_product_success(self, mock_modify: MagicMock) -> None:
        """Test successful product update.

        Args:
            mock_modify: Mock for stripe.Product.modify.
        """
        from core.services.stripe import StripeAPI

        mock_product = Mock()
        mock_product.id = "prod_test"
        mock_product.name = "Updated Name"
        mock_product.description = "Updated Desc"
        mock_product.metadata = {"plan_name": "basic"}
        mock_product.active = True
        mock_modify.return_value = mock_product

        api = StripeAPI()
        result = api.update_product(
            product_id="prod_test",
            name="Updated Name",
            description="Updated Desc",
        )

        assert result is not None
        assert result["name"] == "Updated Name"
        mock_modify.assert_called_once()

    @patch("core.services.stripe.stripe.Product.modify")
    def test_update_product_no_params(self, mock_modify: MagicMock) -> None:
        """Test product update with no parameters.

        Args:
            mock_modify: Mock for stripe.Product.modify.
        """
        from core.services.stripe import StripeAPI

        api = StripeAPI()
        result = api.update_product(product_id="prod_test")

        assert result is None
        mock_modify.assert_not_called()
