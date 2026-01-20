"""Slack client for sending webhook notifications.

This module provides a client for sending formatted notifications
to Slack using incoming webhooks.
"""

import logging
from typing import Any

import requests
from webhooks.models.notification import Notification

logger = logging.getLogger(__name__)

# Default timeout for Slack API requests (seconds)
DEFAULT_TIMEOUT = 30


class SlackClient:
    """Client for sending messages to Slack.

    Handles HTTP communication with Slack's incoming webhook API
    and provides error handling for common failure scenarios.

    Attributes:
        webhook_url: The Slack incoming webhook URL.
        timeout: Request timeout in seconds.
    """

    def __init__(self, webhook_url: str, timeout: int = DEFAULT_TIMEOUT) -> None:
        """Initialize the Slack client with webhook URL.

        Args:
            webhook_url: The Slack incoming webhook URL.
            timeout: Request timeout in seconds (default: 30).
        """
        self.webhook_url = webhook_url
        self.timeout = timeout

    def send_message(self, message: dict[str, Any]) -> bool:
        """Send a message to Slack using the webhook URL.

        Args:
            message: Dictionary containing the Slack message payload.

        Returns:
            True if message was sent successfully.

        Raises:
            ValueError: If webhook URL is not configured.
            RuntimeError: If the request fails or times out.
        """
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
        """Send a notification to Slack.

        Args:
            notification: Notification object to send.

        Returns:
            True if notification was sent successfully.

        Raises:
            ValueError: If webhook URL is not configured.
            RuntimeError: If the request fails.
        """
        return self.send_message(notification.to_slack_message())
