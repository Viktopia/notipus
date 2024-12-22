from flask import Blueprint, jsonify, request, current_app
import requests
from app.providers.base import InvalidDataError

bp = Blueprint("webhooks", __name__)


@bp.route("/webhooks/shopify", methods=["POST"])
def shopify_webhook():
    """Handle Shopify webhooks"""
    try:
        # Parse webhook data
        event_data = current_app.shopify_provider.parse_webhook(request)
        if not event_data:
            return jsonify({"error": "Invalid webhook data"}), 400

        # Format notification
        notification = current_app.event_processor.format_notification(event_data)
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
        return jsonify({"error": str(e)}), 400
    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Failed to send notification: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/webhooks/chargify", methods=["POST"])
def chargify_webhook():
    """Handle Chargify webhooks"""
    try:
        # Parse webhook data
        event_data = current_app.chargify_provider.parse_webhook(request)
        if not event_data:
            return jsonify({"error": "Invalid webhook data"}), 400

        # Format notification
        notification = current_app.event_processor.format_notification(event_data)
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
        return jsonify({"error": str(e)}), 400
    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Failed to send notification: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy"}), 200
