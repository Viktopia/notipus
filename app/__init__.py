from datetime import datetime
from typing import Dict, Any, Optional
import os
import logging
from logging.config import dictConfig

from flask import Flask, request, jsonify
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration
import requests

from .event_processor import EventProcessor
from .models import PaymentEvent
from .providers import ChargifyProvider, ShopifyProvider
from .providers.base import InvalidDataError


def configure_logging():
    """Configure logging for the application"""
    dictConfig({
        'version': 1,
        'formatters': {
            'default': {
                'format': '[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
            },
            'json': {
                'class': 'pythonjsonlogger.jsonlogger.JsonFormatter',
                'format': '%(asctime)s %(levelname)s %(name)s %(message)s %(extra)s',
            }
        },
        'handlers': {
            'wsgi': {
                'class': 'logging.StreamHandler',
                'stream': 'ext://flask.logging.wsgi_errors_stream',
                'formatter': 'default'
            },
            'json': {
                'class': 'logging.StreamHandler',
                'formatter': 'json'
            }
        },
        'root': {
            'level': 'INFO',
            'handlers': ['json' if os.getenv('LOG_FORMAT') == 'json' else 'wsgi']
        }
    })


def create_app(config: Optional[Dict[str, Any]] = None) -> Flask:
    """Create and configure the Flask application"""

    # Configure logging first
    configure_logging()

    app = Flask(__name__)

    # Load default configuration
    app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY", "dev"),
        SLACK_WEBHOOK_URL=os.getenv("SLACK_WEBHOOK_URL", ""),
        CHARGIFY_WEBHOOK_SECRET=os.getenv("CHARGIFY_WEBHOOK_SECRET", ""),
        SHOPIFY_WEBHOOK_SECRET=os.getenv("SHOPIFY_WEBHOOK_SECRET", ""),
    )

    # Override with test config if provided
    if config:
        app.config.update(config)

    # Register blueprints
    from app.routes import bp as webhooks_bp
    app.register_blueprint(webhooks_bp)

    # Initialize providers
    from app.providers import ChargifyProvider, ShopifyProvider
    from app.event_processor import EventProcessor

    app.chargify_provider = ChargifyProvider(
        webhook_secret=app.config["CHARGIFY_WEBHOOK_SECRET"]
    )
    app.shopify_provider = ShopifyProvider(
        webhook_secret=app.config["SHOPIFY_WEBHOOK_SECRET"]
    )
    app.event_processor = EventProcessor()

    return app
