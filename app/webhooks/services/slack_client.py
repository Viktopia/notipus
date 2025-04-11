import logging
from typing import Any, Dict

import requests

from webhooks.models.notification import Notification

logger = logging.getLogger(__name__)


class SlackClient:
    """Client for sending messages to Slack"""

    def __init__(self, webhook_url: str):
        """Initialize the Slack client with webhook URL"""
        self.webhook_url = webhook_url

    def send_message(self, message: Dict[str, Any]) -> bool:
        """Send a message to Slack using the webhook URL"""
        if self.webhook_url is None:
            raise Exception("Webhook_url is unset")
        try:
            response = requests.post(self.webhook_url, json=message)
            response.raise_for_status()
            return True
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
