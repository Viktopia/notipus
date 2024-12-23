from flask import Blueprint, jsonify, request, current_app
import requests
import sentry_sdk
from app.providers.base import InvalidDataError

bp = Blueprint("webhooks", __name__)


@bp.route("/webhook/shopify", methods=["POST"])
def shopify_webhook():
    """Handle Shopify webhooks"""
    try:
        # Check for required headers
        if not request.headers.get("X-Shopify-Topic"):
            return jsonify({"error": "Missing webhook topic"}), 400

        # Validate webhook signature
        if not current_app.shopify_provider.validate_webhook(request):
            return jsonify({"error": "Invalid webhook signature"}), 401

        # Parse webhook data
        event_data = current_app.shopify_provider.parse_webhook(request)
        if not event_data:
            return jsonify({"error": "Invalid webhook data"}), 400

        # Format notification using event processor
        notification = current_app.event_processor.format_notification(
            event_data, event_data.get("customer_data", {})
        )
        if not notification:
            return jsonify({"error": "Failed to format notification"}), 500

        # Send to Slack
        response = requests.post(
            current_app.config["SLACK_WEBHOOK_URL"],
            json=notification.to_slack_message(),
            timeout=5,
        )
        response.raise_for_status()

        return jsonify({"status": "success"}), 200

    except InvalidDataError as e:
        # Don't report validation errors to Sentry
        return jsonify({"error": str(e)}), 400
    except requests.exceptions.RequestException as e:
        # Report Slack API errors to Sentry
        sentry_sdk.capture_exception(e)
        return jsonify({"error": f"Failed to send notification: {str(e)}"}), 500
    except Exception as e:
        # Report unexpected errors to Sentry with context
        sentry_sdk.set_context(
            "webhook_data",
            {
                "headers": dict(request.headers),
                "content_type": request.content_type,
            },
        )
        sentry_sdk.capture_exception(e)
        return jsonify({"error": str(e)}), 500


@bp.route("/webhook/chargify", methods=["POST"])
def chargify_webhook():
    """Handle Chargify webhooks"""
    try:
        # Check content type
        if request.content_type != "application/x-www-form-urlencoded":
            return jsonify({"error": "Invalid content type"}), 400

        # Validate webhook signature
        if not current_app.chargify_provider.validate_webhook(request):
            return jsonify({"error": "Invalid webhook signature"}), 401

        # Parse webhook data
        event_data = current_app.chargify_provider.parse_webhook(request)
        if not event_data:
            return jsonify({"error": "Invalid webhook data"}), 400

        # Format notification using event processor
        notification = current_app.event_processor.format_notification(
            event_data, event_data.get("customer_data", {})
        )
        if not notification:
            return jsonify({"error": "Failed to format notification"}), 500

        # Send to Slack
        response = requests.post(
            current_app.config["SLACK_WEBHOOK_URL"],
            json=notification.to_slack_message(),
            timeout=5,
        )
        response.raise_for_status()

        return jsonify({"status": "success"}), 200

    except InvalidDataError as e:
        # Don't report validation errors to Sentry
        return jsonify({"error": str(e)}), 400
    except requests.exceptions.RequestException as e:
        # Report Slack API errors to Sentry
        sentry_sdk.capture_exception(e)
        return jsonify({"error": f"Failed to send notification: {str(e)}"}), 500
    except Exception as e:
        # Report unexpected errors to Sentry with context
        sentry_sdk.set_context(
            "webhook_data",
            {
                "headers": dict(request.headers),
                "content_type": request.content_type,
            },
        )
        sentry_sdk.capture_exception(e)
        return jsonify({"error": str(e)}), 500


@bp.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy"}), 200
