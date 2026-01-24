"""Tests for the message builder module.

Tests cover:
- MessageContext creation from event data
- BlockFactory block generation
- MessageBuilder complete message assembly
- Payment type detection (recurring vs one-time)
- Payment method extraction
- Provider-specific formatting (SaaS vs E-commerce)
"""

import pytest
from webhooks.services.message_builder import (
    BlockFactory,
    MessageBuilder,
    MessageContext,
    PaymentMethodInfo,
    ProviderType,
    _detect_recurring,
    _extract_payment_method,
)


class TestPaymentMethodInfo:
    """Tests for PaymentMethodInfo dataclass."""

    def test_to_display_with_brand_and_last4(self) -> None:
        """Test display format with brand and last4."""
        pm = PaymentMethodInfo(method_type="card", brand="visa", last4="4242")
        display = pm.to_display()
        assert display == "💳 Visa ••••4242"

    def test_to_display_with_brand_only(self) -> None:
        """Test display format with brand only."""
        pm = PaymentMethodInfo(method_type="card", brand="mastercard")
        display = pm.to_display()
        assert display == "💳 Mastercard"

    def test_to_display_with_method_type_only(self) -> None:
        """Test display format with method type only."""
        pm = PaymentMethodInfo(method_type="bank_account")
        display = pm.to_display()
        assert display == "🏦 Bank_Account"

    def test_to_display_returns_none_when_empty(self) -> None:
        """Test None return when no info available."""
        pm = PaymentMethodInfo()
        assert pm.to_display() is None


class TestDetectRecurring:
    """Tests for _detect_recurring function."""

    def test_renewal_event_is_recurring(self) -> None:
        """Test renewal events are detected as recurring."""
        event = {"type": "renewal_success", "metadata": {}}
        assert _detect_recurring(event) is True

    def test_subscription_id_indicates_recurring(self) -> None:
        """Test subscription_id presence indicates recurring."""
        event = {"type": "payment_success", "metadata": {"subscription_id": "123"}}
        assert _detect_recurring(event) is True

    def test_subscription_contract_indicates_recurring(self) -> None:
        """Test Shopify subscription contract indicates recurring."""
        event = {
            "type": "payment_success",
            "metadata": {"subscription_contract_id": "456"},
        }
        assert _detect_recurring(event) is True

    def test_one_time_payment(self) -> None:
        """Test one-time payment is not recurring."""
        event = {"type": "payment_success", "metadata": {}}
        assert _detect_recurring(event) is False


class TestExtractPaymentMethod:
    """Tests for _extract_payment_method function."""

    def test_shopify_credit_card(self) -> None:
        """Test Shopify credit card extraction."""
        event = {
            "provider": "shopify",
            "metadata": {
                "credit_card_company": "Visa",
                "card_last4": "4242",
            },
        }
        pm = _extract_payment_method(event)
        assert pm is not None
        assert pm.brand == "Visa"
        assert pm.last4 == "4242"

    def test_shopify_gateway(self) -> None:
        """Test Shopify payment gateway extraction."""
        event = {
            "provider": "shopify",
            "metadata": {"payment_gateway": "shopify_payments"},
        }
        pm = _extract_payment_method(event)
        assert pm is not None
        assert pm.method_type == "shopify_payments"

    def test_chargify_card(self) -> None:
        """Test Chargify card extraction."""
        event = {
            "provider": "chargify",
            "metadata": {
                "card_type": "mastercard",
                "card_last4": "5555",
            },
        }
        pm = _extract_payment_method(event)
        assert pm is not None
        assert pm.brand == "mastercard"
        assert pm.last4 == "5555"

    def test_stripe_card(self) -> None:
        """Test Stripe card extraction."""
        event = {
            "provider": "stripe",
            "metadata": {
                "card_brand": "amex",
                "card_last4": "1234",
            },
        }
        pm = _extract_payment_method(event)
        assert pm is not None
        assert pm.brand == "amex"
        assert pm.last4 == "1234"

    def test_unknown_provider_returns_none(self) -> None:
        """Test unknown provider returns None."""
        event = {"provider": "unknown", "metadata": {}}
        assert _extract_payment_method(event) is None


class TestMessageContext:
    """Tests for MessageContext dataclass."""

    def test_from_event_data_saas(self) -> None:
        """Test context creation for SaaS payment."""
        event = {
            "type": "payment_success",
            "provider": "chargify",
            "amount": 99.00,
            "currency": "USD",
            "metadata": {
                "subscription_id": "sub_123",
                "plan_name": "Pro",
                "billing_period": "monthly",
            },
        }
        ctx = MessageContext.from_event_data(event)
        assert ctx.provider == "chargify"
        assert ctx.provider_type == ProviderType.SAAS
        assert ctx.is_recurring is True
        assert ctx.plan_name == "Pro"
        assert ctx.amount == 99.00

    def test_from_event_data_ecommerce(self) -> None:
        """Test context creation for e-commerce order."""
        event = {
            "type": "payment_success",
            "provider": "shopify",
            "amount": 299.00,
            "currency": "USD",
            "metadata": {
                "order_number": "1001",
                "line_items": [{"name": "Widget", "quantity": 2, "price": 149.50}],
            },
        }
        ctx = MessageContext.from_event_data(event)
        assert ctx.provider == "shopify"
        assert ctx.provider_type == ProviderType.ECOMMERCE
        assert ctx.is_recurring is False
        assert ctx.order_number == "1001"
        assert len(ctx.line_items) == 1


class TestBlockFactory:
    """Tests for BlockFactory static methods."""

    def test_header(self) -> None:
        """Test header block creation."""
        block = BlockFactory.header("Test Title", "💰")
        assert block["type"] == "header"
        assert block["text"]["text"] == "💰 Test Title"
        assert block["text"]["emoji"] is True

    def test_header_without_emoji(self) -> None:
        """Test header block without emoji."""
        block = BlockFactory.header("Test Title")
        assert block["text"]["text"] == "Test Title"

    def test_divider(self) -> None:
        """Test divider block creation."""
        block = BlockFactory.divider()
        assert block["type"] == "divider"

    def test_context(self) -> None:
        """Test context block creation."""
        block = BlockFactory.context(["Element 1", "Element 2"])
        assert block["type"] == "context"
        assert len(block["elements"]) == 2
        assert block["elements"][0]["type"] == "mrkdwn"
        assert block["elements"][0]["text"] == "Element 1"

    def test_section(self) -> None:
        """Test section block creation."""
        block = BlockFactory.section("Test text")
        assert block["type"] == "section"
        assert block["text"]["text"] == "Test text"
        assert "accessory" not in block

    def test_section_with_accessory(self) -> None:
        """Test section block with accessory."""
        accessory = {"type": "image", "image_url": "http://example.com/logo.png"}
        block = BlockFactory.section("Test text", accessory)
        assert block["accessory"] == accessory

    def test_image_accessory(self) -> None:
        """Test image accessory creation."""
        accessory = BlockFactory.image_accessory(
            "http://example.com/logo.png", "Company Logo"
        )
        assert accessory["type"] == "image"
        assert accessory["image_url"] == "http://example.com/logo.png"
        assert accessory["alt_text"] == "Company Logo"


class TestMessageBuilder:
    """Tests for MessageBuilder class."""

    @pytest.fixture
    def builder(self) -> MessageBuilder:
        """Create a MessageBuilder instance."""
        return MessageBuilder()

    def test_build_saas_message(self, builder: MessageBuilder) -> None:
        """Test building a SaaS payment message."""
        event_data = {
            "type": "payment_success",
            "provider": "chargify",
            "amount": 99.00,
            "currency": "USD",
            "metadata": {
                "subscription_id": "sub_123",
                "plan_name": "Pro",
            },
        }
        customer_data = {
            "company_name": "Acme Corp",
            "email": "john@acme.com",
        }

        result = builder.build(event_data, customer_data)

        assert "blocks" in result
        assert "color" in result
        assert result["color"] == "#28a745"  # Green for success

        # Check header
        header = result["blocks"][0]
        assert header["type"] == "header"
        assert "Acme Corp" in header["text"]["text"]

        # Check source badge
        badge = result["blocks"][1]
        assert badge["type"] == "context"

    def test_build_ecommerce_message(self, builder: MessageBuilder) -> None:
        """Test building an e-commerce order message."""
        event_data = {
            "type": "payment_success",
            "provider": "shopify",
            "amount": 299.00,
            "currency": "USD",
            "metadata": {
                "order_number": "1001",
                "line_items": [
                    {"name": "Widget Pro", "quantity": 2, "price": 49.99},
                    {"name": "Service", "quantity": 1, "price": 199.00},
                ],
            },
        }
        customer_data = {
            "company": "Test Co",
            "email": "test@test.co",
            "orders_count": 5,
            "total_spent": "1200.00",
        }

        result = builder.build(event_data, customer_data)

        # Check header says "New order" for e-commerce
        header = result["blocks"][0]
        assert "order" in header["text"]["text"].lower()

    def test_build_payment_failure_message(self, builder: MessageBuilder) -> None:
        """Test building a payment failure message."""
        event_data = {
            "type": "payment_failure",
            "provider": "stripe",
            "amount": 50.00,
            "currency": "USD",
            "metadata": {},
        }
        customer_data = {"company_name": "Failed Corp"}

        result = builder.build(event_data, customer_data)

        assert result["color"] == "#dc3545"  # Red for failure
        header = result["blocks"][0]
        assert "failed" in header["text"]["text"].lower()

    def test_format_payment_type_recurring(self, builder: MessageBuilder) -> None:
        """Test recurring payment type formatting."""
        ctx = MessageContext(
            provider="chargify",
            provider_type=ProviderType.SAAS,
            event_type="payment_success",
            is_recurring=True,
            billing_interval="monthly",
            payment_method=None,
            amount=100.0,
            currency="USD",
        )
        result = builder._format_payment_type(ctx)
        assert "🔄" in result
        assert "Recurring" in result
        assert "Monthly" in result

    def test_format_payment_type_one_time(self, builder: MessageBuilder) -> None:
        """Test one-time payment type formatting."""
        ctx = MessageContext(
            provider="shopify",
            provider_type=ProviderType.ECOMMERCE,
            event_type="payment_success",
            is_recurring=False,
            billing_interval=None,
            payment_method=None,
            amount=100.0,
            currency="USD",
        )
        result = builder._format_payment_type(ctx)
        assert "💵" in result
        assert "One-Time" in result

    def test_get_header_text_payment_success(self, builder: MessageBuilder) -> None:
        """Test header text for payment success."""
        ctx = MessageContext(
            provider="chargify",
            provider_type=ProviderType.SAAS,
            event_type="payment_success",
            is_recurring=True,
            billing_interval=None,
            payment_method=None,
            amount=100.0,
            currency="USD",
        )
        emoji, title = builder._get_header_text(ctx, "Acme Corp")
        assert emoji == "💰"
        assert "Payment received" in title
        assert "Acme Corp" in title

    def test_get_header_text_ecommerce_order(self, builder: MessageBuilder) -> None:
        """Test header text for e-commerce order."""
        ctx = MessageContext(
            provider="shopify",
            provider_type=ProviderType.ECOMMERCE,
            event_type="payment_success",
            is_recurring=False,
            billing_interval=None,
            payment_method=None,
            amount=100.0,
            currency="USD",
        )
        emoji, title = builder._get_header_text(ctx, "Test Co")
        assert emoji == "💰"
        assert "order" in title.lower()
        assert "Test Co" in title

    def test_build_source_badge_with_payment_method(
        self, builder: MessageBuilder
    ) -> None:
        """Test source badge includes payment method."""
        ctx = MessageContext(
            provider="chargify",
            provider_type=ProviderType.SAAS,
            event_type="payment_success",
            is_recurring=True,
            billing_interval="monthly",
            payment_method=PaymentMethodInfo(brand="visa", last4="4242"),
            amount=100.0,
            currency="USD",
        )
        badge = builder._build_source_badge(ctx)
        # Badge should contain provider, payment type, and method
        badge_text = badge["elements"][0]["text"]
        assert "Chargify" in badge_text
        assert "Recurring" in badge_text
        assert "Visa" in badge_text
