"""Shopify integration views.

Handles Shopify webhook configuration for receiving order and customer events.
"""

import json
import logging

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import render

from ...models import Integration
from ...services.shopify import ShopifyAPI
from .base import get_user_organization, require_organization

logger = logging.getLogger(__name__)

# Integration metadata
INTEGRATION_TYPE = "shopify"
DISPLAY_NAME = "Shopify"


@login_required
def integrate_shopify(request: HttpRequest) -> HttpResponse | HttpResponseRedirect:
    """Shopify integration setup page.

    Args:
        request: The HTTP request object.

    Returns:
        Shopify integration page or redirect to organization creation.
    """
    organization, redirect_response = require_organization(request)
    if redirect_response:
        return redirect_response

    context = {"organization": organization}
    return render(request, "core/integrate_shopify.html.j2", context)


def connect_shopify(request: HttpRequest) -> JsonResponse:
    """Connect Shopify integration via API.

    Args:
        request: The HTTP request object.

    Returns:
        JSON response with success status or error.
    """
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    access_token = data.get("access_token")
    shop_url = data.get("shop_url")

    if not access_token or not shop_url:
        return JsonResponse({"error": "Missing access token or shop URL"}, status=400)

    # Get user's organization
    organization = get_user_organization(request)
    if not organization:
        if not request.user.is_authenticated:
            return JsonResponse({"error": "User not authenticated"}, status=401)
        return JsonResponse({"error": "User profile not found"}, status=400)

    # Test the Shopify connection
    shop_domain = ShopifyAPI.get_shop_domain(shop_url, access_token)

    if not shop_domain:
        return JsonResponse({"error": "Invalid Shopify credentials"}, status=400)

    # Store or update Shopify integration
    integration, created = Integration.objects.get_or_create(
        organization=organization,
        integration_type=INTEGRATION_TYPE,
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

    logger.info(
        f"Shopify {'connected' if created else 'updated'} for "
        f"organization {organization.name} (shop: {shop_domain})"
    )

    return JsonResponse({"success": True, "shop_domain": shop_domain})
