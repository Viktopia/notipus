import json
from unittest.mock import patch, MagicMock

import pytest
from app import app


@pytest.fixture
def client():
    """Create a test client for the Flask app"""
    with app.test_client() as client:
        yield client


@pytest.fixture
def mock_shopify_validate():
    with patch("app.shopify.validate_webhook", return_value=True) as mock:
        yield mock


@pytest.fixture
def mock_chargify_validate():
    with patch("app.chargify.validate_webhook", return_value=True) as mock:
        yield mock


@pytest.fixture
def mock_shopify_parse():
    with patch("app.shopify.parse_webhook") as mock:
        mock.return_value = MagicMock(
            event_type="order_created", amount=29.99, currency="USD"
        )
        yield mock


@pytest.fixture
def mock_chargify_parse():
    with patch("app.chargify.parse_webhook") as mock:
        mock.return_value = MagicMock(
            event_type="payment_success", amount=29.99, currency="USD"
        )
        yield mock


def test_shopify_webhook_success(
    client,
    sample_shopify_order,
    mock_slack_response,
    mock_shopify_validate,
    mock_shopify_parse,
):
    """Test successful Shopify webhook processing"""
    with patch("requests.post", return_value=mock_slack_response):
        response = client.post(
            "/webhook/shopify",
            data=json.dumps(sample_shopify_order),
            content_type="application/json",
        )

        assert response.status_code == 200
        assert response.json["status"] == "success"


def test_shopify_webhook_invalid_data(client, mock_shopify_validate):
    """Test Shopify webhook with invalid data"""
    mock_shopify_validate.return_value = False
    response = client.post(
        "/webhook/shopify", data=json.dumps({}), content_type="application/json"
    )

    assert response.status_code == 401
    assert response.json["status"] == "error"
    assert "Invalid webhook signature" in response.json["message"]


def test_chargify_webhook_success(
    client,
    sample_chargify_payment,
    mock_slack_response,
    mock_chargify_validate,
    mock_chargify_parse,
):
    """Test successful Chargify webhook processing"""
    with patch("requests.post", return_value=mock_slack_response):
        response = client.post(
            "/webhook/chargify",
            data=sample_chargify_payment,
            content_type="application/x-www-form-urlencoded",
        )

        assert response.status_code == 200
        assert response.json["status"] == "success"


def test_chargify_webhook_wrong_content_type(client, sample_chargify_payment):
    """Test Chargify webhook with wrong content type"""
    response = client.post(
        "/webhook/chargify",
        data=json.dumps(sample_chargify_payment),
        content_type="application/json",
    )

    assert response.status_code == 415
    assert response.json["status"] == "error"
    assert "Unsupported Media Type" in response.json["message"]


def test_chargify_payment_failure_handling(
    client,
    sample_chargify_failure,
    mock_slack_response,
    mock_chargify_validate,
    mock_chargify_parse,
):
    """Test handling of Chargify payment failure events"""
    mock_chargify_parse.return_value = MagicMock(
        event_type="payment_failure", amount=29.99, currency="USD"
    )

    with patch("requests.post", return_value=mock_slack_response):
        response = client.post(
            "/webhook/chargify",
            data=sample_chargify_failure,
            content_type="application/x-www-form-urlencoded",
        )

        assert response.status_code == 200
        assert response.json["status"] == "success"


def test_slack_notification_failure(
    client,
    sample_shopify_order,
    mock_failed_slack_response,
    mock_shopify_validate,
    mock_shopify_parse,
):
    """Test handling of Slack API failures"""
    mock_failed_slack_response.raise_for_status.side_effect = Exception(
        "Slack API error"
    )

    with patch("requests.post", return_value=mock_failed_slack_response):
        response = client.post(
            "/webhook/shopify",
            data=json.dumps(sample_shopify_order),
            content_type="application/json",
        )

        assert response.status_code == 500
        assert response.json["status"] == "error"
        assert "Failed to send to Slack" in response.json["message"]


def test_chargify_trial_end_handling(
    client,
    sample_chargify_trial_end,
    mock_slack_response,
    mock_chargify_validate,
    mock_chargify_parse,
):
    """Test handling of Chargify trial end events"""
    mock_chargify_parse.return_value = MagicMock(
        event_type="trial_end", amount=0, currency="USD"
    )

    with patch("requests.post", return_value=mock_slack_response):
        response = client.post(
            "/webhook/chargify",
            data=sample_chargify_trial_end,
            content_type="application/x-www-form-urlencoded",
        )

        assert response.status_code == 200
        assert response.json["status"] == "success"
