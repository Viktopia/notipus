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



def extract_nested_value(data, keys):
    """
    Utility function to extract nested values from the form data
    """
    for key in keys:
        if isinstance(data, dict):
            data = data.get(key)
        else:
            return None
    return data

def create_enriched_slack_message(event_type, data):
    """
    Creates rich Slack messages with proper formatting and context based on event type.
    """
    if event_type == "payment_success":
        # Calculate customer metrics
        customer_since = "2023-01-15"  # This would come from your customer database
        total_purchases = "5"  # This would be calculated from historical data
        customer_tier = "Premium"  # This would be determined by business logic

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🎉 Successful Payment",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Customer:*\n{data['customer_first_name']} {data['customer_last_name']}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Amount:*\n${data['amount']} {data['currency']}"
                    }
                ]
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Customer Tier:*\n{customer_tier}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Customer Since:*\n{customer_since}"
                    }
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"📈 *Customer Health*\n• Total Purchases: {total_purchases}\n• Payment Status: On time\n• Subscription: Active"
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "View Customer Profile",
                            "emoji": True
                        },
                        "url": f"https://your-admin-panel/customers/{data['subscription_id']}"
                    }
                ]
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Transaction ID: {data['event_id']} | {data['created_at']}"
                    }
                ]
            }
        ]

    elif event_type == "subscription_upgrade":
        previous_plan = "Basic"  # This would come from historical data
        new_plan = "Professional"
        upgrade_value = "$50/month"

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "⭐️ Plan Upgrade",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{data['customer_first_name']} {data['customer_last_name']}* has upgraded their subscription!"
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*From:*\n{previous_plan}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*To:*\n{new_plan}"
                    }
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"📊 *Upgrade Impact*\n• Additional Revenue: {upgrade_value}\n• New Features: Advanced Analytics, API Access\n• Support Level: Priority"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "🎯 *Recommended Actions*\n• Schedule a welcome call\n• Share advanced feature documentation\n• Set up quarterly review"
                }
            }
        ]

    elif event_type == "payment_failed":
        retry_count = "2"  # This would come from your payment system
        last_successful_payment = "2024-01-15"
        customer_value = "$5,000"

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "⚠️ Payment Failed",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*High-Priority Customer Alert*\nPayment failed for {data['customer_first_name']} {data['customer_last_name']}"
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Failed Amount:*\n${data['amount']} {data['currency']}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Retry Count:*\n{retry_count}/3"
                    }
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Customer Context*\n• Lifetime Value: {customer_value}\n• Last Successful Payment: {last_successful_payment}\n• Account Status: At Risk"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "🚨 *Immediate Actions Required*\n1. Contact customer within 24 hours\n2. Check for card expiration\n3. Review account history"
                }
            }
        ]

    return {
        "blocks": blocks
    }

@app.route('/webhook/chargify', methods=['POST'])
def chargify_webhook():
    if request.content_type != 'application/x-www-form-urlencoded':
        return jsonify({'status': 'error', 'message': 'Unsupported Media Type'}), 415

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

            # Determine event type for message formatting
            event_type = 'payment_success'  # This would be determined by business logic
            if 'failed' in data.get('event', '').lower():
                event_type = 'payment_failed'
            elif 'upgrade' in data.get('event', '').lower():
                event_type = 'subscription_upgrade'

            # Create enriched Slack message
            payload = create_enriched_slack_message(event_type, processed_data)

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
