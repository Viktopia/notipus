import logging
from typing import Any, Dict

import requests
from webhooks.models.notification import Notification

logger = logging.getLogger(__name__)

# Default timeout for Slack API requests (seconds)
DEFAULT_TIMEOUT = 30


class SlackClient:
    """Client for sending messages to Slack"""

    def __init__(self, webhook_url: str, timeout: int = DEFAULT_TIMEOUT):
        """
        Initialize the Slack client with webhook URL.

        Args:
            webhook_url: The Slack incoming webhook URL
            timeout: Request timeout in seconds (default: 30)
        """
        self.webhook_url = webhook_url
        self.timeout = timeout

    def send_message(self, message: Dict[str, Any]) -> bool:
        """Send a message to Slack using the webhook URL"""
        if self.webhook_url is None:
            raise ValueError("Webhook URL is not configured")
        try:
            response = requests.post(
                self.webhook_url,
                json=message,
                timeout=self.timeout,
            )
            response.raise_for_status()
            return True
        except requests.exceptions.Timeout:
            logger.error(
                "Slack request timed out",
                extra={"timeout": self.timeout},
            )
            raise RuntimeError("Slack request timed out") from None
        except requests.exceptions.RequestException as e:
            logger.error(
                "Failed to send message to Slack",
                extra={"error": str(e)},
                exc_info=True,
            )
            raise RuntimeError("Failed to send notification to Slack") from e

    def send_notification(self, notification: Notification) -> bool:
        """Send a notification to Slack"""
        return self.send_message(notification.to_slack_message())
