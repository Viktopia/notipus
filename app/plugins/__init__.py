"""Unified plugin system for Notipus.

This package provides a consistent plugin architecture for:
- Enrichment plugins: Enrich customer data with company information
- Source plugins: Receive and process webhooks from payment providers
- Destination plugins: Format and deliver notifications to various platforms

Usage:
    from plugins import PluginRegistry, PluginType
    from plugins.enrichment import BaseEnrichmentPlugin
    from plugins.sources import BaseSourcePlugin
    from plugins.destinations import BaseDestinationPlugin

    # Get the registry
    registry = PluginRegistry.instance()

    # Discover all plugins
    registry.discover()

    # Get plugins by type
    enrichment_plugins = registry.get_enabled(PluginType.ENRICHMENT)
    source_plugins = registry.get_enabled(PluginType.SOURCE)
    destination_plugins = registry.get_enabled(PluginType.DESTINATION)
"""

from plugins.base import (
    BasePlugin,
    PluginCapability,
    PluginMetadata,
    PluginType,
)
from plugins.registry import PluginRegistry, register_plugin

__all__ = [
    "BasePlugin",
    "PluginCapability",
    "PluginMetadata",
    "PluginRegistry",
    "PluginType",
    "register_plugin",
]
