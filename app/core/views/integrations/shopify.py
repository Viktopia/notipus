"""Shopify OAuth integration views.

Handles Shopify OAuth 2.0 flow for receiving order and customer webhooks.
Similar to Stripe Connect, this automatically creates webhook subscriptions
after successful OAuth authorization.
"""

import hashlib
import hmac
import logging
import secrets
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect, render

from ...models import Integration
from .base import (
    DEFAULT_API_TIMEOUT,
    require_organization,
    require_post_method,
)

logger = logging.getLogger(__name__)

# Integration metadata
INTEGRATION_TYPE = "shopify"
DISPLAY_NAME = "Shopify"

# Shopify webhook topics to subscribe to
SHOPIFY_WEBHOOK_TOPICS = [
    "orders/create",
    "orders/paid",
    "orders/cancelled",
    "orders/fulfilled",
    "customers/update",
]


@login_required
def integrate_shopify(request: HttpRequest) -> HttpResponse | HttpResponseRedirect:
    """Shopify integration setup page.

    Shows a form for users to enter their shop URL and initiate OAuth flow.
    If already connected, shows the connected status.

    Args:
        request: The HTTP request object.

    Returns:
        Shopify integration page or redirect to organization creation.
    """
    organization, redirect_response = require_organization(request)
    if redirect_response:
        return redirect_response

    # Check for existing integration
    existing_integration = Integration.objects.filter(
        organization=organization,
        integration_type=INTEGRATION_TYPE,
        is_active=True,
    ).first()

    context = {
        "organization": organization,
        "integration": existing_integration,
        "shopify_configured": bool(settings.SHOPIFY_CLIENT_ID),
    }
    return render(request, "core/integrate_shopify.html.j2", context)


@login_required
def shopify_connect(request: HttpRequest) -> HttpResponseRedirect:
    """Start Shopify OAuth flow.

    Accepts shop URL via POST, validates it, stores state in session,
    and redirects to Shopify OAuth authorization page.

    Args:
        request: The HTTP request object.

    Returns:
        Redirect to Shopify OAuth or integrations page on error.
    """
    error_redirect = require_post_method(request)
    if error_redirect:
        return error_redirect

    organization, redirect_response = require_organization(request)
    if redirect_response:
        return redirect_response

    if not settings.SHOPIFY_CLIENT_ID:
        logger.error("SHOPIFY_CLIENT_ID not configured")
        messages.error(
            request, "Shopify integration is not configured. Please contact support."
        )
        return redirect("core:integrations")

    # Get and validate shop URL from POST data
    shop_url = request.POST.get("shop_url", "").strip().lower()
    if not shop_url:
        messages.error(request, "Please enter your Shopify store URL")
        return redirect("core:integrate_shopify")

    # Normalize shop URL to myshopify.com domain
    shop_domain = _normalize_shop_domain(shop_url)
    if not shop_domain:
        messages.error(
            request,
            "Invalid Shopify store URL. "
            "Please enter a valid URL like 'mystore' or 'mystore.myshopify.com'",
        )
        return redirect("core:integrate_shopify")

    # Validate the shop domain format (security check)
    if not _is_valid_shop_domain(shop_domain):
        messages.error(request, "Invalid Shopify store URL format")
        return redirect("core:integrate_shopify")

    # Generate state parameter for CSRF protection
    state = secrets.token_urlsafe(32)

    # Store state and shop in session for callback verification
    request.session["shopify_oauth_state"] = state
    request.session["shopify_shop_domain"] = shop_domain

    # Build OAuth authorization URL
    # https://shopify.dev/docs/apps/auth/oauth/getting-started
    auth_params = {
        "client_id": settings.SHOPIFY_CLIENT_ID,
        "scope": settings.SHOPIFY_SCOPES,
        "redirect_uri": settings.SHOPIFY_REDIRECT_URI,
        "state": state,
    }

    auth_url = f"https://{shop_domain}/admin/oauth/authorize?{urlencode(auth_params)}"

    logger.info(f"Redirecting to Shopify OAuth for shop: {shop_domain}")
    return redirect(auth_url)


def shopify_connect_callback(
    request: HttpRequest,
) -> HttpResponse | HttpResponseRedirect:
    """Handle Shopify OAuth callback.

    Validates state parameter, exchanges authorization code for access token,
    creates webhook subscriptions, and stores the integration.

    Args:
        request: The HTTP request object.

    Returns:
        Redirect to integrations page on success, error response on failure.
    """
    # Get callback parameters
    code = request.GET.get("code")
    state = request.GET.get("state")
    shop = request.GET.get("shop")
    error = request.GET.get("error")
    error_description = request.GET.get("error_description")

    # Handle OAuth errors
    if error:
        logger.error(f"Shopify OAuth error: {error} - {error_description}")
        error_msg = error_description or error
        messages.error(request, f"Shopify connection failed: {error_msg}")
        return redirect("core:integrations")

    # Validate required parameters
    if not code or not state or not shop:
        messages.error(request, "Invalid OAuth callback: missing parameters")
        return redirect("core:integrations")

    # Validate state parameter (CSRF protection)
    stored_state = request.session.get("shopify_oauth_state")
    if not stored_state or not secrets.compare_digest(state, stored_state):
        logger.error("Shopify OAuth state mismatch - possible CSRF attack")
        messages.error(request, "Invalid OAuth state. Please try again.")
        return redirect("core:integrations")

    # Validate shop matches what we stored
    stored_shop = request.session.get("shopify_shop_domain")
    if not stored_shop or shop != stored_shop:
        logger.error(f"Shopify shop mismatch: expected {stored_shop}, got {shop}")
        messages.error(request, "Shop domain mismatch. Please try again.")
        return redirect("core:integrations")

    # Clean up session
    request.session.pop("shopify_oauth_state", None)
    request.session.pop("shopify_shop_domain", None)

    # Get user's organization
    organization, redirect_response = require_organization(request)
    if redirect_response:
        return redirect_response

    # Validate HMAC signature if present (Shopify may include this)
    hmac_param = request.GET.get("hmac")
    if hmac_param and not _verify_oauth_hmac(request, hmac_param):
        logger.error("Shopify OAuth HMAC verification failed")
        messages.error(request, "OAuth verification failed. Please try again.")
        return redirect("core:integrations")

    # Exchange authorization code for access token
    token_data = _exchange_code_for_token(request, shop, code)
    if token_data is None:
        return redirect("core:integrations")

    access_token = token_data.get("access_token")
    scope = token_data.get("scope", "")

    if not access_token:
        logger.error(f"Missing access_token in Shopify response: {token_data}")
        messages.error(request, "Shopify connection failed: Invalid response")
        return redirect("core:integrations")

    # Create webhook subscriptions
    webhook_result = _create_webhook_subscriptions(
        request, organization, shop, access_token
    )
    if webhook_result is None:
        # Still save the integration but warn about webhook issues
        logger.warning(
            f"Webhook creation failed for shop {shop}, saving integration anyway"
        )
        webhook_ids = []
    else:
        webhook_ids = webhook_result

    # Store or update Shopify integration
    integration, created = Integration.objects.update_or_create(
        organization=organization,
        integration_type=INTEGRATION_TYPE,
        defaults={
            "oauth_credentials": {
                "access_token": access_token,
                "scope": scope,
            },
            "integration_settings": {
                "shop_domain": shop,
                "webhook_ids": webhook_ids,
            },
            "is_active": True,
        },
    )

    action = "connected" if created else "reconnected"
    logger.info(f"Shopify {action} for organization {organization.name} (shop: {shop})")
    messages.success(
        request,
        f"Shopify {action} successfully! You will now receive order notifications.",
    )
    return redirect("core:integrations")


@login_required
def disconnect_shopify(request: HttpRequest) -> HttpResponseRedirect:
    """Disconnect Shopify integration and delete webhook subscriptions.

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

    # Find the active Shopify integration
    integration = Integration.objects.filter(
        organization=organization,
        integration_type=INTEGRATION_TYPE,
        is_active=True,
    ).first()

    if not integration:
        messages.warning(request, "No active Shopify integration found")
        return redirect("core:integrations")

    # Try to delete webhook subscriptions from Shopify
    _delete_webhook_subscriptions(integration)

    # Deactivate the integration
    integration.is_active = False
    integration.save()

    messages.success(request, "Shopify disconnected successfully!")
    return redirect("core:integrations")


def _normalize_shop_domain(shop_url: str) -> str | None:
    """Normalize shop URL to myshopify.com domain.

    Accepts various formats:
    - mystore
    - mystore.myshopify.com
    - https://mystore.myshopify.com
    - mystore.myshopify.com/admin

    Args:
        shop_url: User-provided shop URL.

    Returns:
        Normalized shop domain (e.g., 'mystore.myshopify.com') or None if invalid.
    """
    # Remove protocol and path, lowercase
    shop = shop_url.lower().replace("https://", "").replace("http://", "")
    shop = shop.split("/")[0]  # Remove any path

    # If it doesn't include myshopify.com, add it
    if not shop.endswith(".myshopify.com"):
        # Remove any other domain suffix if present
        shop = shop.split(".")[0]
        shop = f"{shop}.myshopify.com"

    # Validate the shop name part
    shop_name = shop.replace(".myshopify.com", "")
    if not shop_name or not shop_name.replace("-", "").replace("_", "").isalnum():
        return None

    return shop


def _is_valid_shop_domain(shop_domain: str) -> bool:
    """Validate shop domain format for security.

    Prevents injection attacks by ensuring the domain follows
    Shopify's shop domain format.

    Args:
        shop_domain: The shop domain to validate.

    Returns:
        True if valid, False otherwise.
    """
    import re

    # Shopify shop domains must match this pattern
    # Only alphanumeric, hyphens, and underscores allowed in shop name
    pattern = r"^[a-zA-Z0-9][a-zA-Z0-9\-_]*\.myshopify\.com$"
    return bool(re.match(pattern, shop_domain))


def _verify_oauth_hmac(request: HttpRequest, hmac_param: str) -> bool:
    """Verify HMAC signature from Shopify OAuth callback.

    Args:
        request: The HTTP request object.
        hmac_param: The HMAC parameter from the callback.

    Returns:
        True if valid or no secret configured, False if invalid.
    """
    if not settings.SHOPIFY_CLIENT_SECRET:
        return True  # Can't verify without secret

    # Build the message from query parameters (excluding hmac)
    params = dict(request.GET.items())
    params.pop("hmac", None)

    # Sort parameters and create message string
    sorted_params = sorted(params.items())
    message = "&".join(f"{k}={v}" for k, v in sorted_params)

    # Calculate HMAC
    calculated_hmac = hmac.new(
        settings.SHOPIFY_CLIENT_SECRET.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(calculated_hmac, hmac_param)


def _exchange_code_for_token(request: HttpRequest, shop: str, code: str) -> dict | None:
    """Exchange authorization code for access token.

    Args:
        request: The HTTP request object.
        shop: The shop domain.
        code: The authorization code from Shopify.

    Returns:
        Token data dict or None if exchange failed.
    """
    token_url = f"https://{shop}/admin/oauth/access_token"

    try:
        response = requests.post(
            token_url,
            data={
                "client_id": settings.SHOPIFY_CLIENT_ID,
                "client_secret": settings.SHOPIFY_CLIENT_SECRET,
                "code": code,
            },
            timeout=DEFAULT_API_TIMEOUT,
        )
        response.raise_for_status()
        token_data = response.json()
    except requests.exceptions.Timeout:
        logger.error("Shopify OAuth token exchange timed out")
        messages.error(request, "Shopify connection timed out. Please try again.")
        return None
    except requests.exceptions.HTTPError as e:
        logger.error(f"Shopify OAuth token exchange HTTP error: {e}")
        messages.error(request, "Shopify connection failed. Please try again.")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Shopify OAuth request failed: {e!s}")
        messages.error(request, "Shopify connection failed. Please try again.")
        return None

    if "error" in token_data:
        logger.error(f"Shopify token exchange error: {token_data}")
        error_detail = token_data.get("error_description", token_data.get("error"))
        messages.error(request, f"Shopify connection failed: {error_detail}")
        return None

    return token_data


def _create_webhook_subscriptions(
    request: HttpRequest,
    organization: object,
    shop: str,
    access_token: str,
) -> list[int] | None:
    """Create webhook subscriptions on the Shopify store.

    Args:
        request: The HTTP request object.
        organization: The user's organization.
        shop: The shop domain.
        access_token: The Shopify access token.

    Returns:
        List of created webhook IDs or None if failed.
    """
    webhook_url = f"{settings.BASE_URL}/webhook/customer/{organization.uuid}/shopify/"
    api_version = settings.SHOPIFY_API_VERSION
    webhook_ids = []

    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json",
    }

    for topic in SHOPIFY_WEBHOOK_TOPICS:
        try:
            response = requests.post(
                f"https://{shop}/admin/api/{api_version}/webhooks.json",
                headers=headers,
                json={
                    "webhook": {
                        "topic": topic,
                        "address": webhook_url,
                        "format": "json",
                    }
                },
                timeout=DEFAULT_API_TIMEOUT,
            )

            if response.status_code == 201:
                webhook_data = response.json()
                webhook_id = webhook_data.get("webhook", {}).get("id")
                if webhook_id:
                    webhook_ids.append(webhook_id)
                    logger.info(f"Created Shopify webhook for {topic}: {webhook_id}")
            elif response.status_code == 422:
                # Webhook might already exist - this is okay
                logger.info(f"Shopify webhook for {topic} may already exist")
            else:
                logger.warning(
                    f"Failed to create Shopify webhook for {topic}: "
                    f"{response.status_code} - {response.text}"
                )
        except requests.exceptions.RequestException as e:
            logger.error(f"Error creating Shopify webhook for {topic}: {e!s}")

    if not webhook_ids:
        logger.warning(f"No webhooks created for shop {shop}")
        messages.warning(
            request,
            "Connected to Shopify but could not create webhooks. "
            "You may need to configure webhooks manually in Shopify admin.",
        )
        return None

    logger.info(f"Created {len(webhook_ids)} webhooks for shop {shop}")
    return webhook_ids


def _delete_webhook_subscriptions(integration: Integration) -> None:
    """Delete webhook subscriptions from the Shopify store.

    Args:
        integration: The Shopify integration.
    """
    shop = integration.integration_settings.get("shop_domain")
    access_token = integration.oauth_credentials.get("access_token")
    webhook_ids = integration.integration_settings.get("webhook_ids", [])

    if not shop or not access_token:
        return

    api_version = settings.SHOPIFY_API_VERSION
    headers = {
        "X-Shopify-Access-Token": access_token,
    }

    for webhook_id in webhook_ids:
        try:
            response = requests.delete(
                f"https://{shop}/admin/api/{api_version}/webhooks/{webhook_id}.json",
                headers=headers,
                timeout=DEFAULT_API_TIMEOUT,
            )
            if response.status_code in (200, 204, 404):
                logger.info(f"Deleted Shopify webhook {webhook_id}")
            else:
                logger.warning(
                    f"Failed to delete Shopify webhook {webhook_id}: "
                    f"{response.status_code}"
                )
        except requests.exceptions.RequestException as e:
            # Log but don't fail - the webhook might already be deleted
            logger.warning(f"Error deleting Shopify webhook {webhook_id}: {e!s}")
