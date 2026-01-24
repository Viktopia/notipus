"""Base formatter interface and registry for notification targets.

This module defines the BaseFormatter abstract class and FormatterRegistry
for managing notification formatters.
"""

from abc import ABC, abstractmethod
from typing import Any

from webhooks.models.rich_notification import RichNotification


class BaseFormatter(ABC):
    """Abstract base class for notification formatters.

    Formatters convert RichNotification objects into platform-specific
    formats (Slack Block Kit, HTML Email, Discord Embeds, etc.).
    """

    @classmethod
    @abstractmethod
    def get_target_name(cls) -> str:
        """Return the target platform identifier.

        Returns:
            Target identifier string (e.g., "slack", "email", "discord").
        """
        pass

    @abstractmethod
    def format(self, notification: RichNotification) -> Any:
        """Format a notification for the target platform.

        Args:
            notification: RichNotification to format.

        Returns:
            Platform-specific format (dict for Slack, str for email, etc.).
        """
        pass


class FormatterRegistry:
    """Registry for notification formatters.

    Provides registration and lookup of formatters by target name.
    Formatters self-register on import via the @register decorator.

    Example:
        >>> SlackFormatter.register()
        >>> formatter = FormatterRegistry.get("slack")
        >>> output = formatter.format(notification)
    """

    _formatters: dict[str, type[BaseFormatter]] = {}

    @classmethod
    def register(cls, formatter_class: type[BaseFormatter]) -> type[BaseFormatter]:
        """Register a formatter class.

        Can be used as a class decorator:

            @FormatterRegistry.register
            class SlackFormatter(BaseFormatter):
                ...

        Args:
            formatter_class: Formatter class to register.

        Returns:
            The formatter class (for decorator chaining).
        """
        target_name = formatter_class.get_target_name()
        cls._formatters[target_name] = formatter_class
        return formatter_class

    @classmethod
    def get(cls, target: str) -> BaseFormatter:
        """Get a formatter instance for the target platform.

        Args:
            target: Target platform identifier.

        Returns:
            Formatter instance.

        Raises:
            KeyError: If no formatter registered for target.
        """
        if target not in cls._formatters:
            available = ", ".join(cls._formatters.keys()) or "(none)"
            raise KeyError(
                f"No formatter registered for target '{target}'. "
                f"Available: {available}"
            )
        return cls._formatters[target]()

    @classmethod
    def get_available_targets(cls) -> list[str]:
        """Get list of available target platforms.

        Returns:
            List of registered target identifiers.
        """
        return list(cls._formatters.keys())

    @classmethod
    def is_registered(cls, target: str) -> bool:
        """Check if a target has a registered formatter.

        Args:
            target: Target platform identifier.

        Returns:
            True if formatter is registered, False otherwise.
        """
        return target in cls._formatters

    @classmethod
    def clear(cls) -> None:
        """Clear all registered formatters (for testing)."""
        cls._formatters.clear()
