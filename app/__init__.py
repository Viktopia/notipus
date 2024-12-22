import os
from flask import Flask, request, jsonify
from typing import Dict, Any
import requests
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration

from .providers.chargify import ChargifyProvider
from .providers.shopify import ShopifyProvider
from .providers.base import WebhookValidationError, InvalidDataError
from .event_processor import NotificationSection, Notification, CustomerContext

# Initialize Sentry if DSN is provided
if os.environ.get("SENTRY_DSN"):
    sentry_sdk.init(
        dsn=os.environ["SENTRY_DSN"],
        integrations=[FlaskIntegration()],
        traces_sample_rate=1.0,
    )

app = Flask(__name__)

# Initialize providers with webhook secrets only
chargify = ChargifyProvider(
    webhook_secret=os.environ.get("CHARGIFY_WEBHOOK_SECRET", "")
)
shopify = ShopifyProvider(webhook_secret=os.environ.get("SHOPIFY_WEBHOOK_SECRET", ""))


def create_enriched_slack_message(
    event_type: str, event_data: Dict[str, Any], message_text: str
) -> Dict[str, Any]:
    """Create an enriched Slack message with blocks for better formatting and interactivity."""
    sections = []

    # Add the original message text as a section
    sections.append(NotificationSection(message_text))

    # Add failure details for payment failures
    if event_type == "payment_failure":
        amount = event_data.get("payload[transaction][amount_in_cents]", "0")
        retry_count = event_data.get("retry_count", "0")
        sections.append(
            NotificationSection(
                f"*Failed Amount:* ${int(amount)/100:.2f}\n*Retry Count:* {retry_count}"
            )
        )
        sections.append(
            NotificationSection(
                "*Immediate Actions Required:*\n• Contact customer for updated payment method\n• Review account status\n• Check for previous payment issues"
            )
        )

    # Add recommendations for trial end
    elif event_type == "trial_end":
        sections.append(
            NotificationSection(
                "*Recommended Actions:*\n• Send follow-up email with pricing options\n• Schedule a demo call\n• Share relevant case studies"
            )
        )

    # Add emoji to header based on event type
    header = message_text
    if event_type == "payment_failure":
        header = f"🚨 {message_text}"
    elif event_type == "trial_end":
        header = f"📢 {message_text}"

    # Create notification object
    notification = Notification(
        header=header,  # Use the modified header with emoji
        color="#FF0000" if event_type == "payment_failure" else "#FFA500",
        sections=sections,  # Include all sections
        action_buttons=[
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "View Customer Profile"},
                "url": f"https://example.com/customers/{event_data.get('customer_id', '0')}",
            }
        ],
        customer_context=CustomerContext(),
    )

    return notification.to_slack_message()


def send_slack_message(message: Dict[str, Any]) -> None:
    """Send a message to Slack using the webhook URL."""
    slack_webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not slack_webhook_url:
        raise ValueError("SLACK_WEBHOOK_URL environment variable is not set")

    response = requests.post(slack_webhook_url, json=message)
    response.raise_for_status()


@app.route("/webhook/shopify", methods=["POST"])
def shopify_webhook():
    """Handle Shopify webhooks."""
    try:
        # Validate webhook signature
        if not shopify.validate_webhook(request.headers, request.get_data()):
            return jsonify(
                {"status": "error", "message": "Invalid webhook signature"}
            ), 401

        # Parse webhook data
        data = request.get_json()
        topic = request.headers.get("X-Shopify-Topic")
        event = shopify.parse_webhook(data, topic=topic)

        # Create and send Slack message
        message = create_enriched_slack_message(
            event_type=event.event_type,
            event_data=data,
            message_text=f"🛍️ New Shopify order for ${event.amount:.2f} {event.currency}",
        )
        send_slack_message(message)

        return jsonify({"status": "success"}), 200

    except WebhookValidationError as e:
        return jsonify({"status": "error", "message": str(e)}), 401
    except InvalidDataError as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    except requests.exceptions.RequestException as e:
        return jsonify(
            {"status": "error", "message": f"Failed to send to Slack: {str(e)}"}
        ), 500
    except Exception as e:
        if os.environ.get("SENTRY_DSN"):
            sentry_sdk.capture_exception(e)
        return jsonify(
            {"status": "error", "message": f"Failed to send to Slack: {str(e)}"}
        ), 500


@app.route("/webhook/chargify", methods=["POST"])
def chargify_webhook():
    """Handle Chargify webhooks."""
    try:
        # Validate content type
        if request.content_type != "application/x-www-form-urlencoded":
            return jsonify(
                {
                    "status": "error",
                    "message": "Unsupported Media Type. Expected application/x-www-form-urlencoded",
                }
            ), 415

        # Validate webhook signature and ID
        if not chargify.validate_webhook(request.headers, request.get_data()):
            return jsonify(
                {"status": "error", "message": "Invalid webhook signature"}
            ), 401

        # Parse webhook data
        data = request.form.to_dict()
        event = chargify.parse_webhook(data)

        # Create message based on event type
        if event.event_type == "payment_failure":
            message_text = f"❌ Payment failed for ${event.amount:.2f} {event.currency}"
        elif event.event_type == "trial_end":
            message_text = "🔔 Trial period is ending"
        elif event.event_type == "subscription_canceled":
            message_text = "🚫 Subscription has been cancelled"
        elif event.event_type == "dunning_step_reached":
            message_text = "⚠️ Payment recovery in progress"
        else:
            message_text = (
                f"💰 Payment received for ${event.amount:.2f} {event.currency}"
            )

        # Create and send Slack message
        message = create_enriched_slack_message(
            event_type=event.event_type, event_data=data, message_text=message_text
        )
        send_slack_message(message)

        return jsonify({"status": "success"}), 200

    except WebhookValidationError as e:
        return jsonify({"status": "error", "message": str(e)}), 401
    except InvalidDataError as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    except requests.exceptions.RequestException as e:
        return jsonify(
            {"status": "error", "message": f"Failed to send to Slack: {str(e)}"}
        ), 500
    except Exception as e:
        if os.environ.get("SENTRY_DSN"):
            sentry_sdk.capture_exception(e)
        return jsonify(
            {"status": "error", "message": f"Failed to send to Slack: {str(e)}"}
        ), 500
