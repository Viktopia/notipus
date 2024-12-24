import os


class Config:
    """Application configuration."""

    # Webhook secrets
    SHOPIFY_WEBHOOK_SECRET = os.environ.get("SHOPIFY_WEBHOOK_SECRET", "")
    CHARGIFY_WEBHOOK_SECRET = os.environ.get("CHARGIFY_WEBHOOK_SECRET", "")

    # Slack configuration
    SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")
