import json
import os
import random

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

# Slack webhook URL (replace with your actual Slack webhook URL)
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

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
    "💸 Chargify: {name} ({email})’s payment of {amount} went through.",
    "💸 Chargify: Good news! {name} ({email}) paid {amount}.",
    "💸 Chargify: Success! {name} ({email}) paid {amount}."
]

chargify_failure_messages = [
    "⛔️ Chargify: Oops! A payment attempt from {name} ({email}) failed. The transaction for {amount} was declined.",
    "⛔️ Chargify: Uh-oh! {name}'s ({email}) payment for {amount} didn’t go through. Looks like the transaction was blocked.",
    "⛔️ Chargify: Yikes! {name}'s ({email}) card couldn’t process a charge of {amount}.",
    "⛔️ Chargify: {name}'s ({email}) payment of {amount} hit a snag.",
    "⛔️ Chargify: Uh-oh! Payment for {name} ({email}) didn’t pass. The {amount} transaction was blocked."
]

chargify_subscription_messages = [
    "📅 Chargify: Heads up! We’ve got a subscription event for {name} ({email}). Might need to take a look.",
    "📅 Chargify: Update! {name}'s ({email}) subscription has been updated in our records. Changes incoming!",
    "📅 Chargify: News flash! {name}'s ({email}) subscription account got an update. Check out the details.",
    "📅 Chargify: Hey! {name}'s ({email}) subscription status just changed. Let’s see what’s new.",
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
    "⛔️ Chargify: Uh-oh! Renewal for {name}'s ({email}) subscription failed. Let’s check what went wrong.",
    "⛔️ Chargify: Bummer! {name}'s ({email}) renewal attempt didn’t go through. Needs attention.",
    "⛔️ Chargify: Heads up! {name}'s ({email}) renewal didn’t succeed. Time to fix this.",
    "⛔️ Chargify: {name}'s ({email}) renewal failed. Let’s sort this out.",
    "⛔️ Chargify: Uh-oh! Renewal for {name} ({email}) was failed. Review needed."
]

chargify_trial_end_messages = [
    "🔔 Chargify: {name}'s ({email}) trial ends today.",
    "🔔 Chargify: {name}'s ({email}) free trial period is over.",
    "🔔 Chargify: Reminder! {name}'s ({email}) trial is ending.",
    "🔔 Chargify: {name} ({email}) must decide now as the trial period ends.",
    "🔔 Chargify: Trial over! {name}'s ({email}) trial period has ended."
]


@app.route("/webhook/shopify", methods=["POST"])
def shopify_webhook():
    data = request.json

    if data:
        try:
            order_id = data.get("id")
            customer = data.get("customer", {})
            customer_name = f"{customer.get('first_name', 'N/A')} {customer.get('last_name', 'N/A')}"
            customer_email = data.get("contact_email", "N/A")
            total_price = (
                f"{data.get('total_price', 'N/A')} {data.get('currency', 'N/A')}"
            )

            message = random.choice(shopify_order_messages).format(
                name=customer_name, price=total_price, email=customer_email
            )

            payload = {"text": message}

            headers = {"Content-Type": "application/json"}

            response = requests.post(
                SLACK_WEBHOOK_URL, data=json.dumps(payload), headers=headers
            )

            if response.status_code == 200:
                return jsonify({"status": "success"}), 200
            else:
                return (
                    jsonify({"status": "error", "message": "Failed to send to Slack"}),
                    500,
                )
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
    else:
        return jsonify({"status": "error", "message": "Invalid data"}), 400


@app.route("/webhook/chargify", methods=["POST"])
def chargify_webhook():
    if request.content_type != "application/x-www-form-urlencoded":
        return jsonify({"status": "error", "message": "Unsupported Media Type"}), 415

    data = request.form.to_dict()
    print(data)
    if data:
        try:
            event_id = data.get("id")
            event_type = data.get("event")
            customer_first_name = data.get(
                "payload[subscription][customer][first_name]"
            )
            customer_last_name = data.get("payload[subscription][customer][last_name]")
            customer_email = data.get("payload[subscription][customer][email]")
            customer_name = f"{customer_first_name} {customer_last_name}"
            transaction_amount_in_cents = data.get(
                "payload[transaction][amount_in_cents]"
            )
            transaction_currency = data.get("payload[transaction][currency]")

            if transaction_amount_in_cents:
                amount = (
                    f"{int(transaction_amount_in_cents) / 100} {transaction_currency}"
                )
            else:
                amount = "unknown amount"

            if event_type == "payment_failure":
                message = random.choice(chargify_failure_messages).format(
                    name=customer_name, amount=amount, email=customer_email
                )
            elif event_type == "renewal_success":
                message = random.choice(chargify_renewal_messages).format(
                    name=customer_name, email=customer_email
                )
            elif event_type == "trial_end_notice":
                message = random.choice(chargify_trial_end_messages).format(
                    name=customer_name, email=customer_email
                )
            else:
                message = random.choice(chargify_subscription_messages).format(
                    name=customer_name, email=customer_email
                )

            payload = {"text": message}

            headers = {"Content-Type": "application/json"}

            response = requests.post(SLACK_WEBHOOK_URL, json=payload, headers=headers)

            if response.status_code == 200:
                return jsonify({"status": "success"}), 200
            else:
                return (
                    jsonify({"status": "error", "message": "Failed to send to Slack"}),
                    500,
                )
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
    else:
        return jsonify({"status": "error", "message": "Invalid data"}), 400


if __name__ == "__main__":
    app.run(port=5000, debug=True)
