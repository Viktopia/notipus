from typing import Dict, Any, Optional
import os
from logging.config import dictConfig

from flask import Flask
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration

from .event_processor import EventProcessor
from .providers import ChargifyProvider, ShopifyProvider


def configure_logging():
    """Configure logging for the application"""
    dictConfig(
        {
            "version": 1,
            "formatters": {
                "default": {
                    "format": "[%(asctime)s] %(levelname)s in %(module)s: %(message)s",
                },
                "json": {
                    "class": "pythonjsonlogger.json.JsonFormatter",
                    "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
                },
            },
            "handlers": {
                "wsgi": {
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stdout",
                    "formatter": "json",
                }
            },
            "root": {"level": "INFO", "handlers": ["wsgi"]},
            "loggers": {
                "app.providers.shopify": {
                    "level": "DEBUG",
                    "handlers": ["wsgi"],
                    "propagate": False,
                },
                "app.providers.chargify": {
                    "level": "DEBUG",
                    "handlers": ["wsgi"],
                    "propagate": False,
                },
            },
        }
    )


def create_app(config: Optional[Dict[str, Any]] = None) -> Flask:
    """Create and configure the Flask application"""

    # Configure logging first
    configure_logging()

    app = Flask(__name__)

    # Load default configuration
    app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY", "dev"),
        SLACK_WEBHOOK_URL=os.getenv("SLACK_WEBHOOK_URL"),
        CHARGIFY_WEBHOOK_SECRET=os.getenv("CHARGIFY_WEBHOOK_SECRET", ""),
        SHOPIFY_WEBHOOK_SECRET=os.getenv("SHOPIFY_WEBHOOK_SECRET"),
    )

    # Override with test config if provided
    if config:
        app.config.update(config)

    # Validate required configuration
    required_config = [
        "SLACK_WEBHOOK_URL",
        "SHOPIFY_WEBHOOK_SECRET",
    ]
    missing_config = [key for key in required_config if not app.config.get(key)]
    if missing_config:
        raise ValueError(f"Missing required configuration: {', '.join(missing_config)}")

    # Initialize Sentry if DSN is provided
    sentry_dsn = os.getenv("SENTRY_DSN")
    if sentry_dsn:
        sentry_sdk.init(
            dsn=sentry_dsn,
            integrations=[FlaskIntegration()],
            traces_sample_rate=1.0,
        )

    # Register blueprints
    from app.routes import bp as webhooks_bp

    app.register_blueprint(webhooks_bp)

    # Initialize providers
    app.chargify_provider = ChargifyProvider(
        webhook_secret=app.config["CHARGIFY_WEBHOOK_SECRET"]
    )
    app.shopify_provider = ShopifyProvider(
        webhook_secret=app.config["SHOPIFY_WEBHOOK_SECRET"]
    )
    app.event_processor = EventProcessor()

    return app
