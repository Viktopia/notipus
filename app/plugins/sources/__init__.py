"""Source plugins for webhook processing.

Source plugins receive and process webhooks from payment providers
and other external services.

Usage:
    from plugins.sources import BaseSourcePlugin
    from plugins import PluginRegistry, PluginType

    # Get a specific source plugin instance
    registry = PluginRegistry.instance()
    stripe_plugin = registry.get(PluginType.SOURCE, "stripe", webhook_secret="...")

    # Validate and parse a webhook
    if stripe_plugin.validate_webhook(request):
        event_data = stripe_plugin.parse_webhook(request)
"""

from plugins.sources.base import (
    APIError,
    BaseSourcePlugin,
    CustomerData,
    CustomerNotFoundError,
    InvalidDataError,
    InvalidEventType,
    PaymentEvent,
    SubscriptionData,
    WebhookError,
    WebhookValidationError,
)

__all__ = [
    "APIError",
    "BaseSourcePlugin",
    "CustomerData",
    "CustomerNotFoundError",
    "InvalidDataError",
    "InvalidEventType",
    "PaymentEvent",
    "SubscriptionData",
    "WebhookError",
    "WebhookValidationError",
]
