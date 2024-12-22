from flask import Blueprint, jsonify, request, current_app, redirect, url_for
import requests
from app.providers.base import InvalidDataError

bp = Blueprint("webhooks", __name__)


@bp.route("/webhook/shopify", methods=["POST"])
def shopify_webhook_redirect():
    """Redirect singular webhook path to plural form"""
    return redirect(url_for("webhooks.shopify_webhook"))


@bp.route("/webhooks/shopify", methods=["POST"])
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


@bp.route("/webhook/chargify", methods=["POST"])
def chargify_webhook_redirect():
    """Redirect singular webhook path to plural form"""
    return redirect(url_for("webhooks.chargify_webhook"))


@bp.route("/webhooks/chargify", methods=["POST"])
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
