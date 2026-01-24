"""Plugin registry for enrichment providers.

This module provides the central registry for managing enrichment plugins,
including registration, auto-discovery, and lifecycle management.
"""

import importlib
import logging
import pkgutil
from typing import Any

from django.conf import settings

from .base import BaseEnrichmentPlugin, PluginMetadata

logger = logging.getLogger(__name__)


class EnrichmentPluginRegistry:
    """Central registry for enrichment plugins.

    This is a singleton that manages all enrichment plugins. Plugins can be:
    - Manually registered via register()
    - Auto-discovered via discover()

    The registry handles:
    - Plugin registration and storage
    - Plugin instantiation and configuration
    - Filtering by availability and enabled status

    Usage:
        registry = EnrichmentPluginRegistry()
        registry.discover()  # Auto-discover plugins
        plugins = registry.get_enabled_plugins()
    """

    _instance: "EnrichmentPluginRegistry | None" = None
    _plugins: dict[str, type[BaseEnrichmentPlugin]]
    _instances: dict[str, BaseEnrichmentPlugin]
    _initialized: bool

    def __new__(cls) -> "EnrichmentPluginRegistry":
        """Create or return the singleton instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._plugins = {}
            cls._instance._instances = {}
            cls._instance._initialized = False
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton instance.

        Useful for testing to get a fresh registry.
        """
        cls._instance = None

    def register(self, plugin_class: type[BaseEnrichmentPlugin]) -> None:
        """Register a plugin class.

        Args:
            plugin_class: The plugin class to register (not an instance).

        Raises:
            ValueError: If plugin_class doesn't have valid metadata.
        """
        try:
            metadata = plugin_class.get_metadata()
        except Exception as e:
            logger.error(f"Failed to get metadata from {plugin_class}: {e}")
            raise ValueError(f"Invalid plugin class: {e}") from e

        if metadata.name in self._plugins:
            logger.warning(
                f"Plugin '{metadata.name}' already registered, "
                f"replacing with {plugin_class.__name__}"
            )

        self._plugins[metadata.name] = plugin_class
        logger.debug(f"Registered plugin: {metadata.name} ({metadata.display_name})")

    def unregister(self, name: str) -> bool:
        """Unregister a plugin by name.

        Args:
            name: The plugin name to unregister.

        Returns:
            True if plugin was unregistered, False if not found.
        """
        if name in self._plugins:
            del self._plugins[name]
            if name in self._instances:
                del self._instances[name]
            logger.debug(f"Unregistered plugin: {name}")
            return True
        return False

    def discover(self) -> list[str]:
        """Auto-discover plugins in the providers package.

        Scans app/core/providers/ for modules containing BaseEnrichmentPlugin
        subclasses and registers them.

        Returns:
            List of discovered plugin names.
        """
        discovered: list[str] = []

        # Import the providers package
        try:
            import core.providers as providers_package
        except ImportError:
            logger.warning("Could not import core.providers package")
            return discovered

        # Scan for submodules
        package_path = providers_package.__path__
        for _importer, module_name, _is_pkg in pkgutil.iter_modules(package_path):
            # Skip base and registry modules
            if module_name in ("base", "registry", "__init__"):
                continue

            try:
                module = importlib.import_module(f"core.providers.{module_name}")
                discovered.extend(self._register_plugins_from_module(module))
            except Exception as e:
                logger.warning(f"Failed to import module {module_name}: {e}")

        logger.info(f"Discovered {len(discovered)} plugins: {discovered}")
        return discovered

    def _register_plugins_from_module(self, module: Any) -> list[str]:
        """Register all plugin classes from a module.

        Args:
            module: The module to scan for plugins.

        Returns:
            List of registered plugin names.
        """
        registered: list[str] = []

        for attr_name in dir(module):
            attr = getattr(module, attr_name)

            # Check if it's a class that inherits from BaseEnrichmentPlugin
            if (
                isinstance(attr, type)
                and issubclass(attr, BaseEnrichmentPlugin)
                and attr is not BaseEnrichmentPlugin
                and not attr_name.startswith("_")
            ):
                try:
                    self.register(attr)
                    metadata = attr.get_metadata()
                    registered.append(metadata.name)
                except Exception as e:
                    logger.warning(f"Failed to register {attr_name}: {e}")

        return registered

    def get_plugin_class(self, name: str) -> type[BaseEnrichmentPlugin] | None:
        """Get a registered plugin class by name.

        Args:
            name: The plugin name.

        Returns:
            The plugin class, or None if not found.
        """
        return self._plugins.get(name)

    def get_all_plugins(self) -> dict[str, type[BaseEnrichmentPlugin]]:
        """Get all registered plugin classes.

        Returns:
            Dictionary mapping plugin names to classes.
        """
        return dict(self._plugins)

    def get_plugin_metadata(self, name: str) -> PluginMetadata | None:
        """Get metadata for a registered plugin.

        Args:
            name: The plugin name.

        Returns:
            PluginMetadata, or None if plugin not found.
        """
        plugin_class = self._plugins.get(name)
        if plugin_class:
            return plugin_class.get_metadata()
        return None

    def is_plugin_enabled(self, name: str) -> bool:
        """Check if a plugin is enabled in settings.

        Args:
            name: The plugin name.

        Returns:
            True if enabled (default True if not in settings).
        """
        plugin_config = self._get_plugin_config(name)
        return plugin_config.get("enabled", True)

    def is_plugin_available(self, name: str) -> bool:
        """Check if a plugin is available (has required config).

        Args:
            name: The plugin name.

        Returns:
            True if the plugin is available for use.
        """
        plugin_class = self._plugins.get(name)
        if not plugin_class:
            return False
        return plugin_class.is_available()

    def _get_plugin_config(self, name: str) -> dict[str, Any]:
        """Get configuration for a plugin from Django settings.

        Args:
            name: The plugin name.

        Returns:
            Configuration dictionary (empty if not configured).
        """
        enrichment_plugins = getattr(settings, "ENRICHMENT_PLUGINS", {})
        return enrichment_plugins.get(name, {})

    def get_instance(self, name: str) -> BaseEnrichmentPlugin | None:
        """Get or create an instance of a plugin.

        Instances are cached for reuse. The plugin is configured with
        settings from ENRICHMENT_PLUGINS.

        Args:
            name: The plugin name.

        Returns:
            Configured plugin instance, or None if not found/unavailable.
        """
        # Return cached instance if available
        if name in self._instances:
            return self._instances[name]

        plugin_class = self._plugins.get(name)
        if not plugin_class:
            logger.warning(f"Plugin '{name}' not found in registry")
            return None

        # Check availability
        if not plugin_class.is_available():
            logger.info(f"Plugin '{name}' is not available (missing config?)")
            return None

        # Create and configure instance
        try:
            instance = plugin_class()
            config = self._get_plugin_config(name).get("config", {})
            instance.configure(config)
            self._instances[name] = instance
            logger.debug(f"Created instance of plugin '{name}'")
            return instance
        except Exception as e:
            logger.error(f"Failed to create instance of plugin '{name}': {e}")
            return None

    def get_enabled_plugins(self) -> list[BaseEnrichmentPlugin]:
        """Get all enabled and available plugin instances.

        Returns plugins that are:
        - Registered in the registry
        - Enabled in settings (or not explicitly disabled)
        - Available (is_available() returns True)

        Plugins are sorted by priority (highest first).

        Returns:
            List of configured plugin instances.
        """
        plugins: list[tuple[int, BaseEnrichmentPlugin]] = []

        for name in self._plugins:
            if not self.is_plugin_enabled(name):
                logger.debug(f"Plugin '{name}' is disabled in settings")
                continue

            instance = self.get_instance(name)
            if instance:
                # Get priority from settings or metadata
                config = self._get_plugin_config(name)
                priority = config.get("priority", instance.get_metadata().priority)
                plugins.append((priority, instance))

        # Sort by priority (highest first)
        plugins.sort(key=lambda x: x[0], reverse=True)

        return [plugin for _, plugin in plugins]

    def list_plugins(self) -> list[dict[str, Any]]:
        """List all registered plugins with their status.

        Returns:
            List of dictionaries with plugin info.
        """
        result = []
        for name, plugin_class in self._plugins.items():
            metadata = plugin_class.get_metadata()
            result.append(
                {
                    "name": metadata.name,
                    "display_name": metadata.display_name,
                    "version": metadata.version,
                    "description": metadata.description,
                    "capabilities": [cap.value for cap in metadata.capabilities],
                    "priority": metadata.priority,
                    "enabled": self.is_plugin_enabled(name),
                    "available": self.is_plugin_available(name),
                }
            )
        return result


# Convenience function for registration decorator
def register_plugin(cls: type[BaseEnrichmentPlugin]) -> type[BaseEnrichmentPlugin]:
    """Decorator to register a plugin class.

    Usage:
        @register_plugin
        class MyPlugin(BaseEnrichmentPlugin):
            ...

    Args:
        cls: The plugin class to register.

    Returns:
        The same class (for decorator chaining).
    """
    registry = EnrichmentPluginRegistry()
    registry.register(cls)
    return cls
