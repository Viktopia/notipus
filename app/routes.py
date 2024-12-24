import logging
from flask import Blueprint, request, jsonify, current_app
from .providers.base import InvalidDataError

logger = logging.getLogger(__name__)
bp = Blueprint("webhooks", __name__)


@bp.route("/webhook/shopify", methods=["POST"])
def shopify_webhook():
    """Handle Shopify webhooks"""
    try:
        provider = current_app.shopify_provider

        # Validate webhook
        if not provider.validate_webhook(request):
            return jsonify({"error": "Invalid webhook signature"}), 401

        # Parse webhook data
        event_data = provider.parse_webhook(request)
        if not event_data:
            return jsonify(
                {"status": "success", "message": "Test webhook received"}
            ), 200

        # Get customer data
        customer_data = provider.get_customer_data(event_data["customer_id"])

        # Format notification
        notification = current_app.event_processor.format_notification(
            event_data, customer_data
        )

        # Send to Slack
        current_app.slack_client.send_notification(notification)

        return jsonify(
            {"status": "success", "message": "Webhook processed successfully"}
        ), 200

    except InvalidDataError as e:
        logger.warning("Invalid webhook data", exc_info=True)
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error("Server error in Shopify webhook", exc_info=True)
        return jsonify({"error": str(e)}), 500


@bp.route("/webhook/chargify", methods=["POST"])
def chargify_webhook():
    """Handle Chargify webhooks"""
    try:
        provider = current_app.chargify_provider

        # Log webhook data for debugging
        logger.info(
            "Parsing Chargify webhook data",
            extra={
                "content_type": request.content_type,
                "form_data": request.form.to_dict(),
                "headers": dict(request.headers),
            },
        )

        # Validate webhook
        if not provider.validate_webhook(request):
            return jsonify({"error": "Invalid webhook signature"}), 401

        # Parse webhook data
        event_data = provider.parse_webhook(request)
        if not event_data:
            return jsonify(
                {"status": "success", "message": "Test webhook received"}
            ), 200

        # Get customer data
        customer_data = provider.get_customer_data(event_data["customer_id"])

        # Format notification
        notification = current_app.event_processor.format_notification(
            event_data, customer_data
        )

        # Send to Slack
        current_app.slack_client.send_notification(notification)

        return jsonify(
            {"status": "success", "message": "Webhook processed successfully"}
        ), 200

    except InvalidDataError as e:
        logger.warning("Invalid webhook data", exc_info=True)
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error("Server error in Chargify webhook", exc_info=True)
        return jsonify({"error": str(e)}), 500


@bp.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy"}), 200
