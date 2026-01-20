"""Notification models for Slack message formatting.

This module contains the core notification models used to construct
and format Slack messages for webhook events.
"""

from dataclasses import dataclass, field
from typing import Any, ClassVar


@dataclass
class Section:
    """A section of a notification.

    Represents a logical grouping of fields within a Slack notification,
    maintaining field order for consistent display.

    Attributes:
        title: Section header text.
    """

    title: str
    _fields: list[tuple[str, str]] = field(default_factory=list, init=False)

    def __init__(self, title: str, fields: dict[str, str] | None = None) -> None:
        """Initialize a section with a title and optional fields.

        Args:
            title: The section header text.
            fields: Optional dictionary of field key-value pairs.
        """
        self.title = title
        self._fields: list[tuple[str, str]] = []
        if fields:
            for key, value in fields.items():
                self._fields.append((key, value))

    @property
    def fields(self) -> list[tuple[str, str]]:
        """Get the fields as a list of tuples (key, value).

        Returns:
            List of (key, value) tuples in insertion order.
        """
        return self._fields

    def to_dict(self) -> dict[str, Any]:
        """Convert section to Slack block format.

        Returns:
            Dictionary representing a Slack block kit section.
        """
        return {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{self.title}*\n"
                + "\n".join(f"*{k}*: {v}" for k, v in self._fields),
            },
        }

    def to_slack_fields(self) -> list[dict[str, str | bool]]:
        """Convert fields to Slack attachment format.

        Returns:
            List of field dictionaries for Slack attachments.
        """
        return [
            {"title": key, "value": value, "short": True} for key, value in self._fields
        ]


@dataclass
class Notification:
    """A notification to be sent to Slack.

    Represents a complete notification message with sections,
    styling, and optional action buttons.

    Attributes:
        title: Main notification title.
        sections: List of content sections.
        color: Sidebar color (hex code).
        emoji: Emoji to display with title.
        action_buttons: Optional interactive buttons.

    Class Attributes:
        STATUS_COLORS: Mapping of status names to hex colors.
    """

    title: str
    sections: list[Section]
    color: str = field(default="#17a2b8")
    emoji: str = field(default="ℹ️")
    action_buttons: list[dict[str, str]] = field(default_factory=list)
    _status: str = field(init=False)

    STATUS_COLORS: ClassVar[dict[str, str]] = {
        "success": "#28a745",  # Green
        "failed": "#dc3545",  # Red
        "warning": "#ffc107",  # Yellow
        "info": "#17a2b8",  # Blue
    }

    def __post_init__(self) -> None:
        """Set initial status based on color."""
        self._status = self._get_status_from_color(self.color)

    @property
    def status(self) -> str:
        """Get the notification status.

        Returns:
            Current status string (success, failed, warning, info).
        """
        return self._status

    @status.setter
    def status(self, value: str) -> None:
        """Set the status and update color accordingly.

        Args:
            value: New status value. Invalid values default to "info".
        """
        if value not in self.STATUS_COLORS:
            value = "info"
        self._status = value
        self.color = self.STATUS_COLORS[value]

    def _get_status_from_color(self, color: str) -> str:
        """Map color to status.

        Args:
            color: Hex color code.

        Returns:
            Status string corresponding to the color.
        """
        for status, status_color in self.STATUS_COLORS.items():
            if status_color == color:
                return status
        return "info"

    def to_slack_message(self) -> dict[str, Any]:
        """Convert the notification to a Slack message format.

        Returns:
            Dictionary containing blocks and color for Slack API.
        """
        blocks: list[dict[str, Any]] = []

        # Add header with emoji
        blocks.append(
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{self.emoji} {self.title}",
                    "emoji": True,
                },
            }
        )

        # Add sections
        for section in self.sections:
            blocks.append(section.to_dict())

        # Add action buttons if present
        if self.action_buttons:
            blocks.append(
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": button["text"]},
                            "url": button["url"],
                            "style": button.get("style", "default"),
                        }
                        for button in self.action_buttons
                    ],
                }
            )

        return {"blocks": blocks, "color": self.color}
