import json
import os
import random

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

# Slack webhook URL (replace with your actual Slack webhook URL)
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

shopify_order_messages = [
    "💰 Shopify: A new order has come,\nFrom {name} ({email}), it brings joy,\nWorth {price},\nProcessed and fulfilled today.",
    "💰 Shopify: Excitement is here,\n{name} ({email}) has made a purchase,\nFor {price},\nReady for delivery soon.",
    "💰 Shopify: Order placed, we cheer,\n{name}'s ({email}) new purchase made,\nTotaling {price},\nAwaiting fulfillment.",
    "💰 Shopify: Today’s a great day,\n{name} ({email}) orders,\nPrice is {price},\nOrder ready to ship.",
    "💰 Shopify: From {name} ({email}),\nAn order valued at {price},\nConfirmed and fulfilled with care,\nBrings a smile to our faces.",
]

chargify_failure_messages = [
    "⛔️ Chargify: A payment attempt failed,\n{name}'s ({email}) card declined,\nTransaction for {amount},\nChargify sends this news.",
    "⛔️ Chargify: Failed payment received,\n{name}'s ({email}) transaction blocked,\nAmount was {amount},\nPlease check the details.",
    "⛔️ Chargify: Notice of failure,\n{name}'s ({email}) card couldn’t clear,\n{amount} charged,\nAction needed soon.",
    "⛔️ Chargify: {name}'s payment,\nFailed to process, we must fix,\n{amount} issue,\nLet’s resolve this now.",
    "⛔️ Chargify: Payment did not pass,\nFor {name} ({email}) this time,\n{amount} blocked,\nReview is advised.",
]

chargify_subscription_messages = [
    "A subscription event,\nFrom {name}( {email}) just arrived,\nChargify notifies,\nAction may be required.",
    "{name}'s ({email}) subscription,\nUpdated in our records,\nChargify event,\nWe are informed of changes.",
    "Subscription news,\n{name}'s ({email}) account updated,\nChargify informs,\nDetails must be reviewed.",
    "{name}'s ({email}) subscription,\nReceived a new status now,\nChargify sends word,\nKeep track of changes.",
    "Update on {name} ({email}),\nSubscription status altered,\nChargify alert,\nReview and proceed.",
]

chargify_renewal_messages = [
    "🔁 Renewal success,\n{name}'s ({email}) subscription renewed,\nChargify confirms,\nAll is well and good.",
    "🔁 {name} ({email}) renewed,\nSubscription continues on,\nChargify informs,\nRenewal success.",
    "🔁 Subscription renewed,\n{name}'s ({email}) plan continues on,\nChargify lets us know,\nSuccess in renewal.",
    "🔁 {name} ({email}) stays with us,\nSubscription now renewed,\nChargify says yes,\nTo continued service.",
    "🔁 Good news today,\n{name}'s ({email}) renewal complete,\nChargify updates,\nSubscription lives on.",
]

chargify_trial_end_messages = [
    "🔔 Trial ends today,\n{name}'s ({email}) trial period,\nChargify notifies,\nDecision time is near.",
    "🔔 End of trial,\n{name}'s ({email}) free period done,\nChargify informs,\nWhat will happen next?",
    "🔔 {name}'s ({email}) trial ends,\nChargify sends notice,\nConsider next steps,\nSubscription awaits.",
    "🔔 Trial period over,\n{name} ({email}) must now decide,\nChargify updates,\nChoose to stay or not.",
    "🔔 End of trial,\n{name}'s ({email}) trial period,\nChargify sends word,\nTime to make a choice.",
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
