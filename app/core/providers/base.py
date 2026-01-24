"""Base classes and metadata for enrichment plugins.

This module provides the plugin interface for domain enrichment providers,
including metadata, capabilities, and lifecycle management.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class PluginCapability(Enum):
    """Capabilities a plugin can provide for domain enrichment.

    Each capability represents a type of data the plugin can retrieve.
    Used for data blending to determine which plugin should provide
    specific fields.
    """

    LOGO = "logo"
    DESCRIPTION = "description"
    INDUSTRY = "industry"
    SOCIAL_LINKS = "social_links"
    EMPLOYEE_COUNT = "employee_count"
    FUNDING = "funding"
    COLORS = "colors"
    YEAR_FOUNDED = "year_founded"


@dataclass
class PluginMetadata:
    """Metadata describing an enrichment plugin.

    Attributes:
        name: Unique identifier for the plugin (e.g., "brandfetch").
        display_name: Human-readable name (e.g., "Brandfetch").
        version: Semantic version string (e.g., "1.0.0").
        description: Brief description of what the plugin does.
        capabilities: Set of data types this plugin can provide.
        priority: Priority for data blending (higher = preferred). Default 0.
        config_keys: List of required configuration keys (e.g., ["api_key"]).
    """

    name: str
    display_name: str
    version: str
    description: str
    capabilities: set[PluginCapability]
    priority: int = 0
    config_keys: list[str] = field(default_factory=list)


class BaseEnrichmentPlugin(ABC):
    """Base class for enrichment plugins.

    Plugins must implement:
    - get_metadata(): Return plugin metadata (called before instantiation)
    - enrich_domain(): Perform the actual domain enrichment

    Plugins may override:
    - is_available(): Check if plugin can be used (e.g., API key exists)
    - configure(): Configure plugin with settings from Django config
    """

    @classmethod
    @abstractmethod
    def get_metadata(cls) -> PluginMetadata:
        """Return plugin metadata.

        This is called before instantiation to get plugin information
        for registration and configuration.

        Returns:
            PluginMetadata describing this plugin.
        """
        pass

    @classmethod
    def is_available(cls) -> bool:
        """Check if plugin can be used.

        Override this to check for required configuration (e.g., API keys).
        Default implementation returns True.

        Returns:
            True if the plugin is available for use.
        """
        return True

    def configure(self, config: dict[str, Any]) -> None:
        """Configure plugin with settings.

        Called after instantiation with configuration from Django settings.
        Override to set up API keys, URLs, timeouts, etc.

        This is intentionally not abstract - plugins can choose to override
        this method if they need configuration, or use the default no-op.

        Args:
            config: Configuration dictionary from ENRICHMENT_PLUGINS settings.
        """
        # Default implementation stores config for potential future use
        # Subclasses should override to extract specific configuration
        _ = config  # Acknowledge parameter, no-op by default

    @abstractmethod
    def enrich_domain(self, domain: str) -> dict[str, Any]:
        """Enrich domain and return data.

        Args:
            domain: The domain to enrich (e.g., "example.com").

        Returns:
            Dictionary containing enrichment data. Should include:
            - name: Company name
            - logo_url: URL to company logo
            - brand_info: Dict with additional data (description, industry, etc.)
        """
        pass

    def get_provider_name(self) -> str:
        """Return unique provider identifier.

        Returns the plugin name from metadata, falling back to class name.

        Returns:
            String identifier for this provider.
        """
        try:
            return self.get_metadata().name
        except (NotImplementedError, AttributeError):
            return self.__class__.__name__.lower().replace("plugin", "")
