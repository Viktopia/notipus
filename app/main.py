import json
import os
import random

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

# Slack webhook URL (replace with your actual Slack webhook URL)
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

# Message templates for simple notifications
shopify_order_messages = [
    "💰 Shopify: Woohoo! We just got a new order from {name} ({email}). The total is {price}.",
    "💰 Shopify: Great news! {name} ({email}) has placed an order worth {price}.",
    "💰 Shopify: Guess what? {name} ({email}) just made a purchase for {price}.",
    "💰 Shopify: Today just got better! {name} ({email}) ordered items worth {price}.",
    "💰 Shopify: {name} ({email}) placed an order valued at {price}."
]

chargify_success_messages = [
    "💸 Chargify: Woohoo! {name} ({email}) just paid {amount}.",
    "💸 Chargify: Payment success! {name} ({email}) paid {amount}.",
    "💸 Chargify: {name} ({email})'s payment of {amount} went through.",
    "💸 Chargify: Good news! {name} ({email}) paid {amount}.",
    "💸 Chargify: Success! {name} ({email}) paid {amount}."
]

chargify_failure_messages = [
    "⛔️ Chargify: Oops! A payment attempt from {name} ({email}) failed. The transaction for {amount} was declined.",
    "⛔️ Chargify: Uh-oh! {name}'s ({email}) payment for {amount} didn't go through. Looks like the transaction was blocked.",
    "⛔️ Chargify: Yikes! {name}'s ({email}) card couldn't process a charge of {amount}.",
    "⛔️ Chargify: {name}'s ({email}) payment of {amount} hit a snag.",
    "⛔️ Chargify: Uh-oh! Payment for {name} ({email}) didn't pass. The {amount} transaction was blocked."
]

chargify_subscription_messages = [
    "📅 Chargify: Heads up! We've got a subscription event for {name} ({email}). Might need to take a look.",
    "📅 Chargify: Update! {name}'s ({email}) subscription has been updated in our records. Changes incoming!",
    "📅 Chargify: News flash! {name}'s ({email}) subscription account got an update. Check out the details.",
    "📅 Chargify: Hey! {name}'s ({email}) subscription status just changed. Let's see what's new.",
    "📅 Chargify: Alert! {name} ({email}) has a subscription update. Time to review and proceed."
]

chargify_renewal_messages = [
    "🔁 Chargify: Hooray! {name}'s ({email}) subscription renewal was a success.",
    "🔁 Chargify: {name} ({email}) just renewed their subscription. All set for another period.",
    "🔁 Chargify: Good news! {name}'s ({email}) subscription has been renewed. ",
    "🔁 Chargify: {name} ({email}) is staying with us. Subscription renewal complete!",
    "🔁 Chargify: Great news! {name}'s ({email}) renewal is done. Subscription is active again."
]

chargify_renewal_failure_messages = [
    "⛔️ Chargify: Uh-oh! Renewal for {name}'s ({email}) subscription failed. Let's check what went wrong.",
    "⛔️ Chargify: Bummer! {name}'s ({email}) renewal attempt didn't go through. Needs attention.",
    "⛔️ Chargify: Heads up! {name}'s ({email}) renewal didn't succeed. Time to fix this.",
    "⛔️ Chargify: {name}'s ({email}) renewal failed. Let's sort this out.",
    "⛔️ Chargify: Uh-oh! Renewal for {name} ({email}) was failed. Review needed."
]

chargify_trial_end_messages = [
    "🔔 Chargify: {name}'s ({email}) trial ends today.",
    "🔔 Chargify: {name}'s ({email}) free trial period is over.",
    "🔔 Chargify: Reminder! {name}'s ({email}) trial is ending.",
    "🔔 Chargify: {name} ({email}) must decide now as the trial period ends.",
    "🔔 Chargify: Trial over! {name}'s ({email}) trial period has ended."
]

def create_enriched_slack_message(event_type, data, message_text):
    """
    Creates rich Slack messages with proper formatting and context based on event type.
    Combines the friendly message text with structured data.
    """
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": message_text
            }
        }
    ]

    if event_type == "payment_failure":
        # Add contextual information for payment failures
        blocks.extend([
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Failed Amount:*\n${data['amount']} {data['currency']}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": "*Retry Count:*\n2/3"  # This would come from your system
                    }
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "🚨 *Immediate Actions Required*\n1. Contact customer within 24 hours\n2. Check for card expiration\n3. Review account history"
                }
            }
        ])
    elif event_type == "trial_end":
        # Add contextual information for trial endings
        blocks.extend([
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "👉 *Recommended Actions*\n• Send follow-up email\n• Schedule check-in call\n• Review usage metrics"
                }
            }
        ])

    # Add customer profile link for all messages
    blocks.append({
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": "View Customer Profile",
                    "emoji": True
                },
                "url": f"https://your-admin-panel/customers/{data.get('subscription_id', '')}"
            }
        ]
    })

    return {
        "blocks": blocks
    }

@app.route("/webhook/shopify", methods=["POST"])
def shopify_webhook():
    data = request.json

    if data:
        try:
            order_id = data.get("id")
            customer = data.get("customer", {})
            customer_name = f"{customer.get('first_name', 'N/A')} {customer.get('last_name', 'N/A')}"
            customer_email = data.get("contact_email", "N/A")
            total_price = f"{data.get('total_price', 'N/A')} {data.get('currency', 'N/A')}"

            message = random.choice(shopify_order_messages).format(
                name=customer_name, price=total_price, email=customer_email
            )

            # Create enriched message with both friendly text and structured data
            payload = create_enriched_slack_message(
                "order",
                {
                    "subscription_id": order_id,
                    "amount": data.get('total_price'),
                    "currency": data.get('currency')
                },
                message
            )

            headers = {"Content-Type": "application/json"}
            response = requests.post(SLACK_WEBHOOK_URL, json=payload, headers=headers)

            if response.status_code == 200:
                return jsonify({"status": "success"}), 200
            else:
                return jsonify({"status": "error", "message": "Failed to send to Slack"}), 500
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
    else:
        return jsonify({"status": "error", "message": "Invalid data"}), 400

@app.route("/webhook/chargify", methods=["POST"])
def chargify_webhook():
    if request.content_type != "application/x-www-form-urlencoded":
        return jsonify({"status": "error", "message": "Unsupported Media Type"}), 415

    data = request.form.to_dict()
    if data:
        try:
            # Extract basic event data
            processed_data = {
                'event_id': data.get('id'),
                'event_type': data.get('event'),
                'subscription_id': data.get('payload[subscription][id]'),
                'customer_first_name': data.get('payload[subscription][customer][first_name]'),
                'customer_last_name': data.get('payload[subscription][customer][last_name]'),
                'customer_email': data.get('payload[subscription][customer][email]'),
                'amount': int(data.get('payload[transaction][amount_in_cents]', 0)) / 100,
                'currency': data.get('payload[transaction][currency]'),
                'created_at': data.get('payload[transaction][created_at]')
            }

            customer_name = f"{processed_data['customer_first_name']} {processed_data['customer_last_name']}"
            amount = f"{processed_data['amount']} {processed_data['currency']}"

            # Determine event type and select appropriate message template
            event_type = data.get('event', '').lower()
            if 'payment_failure' in event_type:
                message = random.choice(chargify_failure_messages)
                template_type = 'payment_failure'
            elif 'renewal_success' in event_type:
                message = random.choice(chargify_renewal_messages)
                template_type = 'renewal'
            elif 'trial_end' in event_type:
                message = random.choice(chargify_trial_end_messages)
                template_type = 'trial_end'
            else:
                message = random.choice(chargify_subscription_messages)
                template_type = 'subscription'

            # Format the message with customer data
            message = message.format(
                name=customer_name,
                email=processed_data['customer_email'],
                amount=amount
            )

            # Create enriched message combining friendly text with structured data
            payload = create_enriched_slack_message(template_type, processed_data, message)

            headers = {"Content-Type": "application/json"}
            response = requests.post(SLACK_WEBHOOK_URL, json=payload, headers=headers)

            if response.status_code == 200:
                return jsonify({"status": "success"}), 200
            else:
                return jsonify({"status": "error", "message": "Failed to send to Slack"}), 500
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
    else:
        return jsonify({"status": "error", "message": "Invalid data"}), 400

if __name__ == "__main__":
    app.run(port=5000, debug=True)
