import os
from typing import Dict, Any
from flask import Flask, request, jsonify
import requests
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration

from .providers import (
    ChargifyProvider,
    ShopifyProvider,
    WebhookValidationError,
    InvalidDataError,
)
from .enrichment import NotificationEnricher
from .messages import MessageGenerator

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

app = Flask(__name__)

# Initialize providers
chargify_provider = ChargifyProvider(
    api_key=os.environ["CHARGIFY_API_KEY"],
    domain=os.environ["CHARGIFY_DOMAIN"],
    webhook_secret=os.environ["CHARGIFY_WEBHOOK_SECRET"],
)

shopify_provider = ShopifyProvider(
    shop_url=os.environ["SHOPIFY_SHOP_URL"],
    access_token=os.environ["SHOPIFY_ACCESS_TOKEN"],
    webhook_secret=os.environ["SHOPIFY_WEBHOOK_SECRET"],
)

# Initialize message generator
message_generator = MessageGenerator()


def send_slack_message(message: Dict[str, Any]) -> bool:
    """Send a message to Slack"""
    slack_webhook_url = os.environ["SLACK_WEBHOOK_URL"]

    try:
        response = requests.post(slack_webhook_url, json=message)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        # Capture the error in Sentry with additional context
        sentry_sdk.capture_exception(e)
        print(f"Error sending Slack message: {str(e)}")
        return False


@app.route("/webhooks/chargify", methods=["POST"])
def chargify_webhook():
    """Handle Chargify webhooks"""
    try:
        # Set Sentry context for this request
        with sentry_sdk.configure_scope() as scope:
            scope.set_tag("webhook_type", "chargify")
            scope.set_context(
                "webhook_data",
                {"headers": dict(request.headers), "data": request.get_json()},
            )

        # Validate webhook signature
        signature = request.headers.get("X-Chargify-Webhook-Signature")
        if not signature or not chargify_provider.validate_webhook(
            request.get_json(), signature
        ):
            return jsonify({"error": "Invalid webhook signature"}), 401

        # Parse webhook data
        event = chargify_provider.parse_webhook(request.get_json())

        # Add event context to Sentry
        sentry_sdk.set_context(
            "event",
            {
                "id": event.id,
                "type": event.type,
                "customer_id": event.customer_id,
                "amount": event.amount,
                "currency": event.currency,
            },
        )

        # Enrich notification
        enricher = NotificationEnricher(chargify_provider)
        notification = enricher.enrich_notification(event)

        # Generate Slack message
        message = message_generator.generate_message(notification)

        # Send to Slack
        if not send_slack_message(message):
            return jsonify({"error": "Failed to send Slack message"}), 500

        return jsonify({"status": "success"}), 200

    except WebhookValidationError as e:
        sentry_sdk.capture_exception(e)
        return jsonify({"error": str(e)}), 401
    except InvalidDataError as e:
        sentry_sdk.capture_exception(e)
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        sentry_sdk.capture_exception(e)
        print(f"Error processing Chargify webhook: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/webhooks/shopify", methods=["POST"])
def shopify_webhook():
    """Handle Shopify webhooks"""
    try:
        # Set Sentry context for this request
        with sentry_sdk.configure_scope() as scope:
            scope.set_tag("webhook_type", "shopify")
            scope.set_context(
                "webhook_data",
                {"headers": dict(request.headers), "data": request.get_json()},
            )

        # Validate webhook signature
        signature = request.headers.get("X-Shopify-Hmac-Sha256")
        if not signature or not shopify_provider.validate_webhook(
            request.get_json(), signature
        ):
            return jsonify({"error": "Invalid webhook signature"}), 401

        # Parse webhook data
        event = shopify_provider.parse_webhook(request.get_json())

        # Add event context to Sentry
        sentry_sdk.set_context(
            "event",
            {
                "id": event.id,
                "type": event.type,
                "customer_id": event.customer_id,
                "amount": event.amount,
                "currency": event.currency,
            },
        )

        # Enrich notification
        enricher = NotificationEnricher(shopify_provider)
        notification = enricher.enrich_notification(event)

        # Generate Slack message
        message = message_generator.generate_message(notification)

        # Send to Slack
        if not send_slack_message(message):
            return jsonify({"error": "Failed to send Slack message"}), 500

        return jsonify({"status": "success"}), 200

    except WebhookValidationError as e:
        sentry_sdk.capture_exception(e)
        return jsonify({"error": str(e)}), 401
    except InvalidDataError as e:
        sentry_sdk.capture_exception(e)
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        sentry_sdk.capture_exception(e)
        print(f"Error processing Shopify webhook: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
