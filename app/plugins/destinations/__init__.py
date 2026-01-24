"""Destination plugins for notification delivery.

Destination plugins format and deliver notifications to various platforms
(Slack, Email, Discord, etc.).

Usage:
    from plugins.destinations import BaseDestinationPlugin
    from plugins import PluginRegistry, PluginType

    # Get a specific destination plugin
    registry = PluginRegistry.instance()
    slack_plugin = registry.get(PluginType.DESTINATION, "slack")

    # Format and send a notification
    formatted = slack_plugin.format(notification)
    success = slack_plugin.send(formatted, credentials={"webhook_url": "..."})
"""

from plugins.destinations.base import BaseDestinationPlugin

__all__ = [
    "BaseDestinationPlugin",
]
