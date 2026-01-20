"""Integration connection views.

This module handles connecting external services like Slack, Shopify,
Stripe, and Chargify.
"""

import json
import logging
from typing import Any

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import redirect, render

from ..models import Integration, UserProfile
from ..services.shopify import ShopifyAPI
from ..services.stripe import StripeAPI

logger = logging.getLogger(__name__)

# Default timeout for external API requests (seconds)
SLACK_API_TIMEOUT = 30


@login_required
def integrations(request: HttpRequest) -> HttpResponse | HttpResponseRedirect:
    """Integrations overview page.

    Args:
        request: The HTTP request object.

    Returns:
        Integrations page or redirect to organization creation.
    """
    from core.services.dashboard import IntegrationService

    try:
        user_profile = UserProfile.objects.get(user=request.user)
        organization = user_profile.organization

        integration_service = IntegrationService()
        context = integration_service.get_integration_overview(organization)

        return render(request, "core/integrations.html.j2", context)

    except UserProfile.DoesNotExist:
        return redirect("core:create_organization")


@login_required
def integrate_slack(request: HttpRequest) -> HttpResponseRedirect:
    """Start Slack integration flow.

    Args:
        request: The HTTP request object.

    Returns:
        Redirect to Slack connect.
    """
    return redirect("core:slack_connect")


def slack_connect(request: HttpRequest) -> HttpResponseRedirect:
    """Initialize Slack connection for workspace notifications.

    Args:
        request: The HTTP request object.

    Returns:
        Redirect to Slack OAuth authorization.
    """
    scopes = "incoming-webhook,chat:write,channels:read"
    auth_url = (
        f"https://slack.com/oauth/v2/authorize"
        f"?client_id={settings.SLACK_CLIENT_ID}"
        f"&scope={scopes}"
        f"&redirect_uri={settings.SLACK_CONNECT_REDIRECT_URI}"
        f"&response_type=code"
    )
    return redirect(auth_url)


def slack_connect_callback(request: HttpRequest) -> HttpResponse | HttpResponseRedirect:
    """Handle Slack OAuth callback for workspace notifications.

    Args:
        request: The HTTP request object.

    Returns:
        Redirect to integrations page on success, error response on failure.
    """
    code = request.GET.get("code")
    if not code:
        return HttpResponse("Authorization failed: No code provided", status=400)

    # Exchange code for token
    try:
        response = requests.post(
            "https://slack.com/api/oauth.v2.access",
            data={
                "client_id": settings.SLACK_CLIENT_ID,
                "client_secret": settings.SLACK_CLIENT_SECRET,
                "code": code,
                "redirect_uri": settings.SLACK_CONNECT_REDIRECT_URI,
            },
            timeout=SLACK_API_TIMEOUT,
        )
        data = response.json()
    except requests.exceptions.Timeout:
        logger.error("Slack OAuth token exchange timed out")
        return HttpResponse("Slack connection timed out. Please try again.", status=504)
    except requests.exceptions.RequestException as e:
        logger.error(f"Slack OAuth request failed: {e!s}")
        return HttpResponse("Slack connection failed. Please try again.", status=502)

    if not data.get("ok"):
        return HttpResponse(f"Slack connection failed: {data.get('error')}", status=400)

    # Get user's organization
    if not request.user.is_authenticated:
        return redirect("account_login")

    try:
        user_profile = UserProfile.objects.get(user=request.user)
        organization = user_profile.organization
    except UserProfile.DoesNotExist:
        return HttpResponse("User profile not found", status=400)

    # Store or update Slack integration
    integration, created = Integration.objects.get_or_create(
        organization=organization,
        integration_type="slack_notifications",
        defaults={
            "oauth_credentials": {
                "access_token": data["access_token"],
                "team": data["team"],
                "incoming_webhook": data.get("incoming_webhook", {}),
            },
            "integration_settings": {
                "channel": data.get("incoming_webhook", {}).get("channel", "#general"),
                "team_id": data["team"]["id"],
            },
            "is_active": True,
        },
    )

    if not created:
        # Update existing integration
        integration.oauth_credentials = {
            "access_token": data["access_token"],
            "team": data["team"],
            "incoming_webhook": data.get("incoming_webhook", {}),
        }
        integration.integration_settings = {
            "channel": data.get("incoming_webhook", {}).get("channel", "#general"),
            "team_id": data["team"]["id"],
        }
        integration.is_active = True
        integration.save()

    messages.success(request, "Slack connected successfully!")
    return redirect("core:integrations")


@login_required
def integrate_shopify(request: HttpRequest) -> HttpResponse | HttpResponseRedirect:
    """Shopify integration setup page.

    Args:
        request: The HTTP request object.

    Returns:
        Shopify integration page or redirect to organization creation.
    """
    try:
        user_profile = UserProfile.objects.get(user=request.user)
        organization = user_profile.organization

        context = {"organization": organization}
        return render(request, "core/integrate_shopify.html.j2", context)

    except UserProfile.DoesNotExist:
        return redirect("core:create_organization")


def connect_shopify(request: HttpRequest) -> JsonResponse:
    """Connect Shopify integration via API.

    Args:
        request: The HTTP request object.

    Returns:
        JSON response with success status or error.
    """
    if request.method == "POST":
        data = json.loads(request.body)
        access_token = data.get("access_token")
        shop_url = data.get("shop_url")

        if not access_token or not shop_url:
            return JsonResponse(
                {"error": "Missing access token or shop URL"}, status=400
            )

        # Get user's organization
        if not request.user.is_authenticated:
            return JsonResponse({"error": "User not authenticated"}, status=401)

        try:
            user_profile = UserProfile.objects.get(user=request.user)
            organization = user_profile.organization
        except UserProfile.DoesNotExist:
            return JsonResponse({"error": "User profile not found"}, status=400)

        # Test the Shopify connection
        shop_domain = ShopifyAPI.get_shop_domain(shop_url, access_token)

        if not shop_domain:
            return JsonResponse({"error": "Invalid Shopify credentials"}, status=400)

        # Store or update Shopify integration
        integration, created = Integration.objects.get_or_create(
            organization=organization,
            integration_type="shopify",
            defaults={
                "oauth_credentials": {"access_token": access_token},
                "integration_settings": {
                    "shop_url": shop_url,
                    "shop_domain": shop_domain,
                },
                "is_active": True,
            },
        )

        if not created:
            # Update existing integration
            integration.oauth_credentials = {"access_token": access_token}
            integration.integration_settings = {
                "shop_url": shop_url,
                "shop_domain": shop_domain,
            }
            integration.is_active = True
            integration.save()

        return JsonResponse({"success": True, "shop_domain": shop_domain})

    return JsonResponse({"error": "Invalid request method"}, status=405)


def connect_stripe(request: HttpRequest) -> JsonResponse:
    """Connect Stripe integration via API.

    Args:
        request: The HTTP request object.

    Returns:
        JSON response with success status or error.
    """
    if request.method == "POST":
        data = json.loads(request.body)
        api_key = data.get("api_key")

        if not api_key:
            return JsonResponse({"error": "Missing API key"}, status=400)

        # Get user's organization
        if not request.user.is_authenticated:
            return JsonResponse({"error": "User not authenticated"}, status=401)

        try:
            user_profile = UserProfile.objects.get(user=request.user)
            organization = user_profile.organization
        except UserProfile.DoesNotExist:
            return JsonResponse({"error": "User profile not found"}, status=400)

        # Test the Stripe connection
        stripe_api = StripeAPI(api_key)
        account_info = stripe_api.get_account_info()

        if not account_info:
            return JsonResponse({"error": "Invalid Stripe API key"}, status=400)

        # Store or update Stripe integration
        integration, created = Integration.objects.get_or_create(
            organization=organization,
            integration_type="stripe_customer",
            defaults={
                "oauth_credentials": {"api_key": api_key},
                "integration_settings": {
                    "account_id": account_info.get("id"),
                    "business_profile": account_info.get("business_profile", {}),
                },
                "is_active": True,
            },
        )

        if not created:
            # Update existing integration
            integration.oauth_credentials = {"api_key": api_key}
            integration.integration_settings = {
                "account_id": account_info.get("id"),
                "business_profile": account_info.get("business_profile", {}),
            }
            integration.is_active = True
            integration.save()

        return JsonResponse({"success": True, "account_id": account_info.get("id")})

    return JsonResponse({"error": "Invalid request method"}, status=405)


@login_required
def integrate_chargify(request: HttpRequest) -> HttpResponse | HttpResponseRedirect:
    """Chargify integration page.

    Args:
        request: The HTTP request object.

    Returns:
        Chargify integration page or redirect to organization creation.
    """
    try:
        user_profile = UserProfile.objects.get(user=request.user)
        organization = user_profile.organization

        # Check if Chargify is already connected
        existing_integration = Integration.objects.filter(
            organization=organization, integration_type="chargify", is_active=True
        ).first()

        if request.method == "POST":
            webhook_secret = request.POST.get("webhook_secret", "").strip()

            if webhook_secret:
                if existing_integration:
                    # Update existing integration
                    existing_integration.webhook_secret = webhook_secret
                    existing_integration.save()
                    messages.success(
                        request, "Chargify/Maxio integration updated successfully!"
                    )
                else:
                    # Create new integration
                    Integration.objects.create(
                        organization=organization,
                        integration_type="chargify",
                        webhook_secret=webhook_secret,
                        is_active=True,
                    )
                    messages.success(
                        request, "Chargify/Maxio integration connected successfully!"
                    )

                return redirect("core:integrations")
            else:
                messages.error(request, "Please provide a webhook secret.")

        # Generate webhook URL for this organization
        webhook_url = request.build_absolute_uri(
            f"/webhooks/customer/chargify/{organization.uuid}/"
        )

        context: dict[str, Any] = {
            "organization": organization,
            "existing_integration": existing_integration,
            "webhook_url": webhook_url,
        }
        return render(request, "core/integrate_chargify.html.j2", context)

    except UserProfile.DoesNotExist:
        return redirect("core:create_organization")
