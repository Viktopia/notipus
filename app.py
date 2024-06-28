from flask import Flask, request, jsonify
import requests
import json
import shopify
import os

app = Flask(__name__)

# Slack webhook URL (replace with your actual Slack webhook URL)
SLACK_WEBHOOK_URL = os.getenv('SLACK_WEBHOOK_URL')

@app.route('/webhook/shopify', methods=['POST'])
def shopify_webhook():
    data = request.json

    if data:
        try:
            order_id = data.get('id')
            customer = data.get('customer', {})
            customer_name = f"{customer.get('first_name', 'N/A')} {customer.get('last_name', 'N/A')}"
            total_price = data.get('total_price', 'N/A')
            currency = data.get('currency', 'N/A')
            email = data.get('contact_email', 'N/A')
            created_at = data.get('created_at', 'N/A')
            financial_status = data.get('financial_status', 'N/A')
            fulfillment_status = data.get('fulfillment_status', 'N/A')

            message = (
                f"New Order Received:\n"
                f"Order ID: {order_id}\n"
                f"Customer: {customer_name}\n"
                f"Email: {email}\n"
                f"Total Price: {total_price} {currency}\n"
                f"Created At: {created_at}\n"
                f"Financial Status: {financial_status}\n"
                f"Fulfillment Status: {fulfillment_status}\n"
            )

            payload = {
                'text': message
            }

            headers = {
                'Content-Type': 'application/json'
            }

            response = requests.post(SLACK_WEBHOOK_URL, data=json.dumps(payload), headers=headers)

            if response.status_code == 200:
                return jsonify({'status': 'success'}), 200
            else:
                return jsonify({'status': 'error', 'message': 'Failed to send to Slack'}), 500
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500
    else:
        return jsonify({'status': 'error', 'message': 'Invalid data'}), 400

@app.route('/webhook/chargify', methods=['POST'])
def chargify_webhook():
    if request.content_type != 'application/x-www-form-urlencoded':
        return jsonify({'status': 'error', 'message': 'Unsupported Media Type'}), 415

    data = request.form.to_dict()
    if data:
        try:
            event_id = data.get('event_id')
            event_type = data.get('type')
            site = json.loads(data.get('site', '{}'))
            subscription = json.loads(data.get('subscription', '{}'))
            transaction = json.loads(data.get('transaction', '{}'))

            # Extracting relevant information
            subscription_id = subscription.get('id')
            customer_name = f"{subscription.get('customer', {}).get('first_name', 'N/A')} {subscription.get('customer', {}).get('last_name', 'N/A')}"
            amount = transaction.get('amount_in_cents', 0) / 100  # Amount in dollars
            currency = transaction.get('currency', 'USD')
            created_at = transaction.get('created_at')

            message = (
                f"New Chargify Event Received:\n"
                f"Event ID: {event_id}\n"
                f"Event Type: {event_type}\n"
                f"Subscription ID: {subscription_id}\n"
                f"Customer: {customer_name}\n"
                f"Amount: {amount} {currency}\n"
                f"Created At: {created_at}\n"
            )

            payload = {
                'text': message
            }

            headers = {
                'Content-Type': 'application/json'
            }

            response = requests.post(SLACK_WEBHOOK_URL, json=payload, headers=headers)

            if response.status_code == 200:
                return jsonify({'status': 'success'}), 200
            else:
                return jsonify({'status': 'error', 'message': 'Failed to send to Slack'}), 500
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500
    else:
        return jsonify({'status': 'error', 'message': 'Invalid data'}), 400


