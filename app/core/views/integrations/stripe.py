"""Stripe Connect integration views.

Handles Stripe Connect OAuth for receiving payment webhooks from user's Stripe accounts.
"""

import logging

import requests
import stripe
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect

from ...models import Integration
from .base import (
    DEFAULT_API_TIMEOUT,
    require_organization,
    require_post_method,
)

logger = logging.getLogger(__name__)

# Integration metadata
INTEGRATION_TYPE = "stripe_customer"
DISPLAY_NAME = "Stripe"

# Stripe webhook events to subscribe to
STRIPE_WEBHOOK_EVENTS = [
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "customer.subscription.trial_will_end",
    "invoice.payment_succeeded",
    "invoice.payment_failed",
    "invoice.paid",
    "invoice.payment_action_required",
    "checkout.session.completed",
]


@login_required
def integrate_stripe(request: HttpRequest) -> HttpResponseRedirect:
    """Start Stripe Connect integration flow.

    Args:
        request: The HTTP request object.

    Returns:
        Redirect to Stripe Connect OAuth.
    """
    return redirect("core:stripe_connect")


def stripe_connect(request: HttpRequest) -> HttpResponseRedirect:
    """Initialize Stripe Connect OAuth flow for receiving webhooks.

    Args:
        request: The HTTP request object.

    Returns:
        Redirect to Stripe OAuth authorization page.
    """
    if not settings.STRIPE_CONNECT_CLIENT_ID:
        logger.error("STRIPE_CONNECT_CLIENT_ID not configured")
        messages.error(
            request, "Stripe Connect is not configured. Please contact support."
        )
        return redirect("core:integrations")

    # Build OAuth URL with required parameters
    # scope=read_write allows creating webhook endpoints
    auth_url = (
        f"https://connect.stripe.com/oauth/authorize"
        f"?client_id={settings.STRIPE_CONNECT_CLIENT_ID}"
        f"&response_type=code"
        f"&scope=read_write"
        f"&redirect_uri={settings.STRIPE_CONNECT_REDIRECT_URI}"
    )
    return redirect(auth_url)


def stripe_connect_callback(
    request: HttpRequest,
) -> HttpResponse | HttpResponseRedirect:
    """Handle Stripe Connect OAuth callback.

    Exchanges authorization code for access token, creates webhook endpoint
    on the connected account, and stores the integration.

    Args:
        request: The HTTP request object.

    Returns:
        Redirect to integrations page on success, error response on failure.
    """
    code = request.GET.get("code")
    error = request.GET.get("error")
    error_description = request.GET.get("error_description")

    if error:
        logger.error(f"Stripe Connect OAuth error: {error} - {error_description}")
        error_msg = error_description or error
        messages.error(request, f"Stripe connection failed: {error_msg}")
        return redirect("core:integrations")

    if not code:
        messages.error(request, "Authorization failed: No code provided")
        return redirect("core:integrations")

    # Get user's organization
    organization, redirect_response = require_organization(request)
    if redirect_response:
        return redirect_response

    # Exchange authorization code for access token
    token_data = _exchange_code_for_token(request, code)
    if token_data is None:
        return redirect("core:integrations")

    # Extract credentials from response
    access_token = token_data.get("access_token")
    stripe_user_id = token_data.get("stripe_user_id")
    refresh_token = token_data.get("refresh_token")

    if not access_token or not stripe_user_id:
        logger.error(f"Missing credentials in Stripe response: {token_data}")
        messages.error(request, "Stripe connection failed: Invalid response")
        return redirect("core:integrations")

    # Create webhook endpoint on the connected account
    webhook_result = _create_webhook_endpoint(request, organization, access_token)
    if webhook_result is None:
        return redirect("core:integrations")

    webhook_url, webhook_secret, webhook_endpoint_id = webhook_result

    # Store or update Stripe integration
    integration, created = Integration.objects.update_or_create(
        organization=organization,
        integration_type=INTEGRATION_TYPE,
        defaults={
            "oauth_credentials": {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "stripe_user_id": stripe_user_id,
            },
            "webhook_secret": webhook_secret,
            "integration_settings": {
                "webhook_endpoint_id": webhook_endpoint_id,
                "webhook_url": webhook_url,
            },
            "is_active": True,
        },
    )

    action = "connected" if created else "reconnected"
    logger.info(
        f"Stripe {action} for organization {organization.name} "
        f"(account: {stripe_user_id})"
    )
    messages.success(
        request,
        f"Stripe {action} successfully! You will now receive payment notifications.",
    )
    return redirect("core:integrations")


def _exchange_code_for_token(request: HttpRequest, code: str) -> dict | None:
    """Exchange authorization code for access token.

    Args:
        request: The HTTP request object.
        code: The authorization code from Stripe.

    Returns:
        Token data dict or None if exchange failed.
    """
    try:
        response = requests.post(
            "https://connect.stripe.com/oauth/token",
            data={
                "client_secret": settings.STRIPE_SECRET_KEY,
                "code": code,
                "grant_type": "authorization_code",
            },
            timeout=DEFAULT_API_TIMEOUT,
        )
        token_data = response.json()
    except requests.exceptions.Timeout:
        logger.error("Stripe OAuth token exchange timed out")
        messages.error(request, "Stripe connection timed out. Please try again.")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Stripe OAuth request failed: {e!s}")
        messages.error(request, "Stripe connection failed. Please try again.")
        return None

    if "error" in token_data:
        logger.error(f"Stripe token exchange error: {token_data}")
        error_detail = token_data.get("error_description", token_data.get("error"))
        messages.error(request, f"Stripe connection failed: {error_detail}")
        return None

    return token_data


def _create_webhook_endpoint(
    request: HttpRequest, organization: object, access_token: str
) -> tuple[str, str, str] | None:
    """Create webhook endpoint on the connected Stripe account.

    Args:
        request: The HTTP request object.
        organization: The user's organization.
        access_token: The Stripe access token.

    Returns:
        Tuple of (webhook_url, webhook_secret, webhook_endpoint_id) or None if failed.
    """
    webhook_url = f"{settings.BASE_URL}/webhook/customer/{organization.uuid}/stripe/"

    try:
        # Use the connected account's access token
        webhook_endpoint = stripe.WebhookEndpoint.create(
            url=webhook_url,
            enabled_events=STRIPE_WEBHOOK_EVENTS,
            api_key=access_token,
        )
        return webhook_url, webhook_endpoint.secret, webhook_endpoint.id
    except stripe.error.StripeError as e:
        logger.error(f"Failed to create Stripe webhook endpoint: {e!s}")
        messages.error(request, f"Failed to set up Stripe webhooks: {e.user_message}")
        return None


@login_required
def disconnect_stripe(request: HttpRequest) -> HttpResponseRedirect:
    """Disconnect Stripe integration and delete webhook endpoint.

    Args:
        request: The HTTP request object.

    Returns:
        Redirect to integrations page.
    """
    error_redirect = require_post_method(request)
    if error_redirect:
        return error_redirect

    organization, redirect_response = require_organization(request)
    if redirect_response:
        return redirect_response

    # Find the active Stripe integration
    integration = Integration.objects.filter(
        organization=organization,
        integration_type=INTEGRATION_TYPE,
        is_active=True,
    ).first()

    if not integration:
        messages.warning(request, "No active Stripe integration found")
        return redirect("core:integrations")

    # Try to delete the webhook endpoint from Stripe
    _delete_webhook_endpoint(integration)

    # Deactivate the integration
    integration.is_active = False
    integration.save()

    messages.success(request, "Stripe disconnected successfully!")
    return redirect("core:integrations")


def _delete_webhook_endpoint(integration: Integration) -> None:
    """Delete webhook endpoint from the connected Stripe account.

    Args:
        integration: The Stripe integration.
    """
    webhook_endpoint_id = integration.integration_settings.get("webhook_endpoint_id")
    access_token = integration.oauth_credentials.get("access_token")

    if not webhook_endpoint_id or not access_token:
        return

    try:
        stripe.WebhookEndpoint.delete(
            webhook_endpoint_id,
            api_key=access_token,
        )
        logger.info(f"Deleted Stripe webhook endpoint {webhook_endpoint_id}")
    except stripe.error.StripeError as e:
        # Log but don't fail - the endpoint might already be deleted
        logger.warning(f"Failed to delete Stripe webhook endpoint: {e!s}")
