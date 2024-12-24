from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple


@dataclass
class Section:
    """A section of a notification"""

    def __init__(self, title: str, fields: Dict[str, str] = None):
        """Initialize a section with a title and fields"""
        self.title = title
        self._fields = []  # List of tuples to maintain order
        if fields:
            for key, value in fields.items():
                self._fields.append((key, value))

    @property
    def fields(self) -> List[Tuple[str, str]]:
        """Get the fields as a list of tuples (key, value)"""
        return self._fields

    def to_dict(self) -> Dict[str, Any]:
        """Convert section to Slack block format"""
        return {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{self.title}*\n"
                + "\n".join(f"*{k}*: {v}" for k, v in self._fields),
            },
        }

    def to_slack_fields(self) -> List[Dict[str, str]]:
        """Convert fields to Slack format"""
        return [
            {"title": key, "value": value, "short": True} for key, value in self._fields
        ]


@dataclass
class Notification:
    """A notification to be sent to Slack"""

    title: str
    sections: List[Section]
    color: str = field(default="#17a2b8")  # Default info color
    emoji: str = field(default="ℹ️")
    action_buttons: List[Dict[str, str]] = field(default_factory=list)
    _status: str = field(init=False)

    STATUS_COLORS = {
        "success": "#28a745",  # Green
        "failed": "#dc3545",  # Red
        "warning": "#ffc107",  # Yellow
        "info": "#17a2b8",  # Blue
    }

    def __post_init__(self):
        """Set initial status based on color"""
        self._status = self._get_status_from_color(self.color)

    @property
    def status(self) -> str:
        """Get the notification status"""
        return self._status

    @status.setter
    def status(self, value: str) -> None:
        """Set the status and update color accordingly"""
        if value not in self.STATUS_COLORS:
            value = "info"
        self._status = value
        self.color = self.STATUS_COLORS[value]

    def _get_status_from_color(self, color: str) -> str:
        """Map color to status"""
        for status, status_color in self.STATUS_COLORS.items():
            if status_color == color:
                return status
        return "info"

    def to_slack_message(self) -> Dict[str, Any]:
        """Convert the notification to a Slack message format"""
        blocks = []

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
