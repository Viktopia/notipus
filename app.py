import json
import os
import random

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

# Slack webhook URL (replace with your actual Slack webhook URL)
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

shopify_order_messages = [
    "💰 Shopify: A new order has come,\nFrom {name}, it brings joy,\nWorth {price},\nProcessed and fulfilled today.",
    "💰 Shopify: Excitement is here,\n{name} has made a purchase,\nFor {price},\nReady for delivery soon.",
    "💰 Shopify: Order placed, we cheer,\n{name}'s new purchase made,\nTotaling {price},\nAwaiting fulfillment.",
    "💰 Shopify: Today’s a great day,\n{name} buys again,\nPrice is {price},\nOrder ready to ship.",
    "💰 Shopify: From {name},\nAn order valued at {price},\nConfirmed and fulfilled with care,\nBrings a smile to our faces.",
]

chargify_failure_messages = [
    "⛔️ Chargify: A payment attempt failed,\n{name}'s card declined,\nTransaction for {amount},\nChargify sends this news.",
    "⛔️ Chargify: Failed payment received,\n{name}'s transaction blocked,\nAmount was {amount},\nPlease check the details.",
    "⛔️ Chargify: Notice of failure,\n{name}'s card couldn’t clear,\n{amount} charged,\nAction needed soon.",
    "⛔️ Chargify: {name}'s payment,\nFailed to process, we must fix,\n{amount} issue,\nLet’s resolve this now.",
    "⛔️ Chargify: Payment did not pass,\nFor {name} this time,\n{amount} blocked,\nReview is advised.",
]

chargify_subscription_messages = [
    "A subscription event,\nFrom {name} just arrived,\nChargify notifies,\nAction may be required.",
    "{name}'s subscription,\nUpdated in our records,\nChargify event,\nWe are informed of changes.",
    "Subscription news,\n{name}'s account updated,\nChargify informs,\nDetails must be reviewed.",
    "{name}'s subscription,\nReceived a new status now,\nChargify sends word,\nKeep track of changes.",
    "Update on {name},\nSubscription status altered,\nChargify alert,\nReview and proceed.",
]

chargify_renewal_messages = [
    "🔁 Renewal success,\n{name}'s subscription renewed,\nChargify confirms,\nAll is well and good.",
    "🔁 {name} renewed,\nSubscription continues on,\nChargify informs,\nRenewal success.",
    "🔁 Subscription renewed,\n{name}'s plan continues on,\nChargify lets us know,\nSuccess in renewal.",
    "🔁 {name} stays with us,\nSubscription now renewed,\nChargify says yes,\nTo continued service.",
    "🔁 Good news today,\n{name}'s renewal complete,\nChargify updates,\nSubscription lives on.",
]

chargify_trial_end_messages = [
    "🔔 Trial ends today,\n{name}'s trial period,\nChargify notifies,\nDecision time is near.",
    "🔔 End of trial,\n{name}'s free period done,\nChargify informs,\nWhat will happen next?",
    "🔔 {name}'s trial ends,\nChargify sends notice,\nConsider next steps,\nSubscription awaits.",
    "🔔 Trial period over,\n{name} must now decide,\nChargify updates,\nChoose to stay or not.",
    "🔔 End of trial,\n{name}'s trial period,\nChargify sends word,\nTime to make a choice.",
]


@app.route("/webhook/shopify", methods=["POST"])
def shopify_webhook():
    data = request.json

    if data:
        try:
            order_id = data.get("id")
            customer = data.get("customer", {})
            customer_name = f"{customer.get('first_name', 'N/A')} {customer.get('last_name', 'N/A')}"
            total_price = (
                f"{data.get('total_price', 'N/A')} {data.get('currency', 'N/A')}"
            )

            message = random.choice(shopify_order_messages).format(
                name=customer_name, price=total_price
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
                    name=customer_name, amount=amount
                )
            elif event_type == "renewal_success":
                message = random.choice(chargify_renewal_messages).format(
                    name=customer_name
                )
            elif event_type == "trial_end_notice":
                message = random.choice(chargify_trial_end_messages).format(
                    name=customer_name
                )
            else:
                message = random.choice(chargify_subscription_messages).format(
                    name=customer_name
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
