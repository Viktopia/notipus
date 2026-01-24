"""DRY message builder with reusable blocks for Slack notifications.

This module provides a structured approach to building Slack messages
based on payment provider type (SaaS vs E-commerce) with context-aware
formatting and company enrichment integration.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.models import Company


class ProviderType(Enum):
    """Provider type classification."""

    SAAS = "saas"  # Subscription-based (Chargify, Stripe subscriptions)
    ECOMMERCE = "ecommerce"  # One-time orders (Shopify)


# Provider type mapping
PROVIDER_TYPES: dict[str, ProviderType] = {
    "shopify": ProviderType.ECOMMERCE,
    "chargify": ProviderType.SAAS,
    "stripe": ProviderType.SAAS,
    "stripe_customer": ProviderType.SAAS,
}

# Provider display icons (emoji for Slack compatibility)
PROVIDER_ICONS: dict[str, str] = {
    "shopify": "🛍️",
    "chargify": "💵",
    "stripe": "💳",
    "stripe_customer": "💳",
}

# Provider display names
PROVIDER_NAMES: dict[str, str] = {
    "shopify": "Shopify",
    "chargify": "Chargify",
    "stripe": "Stripe",
    "stripe_customer": "Stripe",
}

# Payment method icons
PAYMENT_METHOD_ICONS: dict[str, str] = {
    # Card brands
    "visa": "💳",
    "mastercard": "💳",
    "amex": "💳",
    "discover": "💳",
    # Bank/ACH
    "bank_account": "🏦",
    "us_bank_account": "🏦",
    "ach": "🏦",
    "sepa_debit": "🏦",
    # Digital wallets
    "paypal": "🅿️",
    "apple_pay": "🍎",
    "google_pay": "📱",
    "shop_pay": "🛍️",
    # Other
    "wire": "🏦",
    "manual": "📝",
    "cash": "💵",
    "shopify_payments": "💳",
}


@dataclass
class PaymentMethodInfo:
    """Payment method details."""

    method_type: str | None = None  # card, bank_account, paypal
    brand: str | None = None  # visa, mastercard
    last4: str | None = None

    def to_display(self) -> str | None:
        """Format for display: '💳 Visa ••••4242'."""
        if not self.brand and not self.method_type:
            return None
        key = (self.brand or self.method_type or "").lower()
        icon = PAYMENT_METHOD_ICONS.get(key, "💳")
        display_name = (self.brand or self.method_type or "Card").title()
        display = f"{icon} {display_name}"
        if self.last4:
            display += f" ••••{self.last4}"
        return display


@dataclass
class MessageContext:
    """Context for building a message - extracted from event data."""

    provider: str
    provider_type: ProviderType
    event_type: str
    is_recurring: bool
    billing_interval: str | None
    payment_method: PaymentMethodInfo | None
    amount: float | None
    currency: str
    # SaaS-specific
    plan_name: str | None = None
    subscription_id: str | None = None
    # E-commerce specific
    order_number: str | None = None
    line_items: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_event_data(cls, event_data: dict[str, Any]) -> "MessageContext":
        """Factory to create context from raw event data."""
        provider = event_data.get("provider", "unknown")
        metadata = event_data.get("metadata", {})

        return cls(
            provider=provider,
            provider_type=PROVIDER_TYPES.get(provider, ProviderType.SAAS),
            event_type=event_data.get("type", ""),
            is_recurring=_detect_recurring(event_data),
            billing_interval=metadata.get("billing_period"),
            payment_method=_extract_payment_method(event_data),
            amount=event_data.get("amount"),
            currency=event_data.get("currency", "USD"),
            plan_name=metadata.get("plan_name"),
            subscription_id=metadata.get("subscription_id"),
            order_number=metadata.get("order_number"),
            line_items=metadata.get("line_items", []),
        )


def _detect_recurring(event_data: dict[str, Any]) -> bool:
    """Detect if payment is recurring based on event data."""
    event_type = event_data.get("type", "")
    metadata = event_data.get("metadata", {})

    # Renewal events are always recurring
    if event_type in ("renewal_success", "renewal_failure"):
        return True

    # Check for subscription_id presence
    if metadata.get("subscription_id"):
        return True

    # Shopify: check for subscription info
    if metadata.get("subscription_contract_id"):
        return True

    return False


def _extract_payment_method(event_data: dict[str, Any]) -> PaymentMethodInfo | None:
    """Extract payment method info from event data."""
    metadata = event_data.get("metadata", {})
    provider = event_data.get("provider", "")

    if provider == "shopify":
        # Try credit card first
        card_brand = metadata.get("credit_card_company")
        if card_brand:
            return PaymentMethodInfo(
                method_type="card",
                brand=card_brand,
                last4=metadata.get("card_last4"),
            )
        # Fall back to gateway name
        gateway = metadata.get("payment_gateway")
        if gateway:
            return PaymentMethodInfo(method_type=gateway)

    elif provider == "chargify":
        card_type = metadata.get("card_type")
        if card_type:
            return PaymentMethodInfo(
                method_type="card",
                brand=card_type,
                last4=metadata.get("card_last4"),
            )
        method = metadata.get("payment_method")
        if method:
            return PaymentMethodInfo(method_type=method)

    elif provider in ("stripe", "stripe_customer"):
        card_brand = metadata.get("card_brand")
        if card_brand:
            return PaymentMethodInfo(
                method_type="card",
                brand=card_brand,
                last4=metadata.get("card_last4"),
            )
        pm_type = metadata.get("payment_method_type")
        if pm_type:
            return PaymentMethodInfo(method_type=pm_type)

    return None


class BlockFactory:
    """Factory for creating reusable Slack blocks."""

    @staticmethod
    def header(text: str, emoji: str = "") -> dict[str, Any]:
        """Create header block."""
        display_text = f"{emoji} {text}".strip() if emoji else text
        return {
            "type": "header",
            "text": {"type": "plain_text", "text": display_text, "emoji": True},
        }

    @staticmethod
    def divider() -> dict[str, Any]:
        """Create divider block."""
        return {"type": "divider"}

    @staticmethod
    def context(elements: list[str]) -> dict[str, Any]:
        """Create context block from text elements."""
        return {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": el} for el in elements],
        }

    @staticmethod
    def section(text: str, accessory: dict[str, Any] | None = None) -> dict[str, Any]:
        """Create section block with optional accessory (e.g., image)."""
        block: dict[str, Any] = {
            "type": "section",
            "text": {"type": "mrkdwn", "text": text},
        }
        if accessory:
            block["accessory"] = accessory
        return block

    @staticmethod
    def image_accessory(url: str, alt_text: str) -> dict[str, Any]:
        """Create image accessory for section blocks."""
        return {"type": "image", "image_url": url, "alt_text": alt_text}


class MessageBuilder:
    """Build Slack messages from event data with reusable blocks."""

    def __init__(self) -> None:
        """Initialize message builder with block factory."""
        self.blocks = BlockFactory()

    def build(
        self,
        event_data: dict[str, Any],
        customer_data: dict[str, Any],
        company: Company | None = None,
    ) -> dict[str, Any]:
        """Build complete Slack message from event data.

        Args:
            event_data: Event data dictionary from provider.
            customer_data: Customer data dictionary.
            company: Optional enriched Company model.

        Returns:
            Dict with 'blocks' and 'color' for Slack API.
        """
        context = MessageContext.from_event_data(event_data)

        blocks: list[dict[str, Any]] = [
            self._build_header(context, customer_data),
            self._build_source_badge(context),
            self._build_details_section(context),
            self.blocks.divider(),
        ]

        # Add company section if enrichment available
        if company and (company.name or company.has_logo):
            blocks.append(self._build_company_section(company))

        # Add customer footer
        blocks.append(self._build_customer_footer(customer_data))

        return {
            "blocks": blocks,
            "color": self._get_color(context.event_type),
        }

    def _build_header(
        self, ctx: MessageContext, customer_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Build header - same structure for all providers."""
        company_name = customer_data.get("company_name") or customer_data.get(
            "company", "Customer"
        )
        emoji, title = self._get_header_text(ctx, company_name)
        return self.blocks.header(title, emoji)

    def _build_source_badge(self, ctx: MessageContext) -> dict[str, Any]:
        """Build source badge: Provider • Payment Type • Payment Method."""
        provider_icon = PROVIDER_ICONS.get(ctx.provider, "📦")
        provider_name = PROVIDER_NAMES.get(ctx.provider, ctx.provider.title())

        elements = [
            f"{provider_icon} {provider_name}",
            self._format_payment_type(ctx),
        ]

        # Add payment method if available
        if ctx.payment_method:
            pm_display = ctx.payment_method.to_display()
            if pm_display:
                elements.append(pm_display)

        return self.blocks.context([" • ".join(elements)])

    def _build_details_section(self, ctx: MessageContext) -> dict[str, Any]:
        """Build details section - CONDITIONAL based on provider type."""
        if ctx.provider_type == ProviderType.ECOMMERCE:
            return self._build_ecommerce_details(ctx)
        return self._build_saas_details(ctx)

    def _build_company_section(self, company: Company) -> dict[str, Any]:
        """Build company enrichment section with logo.

        Uses canonical/blended fields from brand_info.
        """
        brand_info = company.brand_info or {}
        name = brand_info.get("name") or company.name or company.domain

        text_parts = [f"🏢 *{name}*"]

        # Add industry and year if available
        details: list[str] = []
        if brand_info.get("industry"):
            details.append(brand_info["industry"])
        if brand_info.get("year_founded"):
            details.append(f"Founded {brand_info['year_founded']}")
        if brand_info.get("employee_count"):
            details.append(f"{brand_info['employee_count']} employees")
        if details:
            text_parts.append(f"_{' • '.join(details)}_")

        # Add description as blockquote (truncated)
        if brand_info.get("description"):
            desc = brand_info["description"][:100]
            if len(brand_info["description"]) > 100:
                desc += "..."
            text_parts.append(f">{desc}")

        # Logo from Company model
        accessory = None
        if company.has_logo:
            logo_url = company.get_logo_url()
            if logo_url:
                accessory = self.blocks.image_accessory(logo_url, name)

        return self.blocks.section("\n".join(text_parts), accessory)

    def _build_customer_footer(self, customer_data: dict[str, Any]) -> dict[str, Any]:
        """Build compact customer context footer."""
        elements: list[str] = []

        if customer_data.get("email"):
            elements.append(f"👤 {customer_data['email']}")
        if customer_data.get("orders_count"):
            elements.append(f"📊 {customer_data['orders_count']} orders")
        if customer_data.get("total_spent"):
            elements.append(f"💰 ${customer_data['total_spent']} lifetime")

        if elements:
            return self.blocks.context(elements)
        return self.blocks.context(["👤 Customer"])

    def _build_saas_details(self, ctx: MessageContext) -> dict[str, Any]:
        """Build SaaS subscription payment details."""
        lines = ["📊 *Payment Details*"]

        if ctx.amount is not None:
            lines.append(f"Amount: {ctx.currency} {ctx.amount:,.2f}")
        if ctx.plan_name:
            lines.append(f"Plan: {ctx.plan_name}")
        if ctx.subscription_id:
            lines.append(f"Subscription: #{ctx.subscription_id}")

        return self.blocks.section("\n".join(lines))

    def _build_ecommerce_details(self, ctx: MessageContext) -> dict[str, Any]:
        """Build e-commerce order details with line items."""
        order_display = ctx.order_number or "N/A"
        lines = [f"🛒 *Order #{order_display}*"]

        if ctx.amount is not None:
            lines.append(f"Amount: {ctx.currency} {ctx.amount:,.2f}")

        # Add line items
        if ctx.line_items:
            for item in ctx.line_items[:5]:  # Max 5 items
                qty = item.get("quantity", 1)
                name = item.get("name", "Item")
                price = item.get("price", 0)
                lines.append(f"• {qty}x {name} (${price:.2f})")

            if len(ctx.line_items) > 5:
                remaining = len(ctx.line_items) - 5
                lines.append(f"_...and {remaining} more items_")

        return self.blocks.section("\n".join(lines))

    def _get_header_text(
        self, ctx: MessageContext, company_name: str
    ) -> tuple[str, str]:
        """Get emoji and title based on event type."""
        if ctx.event_type == "payment_success":
            if ctx.provider_type == ProviderType.ECOMMERCE:
                return "💰", f"New order from {company_name}"
            return "💰", f"Payment received from {company_name}"
        elif ctx.event_type == "payment_failure":
            return "❌", f"Payment failed for {company_name}"
        elif ctx.event_type == "subscription_created":
            return "🎉", f"New subscription for {company_name}"
        elif ctx.event_type == "subscription_canceled":
            return "⚠️", f"Subscription canceled for {company_name}"
        else:
            title = ctx.event_type.replace("_", " ").title()
            return "ℹ️", f"{title} for {company_name}"

    def _format_payment_type(self, ctx: MessageContext) -> str:
        """Format payment type badge."""
        if ctx.is_recurring:
            if ctx.billing_interval:
                return f"🔄 Recurring ({ctx.billing_interval.title()})"
            return "🔄 Recurring"
        return "💵 One-Time"

    def _get_color(self, event_type: str) -> str:
        """Get sidebar color for event type."""
        colors = {
            "payment_success": "#28a745",
            "payment_failure": "#dc3545",
            "subscription_created": "#17a2b8",
            "subscription_canceled": "#ffc107",
        }
        return colors.get(event_type, "#17a2b8")
