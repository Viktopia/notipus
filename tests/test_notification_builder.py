"""Tests for the NotificationBuilder service.

This module tests the NotificationBuilder class that creates
RichNotification objects from event and customer data.
"""

from unittest.mock import MagicMock

import pytest
from webhooks.models.rich_notification import (
    NotificationSeverity,
    NotificationType,
    RichNotification,
)
from webhooks.services.notification_builder import NotificationBuilder


@pytest.fixture
def builder() -> NotificationBuilder:
    """Create a NotificationBuilder instance."""
    return NotificationBuilder()


@pytest.fixture
def payment_success_event() -> dict:
    """Sample payment success event data."""
    return {
        "type": "payment_success",
        "provider": "stripe",
        "amount": 299.00,
        "currency": "USD",
        "metadata": {
            "plan_name": "Enterprise",
            "subscription_id": "sub_123",
            "billing_period": "monthly",
            "card_brand": "visa",
            "card_last4": "4242",
            "stripe_customer_id": "cus_abc123",
        },
    }


@pytest.fixture
def payment_failure_event() -> dict:
    """Sample payment failure event data."""
    return {
        "type": "payment_failure",
        "provider": "chargify",
        "amount": 99.00,
        "currency": "USD",
        "metadata": {
            "plan_name": "Pro",
            "subscription_id": "sub_456",
            "failure_reason": "Card declined",
        },
    }


@pytest.fixture
def subscription_created_event() -> dict:
    """Sample subscription created event data."""
    return {
        "type": "subscription_created",
        "provider": "stripe",
        "amount": 49.00,
        "currency": "USD",
        "metadata": {
            "plan_name": "Starter",
            "subscription_id": "sub_789",
            "billing_period": "monthly",
        },
    }


@pytest.fixture
def customer_data() -> dict:
    """Sample customer data."""
    return {
        "email": "alice@acme.com",
        "first_name": "Alice",
        "last_name": "Smith",
        "company_name": "Acme Inc",
        "orders_count": 5,
        "total_spent": 1500.00,
        "created_at": "2024-03-15T10:00:00Z",
    }


@pytest.fixture
def new_customer_data() -> dict:
    """Sample data for a new customer (first payment)."""
    return {
        "email": "bob@newco.com",
        "first_name": "Bob",
        "last_name": "Jones",
        "company_name": "NewCo",
        "orders_count": 0,
        "total_spent": 0,
    }


@pytest.fixture
def mock_company() -> MagicMock:
    """Create a mock Company object."""
    company = MagicMock()
    company.domain = "acme.com"
    company.name = "Acme Corporation"
    company.has_logo = True
    company.get_logo_url.return_value = "https://example.com/logo.png"
    company.brand_info = {
        "name": "Acme Corporation",
        "industry": "Technology",
        "year_founded": 2015,
        "employee_count": "51-200",
        "description": "Acme Corporation builds tools for developers.",
        "logo_url": "https://example.com/logo.png",
        "links": [
            {"name": "linkedin", "url": "https://linkedin.com/company/acme-corp"},
            {"name": "twitter", "url": "https://twitter.com/acme"},
        ],
    }
    return company


class TestNotificationBuilderBasic:
    """Test basic NotificationBuilder functionality."""

    def test_build_returns_rich_notification(
        self,
        builder: NotificationBuilder,
        payment_success_event: dict,
        customer_data: dict,
    ) -> None:
        """Test that build returns a RichNotification object."""
        result = builder.build(payment_success_event, customer_data)

        assert isinstance(result, RichNotification)

    def test_build_requires_event_data(
        self, builder: NotificationBuilder, customer_data: dict
    ) -> None:
        """Test that build raises ValueError for missing event data."""
        with pytest.raises(ValueError, match="Missing event data"):
            builder.build({}, customer_data)

        with pytest.raises(ValueError, match="Missing event data"):
            builder.build(None, customer_data)  # type: ignore

    def test_build_requires_customer_data(
        self, builder: NotificationBuilder, payment_success_event: dict
    ) -> None:
        """Test that build raises ValueError for missing customer data."""
        with pytest.raises(ValueError, match="Missing customer data"):
            builder.build(payment_success_event, {})

        with pytest.raises(ValueError, match="Missing customer data"):
            builder.build(payment_success_event, None)  # type: ignore

    def test_build_requires_event_type(
        self, builder: NotificationBuilder, customer_data: dict
    ) -> None:
        """Test that build raises ValueError for missing event type."""
        with pytest.raises(ValueError, match="Missing event type"):
            builder.build({"provider": "stripe"}, customer_data)


class TestNotificationTypes:
    """Test notification type detection."""

    def test_payment_success_type(
        self,
        builder: NotificationBuilder,
        payment_success_event: dict,
        customer_data: dict,
    ) -> None:
        """Test payment success notification type."""
        result = builder.build(payment_success_event, customer_data)

        assert result.type == NotificationType.PAYMENT_SUCCESS
        assert result.severity == NotificationSeverity.SUCCESS
        assert result.headline_icon == "money"

    def test_payment_failure_type(
        self,
        builder: NotificationBuilder,
        payment_failure_event: dict,
        customer_data: dict,
    ) -> None:
        """Test payment failure notification type."""
        result = builder.build(payment_failure_event, customer_data)

        assert result.type == NotificationType.PAYMENT_FAILURE
        assert result.severity == NotificationSeverity.ERROR
        assert result.headline_icon == "error"

    def test_subscription_created_type(
        self,
        builder: NotificationBuilder,
        subscription_created_event: dict,
        customer_data: dict,
    ) -> None:
        """Test subscription created notification type."""
        result = builder.build(subscription_created_event, customer_data)

        assert result.type == NotificationType.SUBSCRIPTION_CREATED
        # New subscription is a positive event
        assert result.severity == NotificationSeverity.SUCCESS
        assert result.headline_icon == "celebration"

    def test_subscription_canceled_type(
        self, builder: NotificationBuilder, customer_data: dict
    ) -> None:
        """Test subscription canceled notification type."""
        event = {"type": "subscription_canceled", "provider": "stripe"}
        result = builder.build(event, customer_data)

        assert result.type == NotificationType.SUBSCRIPTION_CANCELED
        assert result.severity == NotificationSeverity.WARNING
        assert result.headline_icon == "warning"


class TestHeadlineBuilding:
    """Test headline generation."""

    def test_payment_success_headline_with_amount(
        self,
        builder: NotificationBuilder,
        payment_success_event: dict,
        customer_data: dict,
    ) -> None:
        """Test payment success headline includes amount and company."""
        result = builder.build(payment_success_event, customer_data)

        assert "$299.00" in result.headline
        assert "Acme Inc" in result.headline

    def test_payment_failure_headline(
        self,
        builder: NotificationBuilder,
        payment_failure_event: dict,
        customer_data: dict,
    ) -> None:
        """Test payment failure headline."""
        result = builder.build(payment_failure_event, customer_data)

        assert "failed" in result.headline.lower()
        assert "Acme Inc" in result.headline

    def test_subscription_created_headline(
        self,
        builder: NotificationBuilder,
        subscription_created_event: dict,
        new_customer_data: dict,
    ) -> None:
        """Test subscription created headline."""
        result = builder.build(subscription_created_event, new_customer_data)

        assert "New" in result.headline or "subscription" in result.headline.lower()

    def test_headline_uses_enriched_company_name(
        self,
        builder: NotificationBuilder,
        payment_success_event: dict,
        customer_data: dict,
        mock_company: MagicMock,
    ) -> None:
        """Test that headline uses enriched company name when available."""
        result = builder.build(payment_success_event, customer_data, mock_company)

        assert "Acme Corporation" in result.headline


class TestPaymentInfo:
    """Test PaymentInfo extraction."""

    def test_payment_info_extracted(
        self,
        builder: NotificationBuilder,
        payment_success_event: dict,
        customer_data: dict,
    ) -> None:
        """Test that payment info is extracted correctly."""
        result = builder.build(payment_success_event, customer_data)

        assert result.payment is not None
        assert result.payment.amount == 299.00
        assert result.payment.currency == "USD"
        assert result.payment.plan_name == "Enterprise"
        assert result.payment.subscription_id == "sub_123"

    def test_payment_method_extraction(
        self,
        builder: NotificationBuilder,
        payment_success_event: dict,
        customer_data: dict,
    ) -> None:
        """Test payment method is extracted."""
        result = builder.build(payment_success_event, customer_data)

        assert result.payment is not None
        assert result.payment.payment_method == "visa"
        assert result.payment.card_last4 == "4242"

    def test_recurring_detection_with_subscription(
        self,
        builder: NotificationBuilder,
        payment_success_event: dict,
        customer_data: dict,
    ) -> None:
        """Test recurring payment detection."""
        result = builder.build(payment_success_event, customer_data)

        assert result.is_recurring is True
        assert result.billing_interval == "monthly"

    def test_one_time_payment_detection(
        self, builder: NotificationBuilder, customer_data: dict
    ) -> None:
        """Test one-time payment detection."""
        event = {
            "type": "payment_success",
            "provider": "shopify",
            "amount": 50.00,
            "currency": "USD",
            "metadata": {"order_number": "1234"},
        }
        result = builder.build(event, customer_data)

        assert result.is_recurring is False

    def test_arr_calculation_monthly(
        self,
        builder: NotificationBuilder,
        payment_success_event: dict,
        customer_data: dict,
    ) -> None:
        """Test ARR calculation for monthly payments."""
        result = builder.build(payment_success_event, customer_data)

        assert result.payment is not None
        arr = result.payment.get_arr()
        assert arr == 299.00 * 12


class TestCustomerInfo:
    """Test CustomerInfo building."""

    def test_customer_info_built(
        self,
        builder: NotificationBuilder,
        payment_success_event: dict,
        customer_data: dict,
    ) -> None:
        """Test customer info is built correctly."""
        result = builder.build(payment_success_event, customer_data)

        assert result.customer.email == "alice@acme.com"
        assert result.customer.name == "Alice Smith"
        assert result.customer.company_name == "Acme Inc"
        assert result.customer.orders_count == 5
        assert result.customer.total_spent == 1500.00

    def test_tenure_display_formatted(
        self,
        builder: NotificationBuilder,
        payment_success_event: dict,
        customer_data: dict,
    ) -> None:
        """Test tenure display formatting."""
        result = builder.build(payment_success_event, customer_data)

        assert result.customer.tenure_display is not None
        assert "Since" in result.customer.tenure_display
        assert "Mar 2024" in result.customer.tenure_display

    def test_ltv_display_formatted(
        self,
        builder: NotificationBuilder,
        payment_success_event: dict,
        customer_data: dict,
    ) -> None:
        """Test LTV display formatting."""
        result = builder.build(payment_success_event, customer_data)

        assert result.customer.ltv_display is not None
        assert "$1.5k" in result.customer.ltv_display


class TestCompanyEnrichment:
    """Test company enrichment integration."""

    def test_company_info_built_from_enrichment(
        self,
        builder: NotificationBuilder,
        payment_success_event: dict,
        customer_data: dict,
        mock_company: MagicMock,
    ) -> None:
        """Test company info is built from enriched Company model."""
        result = builder.build(payment_success_event, customer_data, mock_company)

        assert result.company is not None
        assert result.company.name == "Acme Corporation"
        assert result.company.domain == "acme.com"
        assert result.company.industry == "Technology"
        assert result.company.year_founded == 2015
        assert result.company.logo_url is not None

    def test_no_company_info_without_enrichment(
        self,
        builder: NotificationBuilder,
        payment_success_event: dict,
        customer_data: dict,
    ) -> None:
        """Test company info is None without enrichment."""
        result = builder.build(payment_success_event, customer_data)

        assert result.company is None

    def test_linkedin_url_extracted_from_brand_info(
        self,
        builder: NotificationBuilder,
        payment_success_event: dict,
        customer_data: dict,
        mock_company: MagicMock,
    ) -> None:
        """Test LinkedIn URL is extracted from brand_info links array."""
        result = builder.build(payment_success_event, customer_data, mock_company)

        assert result.company is not None
        assert result.company.linkedin_url == "https://linkedin.com/company/acme-corp"

    def test_linkedin_url_none_when_not_in_links(
        self,
        builder: NotificationBuilder,
        payment_success_event: dict,
        customer_data: dict,
    ) -> None:
        """Test LinkedIn URL is None when not in brand_info links."""
        company = MagicMock()
        company.domain = "test.com"
        company.name = "Test Corp"
        company.has_logo = False
        company.brand_info = {
            "name": "Test Corp",
            "links": [
                {"name": "twitter", "url": "https://twitter.com/test"},
            ],
        }

        result = builder.build(payment_success_event, customer_data, company)

        assert result.company is not None
        assert result.company.linkedin_url is None

    def test_linkedin_url_none_when_no_links(
        self,
        builder: NotificationBuilder,
        payment_success_event: dict,
        customer_data: dict,
    ) -> None:
        """Test LinkedIn URL is None when no links in brand_info."""
        company = MagicMock()
        company.domain = "test.com"
        company.name = "Test Corp"
        company.has_logo = False
        company.brand_info = {
            "name": "Test Corp",
        }

        result = builder.build(payment_success_event, customer_data, company)

        assert result.company is not None
        assert result.company.linkedin_url is None


class TestActionButtons:
    """Test action button generation."""

    def test_stripe_action_buttons(
        self,
        builder: NotificationBuilder,
        payment_success_event: dict,
        customer_data: dict,
    ) -> None:
        """Test Stripe-specific action buttons."""
        result = builder.build(payment_success_event, customer_data)

        assert len(result.actions) > 0
        action_texts = [a.text for a in result.actions]
        assert "View in Stripe" in action_texts

    def test_website_button_with_company(
        self,
        builder: NotificationBuilder,
        payment_success_event: dict,
        customer_data: dict,
        mock_company: MagicMock,
    ) -> None:
        """Test website button added when company is enriched."""
        result = builder.build(payment_success_event, customer_data, mock_company)

        action_texts = [a.text for a in result.actions]
        assert "Website" in action_texts

    def test_contact_button_on_failure(
        self,
        builder: NotificationBuilder,
        payment_failure_event: dict,
        customer_data: dict,
    ) -> None:
        """Test contact customer button on payment failure."""
        result = builder.build(payment_failure_event, customer_data)

        action_texts = [a.text for a in result.actions]
        assert "Contact Customer" in action_texts


class TestInsightDetection:
    """Test insight detection integration."""

    def test_first_payment_insight(
        self,
        builder: NotificationBuilder,
        subscription_created_event: dict,
        new_customer_data: dict,
    ) -> None:
        """Test first payment insight detection."""
        result = builder.build(subscription_created_event, new_customer_data)

        assert result.insight is not None
        assert (
            "First payment" in result.insight.text or "Welcome" in result.insight.text
        )

    def test_failure_reason_insight(
        self,
        builder: NotificationBuilder,
        payment_failure_event: dict,
        customer_data: dict,
    ) -> None:
        """Test failure reason shown as insight."""
        result = builder.build(payment_failure_event, customer_data)

        assert result.insight is not None
        assert "declined" in result.insight.text.lower()


class TestProviderInfo:
    """Test provider information."""

    def test_stripe_provider_info(
        self,
        builder: NotificationBuilder,
        payment_success_event: dict,
        customer_data: dict,
    ) -> None:
        """Test Stripe provider information."""
        result = builder.build(payment_success_event, customer_data)

        assert result.provider == "stripe"
        assert result.provider_display == "Stripe"

    def test_chargify_provider_info(
        self,
        builder: NotificationBuilder,
        payment_failure_event: dict,
        customer_data: dict,
    ) -> None:
        """Test Chargify provider information."""
        result = builder.build(payment_failure_event, customer_data)

        assert result.provider == "chargify"
        assert result.provider_display == "Chargify"

    def test_shopify_provider_info(
        self, builder: NotificationBuilder, customer_data: dict
    ) -> None:
        """Test Shopify provider information."""
        event = {
            "type": "payment_success",
            "provider": "shopify",
            "amount": 100.00,
            "currency": "USD",
            "metadata": {"order_number": "1001"},
        }
        result = builder.build(event, customer_data)

        assert result.provider == "shopify"
        assert result.provider_display == "Shopify"
