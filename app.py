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
