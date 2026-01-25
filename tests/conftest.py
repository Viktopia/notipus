"""Pytest configuration and fixtures for the test suite.

This module provides common fixtures for testing webhook handling,
authentication, and notification processing.
"""

from typing import Any, Generator
from unittest.mock import Mock, patch

import pytest
import sentry_sdk
from django.http import HttpRequest
from django.test import Client
from django.test.client import RequestFactory


@pytest.fixture(autouse=True)
def disable_sentry() -> Generator[None, None, None]:
    """Disable Sentry during tests to prevent sending test errors.

    This fixture runs automatically for all tests.

    Yields:
        None
    """
    # Disable Sentry by reinitializing with empty DSN
    sentry_sdk.init(dsn="")
    yield


# Test organization UUID for multi-tenant webhook endpoints
TEST_ORG_UUID = "12345678-1234-5678-1234-567812345678"


@pytest.fixture
def mock_webhook_validation() -> Generator[Any, None, None]:
    """Mock webhook validation for tests.

    Yields:
        Mock process_event_rich function.
    """

    def mock_process_event_rich(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"blocks": [], "color": "#28a745"}

    with patch(
        "webhooks.services.event_processor.EventProcessor.process_event_rich",
        mock_process_event_rich,
    ):
        yield mock_process_event_rich


@pytest.fixture
def client() -> Client:
    """Create a Django test client.

    Returns:
        Django test Client instance.
    """
    return Client()


@pytest.fixture
def request_factory() -> RequestFactory:
    """Create a Django RequestFactory for mocking requests.

    Returns:
        Django RequestFactory instance.
    """
    return RequestFactory()


@pytest.fixture
def mock_slack_response() -> Mock:
    """Create a mock successful Slack API response.

    Returns:
        Mock response object with ok=True.
    """
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"ok": True}
    return mock_response


@pytest.fixture
def test_organization_uuid() -> str:
    """Return a test organization UUID for webhook endpoints.

    Returns:
        Test organization UUID string.
    """
    return TEST_ORG_UUID


@pytest.fixture
def mock_shopify_request(request_factory: RequestFactory) -> HttpRequest:
    """Create a mock Shopify webhook request.

    Note: This fixture creates a mock request for testing providers directly.
    For integration tests, use the customer webhook endpoints with
    test_organization_uuid fixture.

    Args:
        request_factory: Django RequestFactory instance.

    Returns:
        Mock HttpRequest for Shopify webhook.
    """
    headers = {
        "HTTP_X_SHOPIFY_TOPIC": "orders/paid",
        "HTTP_X_SHOPIFY_SHOP_DOMAIN": "test.myshopify.com",
        "HTTP_X_SHOPIFY_HMAC_SHA256": "test_signature",
        "HTTP_X_SHOPIFY_ORDER_ID": "123456789",
        "HTTP_X_SHOPIFY_API_VERSION": "2025-01",
    }
    data: dict[str, Any] = {
        "id": 123456789,
        "order_number": 1001,
        "customer": {
            "id": 456,
            "email": "test@example.com",
            "first_name": "Test",
            "last_name": "User",
            "company": "Test Company",
            "orders_count": 5,
            "total_spent": "299.95",
        },
        "total_price": "29.99",
        "currency": "USD",
        "financial_status": "paid",
    }
    # Use organization-specific webhook endpoint path
    request = request_factory.post(
        f"/webhook/customer/{TEST_ORG_UUID}/shopify/",
        data=data,
        content_type="application/json",
        **headers,
    )
    return request


@pytest.fixture
def mock_shopify_customer_request(request_factory: RequestFactory) -> HttpRequest:
    """Create a mock Shopify customer webhook request.

    Note: This fixture creates a mock request for testing providers directly.

    Args:
        request_factory: Django RequestFactory instance.

    Returns:
        Mock HttpRequest for Shopify customer webhook.
    """
    headers = {
        "HTTP_X_SHOPIFY_TOPIC": "customers/update",
        "HTTP_X_SHOPIFY_SHOP_DOMAIN": "test.myshopify.com",
        "HTTP_X_SHOPIFY_HMAC_SHA256": "test_signature",
    }
    data: dict[str, Any] = {
        "id": 456,
        "email": "test@example.com",
        "accepts_marketing": True,
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-03-15T10:00:00Z",
        "first_name": "Test",
        "last_name": "User",
        "company": "Updated Company Name",
        "orders_count": 10,
        "total_spent": "599.90",
        "note": "Enterprise customer, upgraded plan",
        "tags": ["enterprise", "priority", "annual"],
        "addresses": [
            {
                "id": 1,
                "company": "Updated Company Name",
                "country": "United States",
                "country_code": "US",
            }
        ],
        "metafields": [
            {
                "key": "team_size",
                "value": "50",
                "namespace": "customer",
            },
            {
                "key": "plan_type",
                "value": "enterprise_annual",
                "namespace": "subscription",
            },
        ],
    }
    # Use organization-specific webhook endpoint path
    request = request_factory.post(
        f"/webhook/customer/{TEST_ORG_UUID}/shopify/",
        data=data,
        content_type="application/json",
        **headers,
    )
    return request


@pytest.fixture
def mock_chargify_request(request_factory: RequestFactory) -> HttpRequest:
    """Create a mock Chargify webhook request.

    Note: This fixture creates a mock request for testing providers directly.

    Args:
        request_factory: Django RequestFactory instance.

    Returns:
        Mock HttpRequest for Chargify webhook.
    """
    headers = {
        "HTTP_X_CHARGIFY_WEBHOOK_ID": "test_webhook_1",
        "HTTP_X_CHARGIFY_WEBHOOK_SIGNATURE_HMAC_SHA_256": "test_signature",
    }
    data: dict[str, str] = {
        "event": "payment_success",
        "id": "12345",
        "payload[subscription][id]": "sub_789",
        "payload[subscription][customer][id]": "cust_123",
        "payload[subscription][customer][email]": "test@example.com",
        "payload[subscription][customer][first_name]": "Test",
        "payload[subscription][customer][last_name]": "User",
        "payload[subscription][customer][organization]": "Test Co",
        "payload[subscription][product][name]": "Enterprise Plan",
        "payload[transaction][amount_in_cents]": "10000",
        "created_at": "2024-03-15T10:00:00Z",
    }
    # Use organization-specific webhook endpoint path
    request = request_factory.post(
        f"/webhook/customer/{TEST_ORG_UUID}/chargify/",
        data=data,
        content_type="application/x-www-form-urlencoded",
        **headers,
    )
    return request
