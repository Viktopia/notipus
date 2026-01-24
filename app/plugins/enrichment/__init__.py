"""Enrichment plugins for domain/company data enrichment.

Enrichment plugins retrieve company information (logos, descriptions,
industry classification, etc.) from external APIs.

Usage:
    from plugins.enrichment import BaseEnrichmentPlugin
    from plugins import PluginRegistry, PluginType

    # Get all enabled enrichment plugins
    registry = PluginRegistry.instance()
    plugins = registry.get_enabled(PluginType.ENRICHMENT)

    # Enrich a domain
    for plugin in plugins:
        data = plugin.enrich_domain("example.com")
"""

from plugins.enrichment.base import BaseEnrichmentPlugin, EnrichmentCapability

__all__ = [
    "BaseEnrichmentPlugin",
    "EnrichmentCapability",
]
