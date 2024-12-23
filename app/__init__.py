from typing import Dict, Any, Optional
import os
import logging
from flask import Flask
from pythonjsonlogger.jsonlogger import JsonFormatter
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration
from .event_processor import EventProcessor
from .providers import ChargifyProvider, ShopifyProvider

# Configure logging
logger = logging.getLogger()
logHandler = logging.StreamHandler()
formatter = JsonFormatter()
logHandler.setFormatter(formatter)
logger.addHandler(logHandler)

# Set log level based on DEBUG env var
debug_mode = os.getenv("DEBUG", "false").lower() == "true"
logger.setLevel(logging.DEBUG if debug_mode else logging.INFO)


def create_app(config: Optional[Dict[str, Any]] = None) -> Flask:
    """Create and configure the Flask application"""
    # Initialize Sentry if DSN is configured
    sentry_dsn = os.getenv("SENTRY_DSN")
    if sentry_dsn:
        sentry_sdk.init(
            dsn=sentry_dsn,
            integrations=[FlaskIntegration()],
            traces_sample_rate=1.0,
            environment=os.getenv("FLASK_ENV", "production"),
        )

    app = Flask(__name__)

    # Load configuration
    app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY", "dev"),
        SLACK_WEBHOOK_URL=os.getenv("SLACK_WEBHOOK_URL"),
        CHARGIFY_WEBHOOK_SECRET=os.getenv("CHARGIFY_WEBHOOK_SECRET"),
        SHOPIFY_WEBHOOK_SECRET=os.getenv("SHOPIFY_WEBHOOK_SECRET"),
        DEBUG=debug_mode,
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
