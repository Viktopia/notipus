import json
from unittest.mock import patch

import pytest
from app import app

@pytest.fixture
def client():
    """Create a test client for the Flask app"""
    with app.test_client() as client:
        yield client

def test_shopify_webhook_success(client, sample_shopify_order, mock_slack_response):
    """Test successful Shopify webhook processing"""
    with patch('requests.post', return_value=mock_slack_response):
        response = client.post(
            '/webhook/shopify',
            data=json.dumps(sample_shopify_order),
            content_type='application/json'
        )

        assert response.status_code == 200
        assert response.json['status'] == 'success'

def test_shopify_webhook_invalid_data(client):
    """Test Shopify webhook with invalid data"""
    response = client.post(
        '/webhook/shopify',
        data=json.dumps({}),
        content_type='application/json'
    )

    assert response.status_code == 400
    assert response.json['status'] == 'error'
    assert 'Invalid data' in response.json['message']

def test_chargify_webhook_success(client, sample_chargify_payment, mock_slack_response):
    """Test successful Chargify webhook processing"""
    with patch('requests.post', return_value=mock_slack_response):
        response = client.post(
            '/webhook/chargify',
            data=sample_chargify_payment,
            content_type='application/x-www-form-urlencoded'
        )

        assert response.status_code == 200
        assert response.json['status'] == 'success'

def test_chargify_webhook_wrong_content_type(client, sample_chargify_payment):
    """Test Chargify webhook with wrong content type"""
    response = client.post(
        '/webhook/chargify',
        data=json.dumps(sample_chargify_payment),
        content_type='application/json'
    )

    assert response.status_code == 415
    assert response.json['status'] == 'error'
    assert 'Unsupported Media Type' in response.json['message']

def test_chargify_payment_failure_handling(client, sample_chargify_failure, mock_slack_response):
    """Test handling of Chargify payment failure events"""
    with patch('requests.post', return_value=mock_slack_response):
        response = client.post(
            '/webhook/chargify',
            data=sample_chargify_failure,
            content_type='application/x-www-form-urlencoded'
        )

        assert response.status_code == 200
        assert response.json['status'] == 'success'

def test_slack_notification_failure(client, sample_shopify_order, mock_failed_slack_response):
    """Test handling of Slack API failures"""
    with patch('requests.post', return_value=mock_failed_slack_response):
        response = client.post(
            '/webhook/shopify',
            data=json.dumps(sample_shopify_order),
            content_type='application/json'
        )

        assert response.status_code == 500
        assert response.json['status'] == 'error'
        assert 'Failed to send to Slack' in response.json['message']

def test_chargify_trial_end_handling(client, sample_chargify_trial_end, mock_slack_response):
    """Test handling of Chargify trial end events"""
    with patch('requests.post', return_value=mock_slack_response):
        response = client.post(
            '/webhook/chargify',
            data=sample_chargify_trial_end,
            content_type='application/x-www-form-urlencoded'
        )

        assert response.status_code == 200
        assert response.json['status'] == 'success'
