import os
from flask import Flask, request, jsonify
import requests
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration

from .providers import (
    ChargifyProvider,
    ShopifyProvider,
    InvalidDataError,
)
from .event_processor import EventProcessor
from .models import PaymentEvent

# Initialize Sentry if DSN is provided
sentry_dsn = os.environ.get("SENTRY_DSN")
if sentry_dsn:
    sentry_sdk.init(
        dsn=sentry_dsn,
        integrations=[FlaskIntegration()],
        traces_sample_rate=1.0,
        profiles_sample_rate=1.0,
        environment=os.environ.get("ENVIRONMENT", "production"),
    )


def create_app(test_config=None):
    """Create and configure the Flask app"""
    app = Flask(__name__)

    # Load default configuration
    app.config.from_mapping(
        TESTING=False,
        SLACK_WEBHOOK_URL=os.environ.get("SLACK_WEBHOOK_URL"),
        CHARGIFY_WEBHOOK_SECRET=os.environ.get("CHARGIFY_WEBHOOK_SECRET"),
        SHOPIFY_WEBHOOK_SECRET=os.environ.get("SHOPIFY_WEBHOOK_SECRET"),
    )

    # Override configuration with test config if provided
    if test_config is not None:
        app.config.update(test_config)

    # Initialize providers
    app.chargify_provider = ChargifyProvider(
        webhook_secret=app.config["CHARGIFY_WEBHOOK_SECRET"],
    )

    app.shopify_provider = ShopifyProvider(
        webhook_secret=app.config["SHOPIFY_WEBHOOK_SECRET"],
    )

    # Initialize event processor
    app.event_processor = EventProcessor()

    # Register routes
    @app.route("/webhooks/chargify", methods=["POST"])
    def chargify_webhook():
        """Handle Chargify webhooks"""
        try:
            # Check content type
            if request.content_type != "application/x-www-form-urlencoded":
                return jsonify({"error": "Invalid content type"}), 400

            # Validate webhook signature
            if not app.chargify_provider.validate_webhook(request):
                return jsonify({"error": "Invalid webhook signature"}), 401

            # Parse webhook data
            event_data = app.chargify_provider.parse_webhook(request)
            if not event_data:
                return jsonify({"error": "Invalid webhook data"}), 400

            # Create PaymentEvent object
            payment_event = PaymentEvent(
                id=event_data.get(
                    "id", "evt_" + str(event_data.get("customer_id", "unknown"))
                ),
                event_type=event_data["type"],
                customer_id=event_data["customer_id"],
                amount=event_data["amount"],
                currency=event_data["currency"],
                status=event_data.get("status", "success"),
                timestamp=event_data.get("timestamp"),
                metadata=event_data.get("metadata", {}),
            )

            # Process event and send notification
            notification = app.event_processor.format_notification(
                payment_event, event_data.get("customer_data", {})
            )
            response = requests.post(
                app.config["SLACK_WEBHOOK_URL"],
                json=notification.to_slack_message(),
            )
            response.raise_for_status()

            return jsonify({"status": "success"}), 200

        except InvalidDataError as e:
            return jsonify({"error": str(e)}), 400
        except requests.exceptions.RequestException as e:
            return jsonify({"error": str(e)}), 500
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/webhooks/shopify", methods=["POST"])
    def shopify_webhook():
        """Handle Shopify webhooks"""
        try:
            # Check content type
            if request.content_type != "application/json":
                return jsonify({"error": "Invalid content type"}), 400

            # Get webhook topic from headers
            topic = request.headers.get("X-Shopify-Topic")
            if not topic:
                return jsonify({"error": "Missing webhook topic"}), 400

            # Validate webhook signature
            if not app.shopify_provider.validate_webhook(request):
                return jsonify({"error": "Invalid webhook signature"}), 401

            # Parse webhook data
            event_data = app.shopify_provider.parse_webhook(request, topic=topic)
            if not event_data:
                return jsonify({"error": "Invalid webhook data"}), 400

            # Create PaymentEvent object
            payment_event = PaymentEvent(
                id=event_data.get(
                    "id", "evt_" + str(event_data.get("customer_id", "unknown"))
                ),
                event_type=event_data["type"],
                customer_id=event_data["customer_id"],
                amount=event_data["amount"],
                currency=event_data["currency"],
                status=event_data.get("status", "success"),
                timestamp=event_data.get("timestamp"),
                metadata=event_data.get("metadata", {}),
            )

            # Process event and send notification
            notification = app.event_processor.format_notification(
                payment_event, event_data.get("customer_data", {})
            )
            response = requests.post(
                app.config["SLACK_WEBHOOK_URL"],
                json=notification.to_slack_message(),
            )
            response.raise_for_status()

            return jsonify({"status": "success"}), 200

        except InvalidDataError as e:
            return jsonify({"error": str(e)}), 400
        except requests.exceptions.RequestException as e:
            return jsonify({"error": str(e)}), 500
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/health", methods=["GET"])
    def health_check():
        return jsonify({"status": "healthy"}), 200

    return app
