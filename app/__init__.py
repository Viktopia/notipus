from datetime import datetime
from typing import Dict, Any, Optional
import os

from flask import Flask, request, jsonify
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration
import requests

from .event_processor import EventProcessor
from .models import PaymentEvent
from .providers import ChargifyProvider, ShopifyProvider
from .providers.base import InvalidDataError


def create_app(config: Optional[Dict[str, Any]] = None) -> Flask:
    """Create and configure the Flask application"""
    # Initialize Sentry if DSN is provided
    sentry_dsn = os.getenv("SENTRY_DSN")
    if sentry_dsn:
        sentry_sdk.init(
            dsn=sentry_dsn,
            integrations=[FlaskIntegration()],
            traces_sample_rate=1.0,
        )

    app = Flask(__name__)

    # Load default configuration
    app.config.update(
        CHARGIFY_WEBHOOK_SECRET=os.getenv("CHARGIFY_WEBHOOK_SECRET", ""),
        SHOPIFY_WEBHOOK_SECRET=os.getenv("SHOPIFY_WEBHOOK_SECRET", ""),
        SLACK_WEBHOOK_URL=os.getenv("SLACK_WEBHOOK_URL", ""),
    )

    # Override with custom config if provided
    if config:
        app.config.update(config)

    # Validate required environment variables
    required_vars = ["SLACK_WEBHOOK_URL"]
    missing_vars = [var for var in required_vars if not app.config.get(var)]
    if missing_vars:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing_vars)}"
        )

    # Initialize providers
    chargify = ChargifyProvider(
        webhook_secret=app.config["CHARGIFY_WEBHOOK_SECRET"],
    )
    shopify = ShopifyProvider(
        webhook_secret=app.config["SHOPIFY_WEBHOOK_SECRET"],
    )

    # Initialize event processor
    processor = EventProcessor()

    @app.route("/webhooks/chargify", methods=["POST"])
    def chargify_webhook():
        """Handle Chargify webhooks"""
        try:
            # Validate webhook signature
            if not chargify.validate_webhook(request):
                return jsonify({"error": "Invalid webhook signature"}), 401

            # Parse webhook data
            try:
                event = chargify.parse_webhook(request)
            except InvalidDataError as e:
                return jsonify({"error": str(e)}), 400

            if not event:
                return jsonify({"error": "Invalid webhook data"}), 400

            # Create payment event
            try:
                timestamp = datetime.fromisoformat(
                    event["timestamp"].replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                timestamp = datetime.now()

            payment_event = PaymentEvent(
                id=event["id"],
                event_type=event["type"],
                customer_id=event["customer_id"],
                amount=event["amount"],
                currency=event["currency"],
                status=event["status"],
                timestamp=timestamp,
                metadata={
                    **event["metadata"],
                    "source": "chargify",
                },
            )

            # Format notification with customer data
            notification = processor.format_notification(
                event=payment_event,
                customer_data=event["customer_data"],
            )

            # Convert to Slack message format and send
            message = notification.to_slack_message()
            response = requests.post(app.config["SLACK_WEBHOOK_URL"], json=message)
            response.raise_for_status()

            return jsonify({"status": "success"}), 200

        except requests.exceptions.RequestException as e:
            return jsonify({"error": f"Failed to send notification: {str(e)}"}), 500
        except Exception as e:
            if sentry_dsn:
                sentry_sdk.capture_exception(e)
            return jsonify({"error": str(e)}), 500

    @app.route("/webhooks/shopify", methods=["POST"])
    def shopify_webhook():
        """Handle Shopify webhooks"""
        try:
            # Get webhook topic from header
            topic = request.headers.get("X-Shopify-Topic")
            if not topic:
                return jsonify({"error": "Missing webhook topic"}), 400

            # Validate webhook signature
            if not shopify.validate_webhook(request):
                return jsonify({"error": "Invalid webhook signature"}), 401

            # Parse webhook data
            try:
                event = shopify.parse_webhook(request, topic=topic)
            except InvalidDataError as e:
                return jsonify({"error": str(e)}), 400

            if not event:
                return jsonify({"error": "Invalid webhook data"}), 400

            # Create payment event
            try:
                timestamp = datetime.fromisoformat(
                    event["timestamp"].replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                timestamp = datetime.now()

            payment_event = PaymentEvent(
                id=event["id"],
                event_type=event["type"],
                customer_id=event["customer_id"],
                amount=event["amount"],
                currency=event["currency"],
                status=event["status"],
                timestamp=timestamp,
                metadata={
                    **event["metadata"],
                    "source": "shopify",
                    "shop_domain": request.headers.get("X-Shopify-Shop-Domain", ""),
                },
            )

            # Format notification with customer data
            notification = processor.format_notification(
                event=payment_event,
                customer_data=event["customer_data"],
            )

            # Convert to Slack message format and send
            message = notification.to_slack_message()
            response = requests.post(app.config["SLACK_WEBHOOK_URL"], json=message)
            response.raise_for_status()

            return jsonify({"status": "success"}), 200

        except requests.exceptions.RequestException as e:
            return jsonify({"error": f"Failed to send notification: {str(e)}"}), 500
        except Exception as e:
            if sentry_dsn:
                sentry_sdk.capture_exception(e)
            return jsonify({"error": str(e)}), 500

    @app.route("/health", methods=["GET"])
    def health_check():
        """Health check endpoint"""
        return jsonify({"status": "healthy"}), 200

    return app
