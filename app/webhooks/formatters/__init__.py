"""Notification formatters package.

This package contains formatters that convert RichNotification objects
into platform-specific formats (Slack, Email, Discord, etc.).
"""

from .base import BaseFormatter, FormatterRegistry
from .slack import SlackFormatter

__all__ = [
    "BaseFormatter",
    "FormatterRegistry",
    "SlackFormatter",
]
