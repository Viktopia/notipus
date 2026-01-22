"""Chargify/Maxio integration views.

Handles Chargify webhook configuration for receiving subscription events.
"""

import logging
from typing import Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect, render

from ...models import Integration
from .base import require_organization

logger = logging.getLogger(__name__)

# Integration metadata
INTEGRATION_TYPE = "chargify"
DISPLAY_NAME = "Chargify / Maxio"


@login_required
def integrate_chargify(request: HttpRequest) -> HttpResponse | HttpResponseRedirect:
    """Chargify integration page.

    Args:
        request: The HTTP request object.

    Returns:
        Chargify integration page or redirect to organization creation.
    """
    organization, redirect_response = require_organization(request)
    if redirect_response:
        return redirect_response

    # Check if Chargify is already connected
    existing_integration = Integration.objects.filter(
        organization=organization, integration_type=INTEGRATION_TYPE, is_active=True
    ).first()

    if request.method == "POST":
        return _handle_chargify_connect(request, organization, existing_integration)

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


def _handle_chargify_connect(
    request: HttpRequest,
    organization: object,
    existing_integration: Integration | None,
) -> HttpResponseRedirect:
    """Handle POST request to connect/update Chargify integration.

    Args:
        request: The HTTP request object.
        organization: The user's organization.
        existing_integration: Existing integration if any.

    Returns:
        Redirect to integrations page.
    """
    webhook_secret = request.POST.get("webhook_secret", "").strip()

    if not webhook_secret:
        messages.error(request, "Please provide a webhook secret.")
        return redirect("core:integrate_chargify")

    if existing_integration:
        # Update existing integration
        existing_integration.webhook_secret = webhook_secret
        existing_integration.save()
        logger.info(
            f"Chargify integration updated for organization {organization.name}"
        )
        messages.success(request, "Chargify/Maxio integration updated successfully!")
    else:
        # Create new integration
        Integration.objects.create(
            organization=organization,
            integration_type=INTEGRATION_TYPE,
            webhook_secret=webhook_secret,
            is_active=True,
        )
        logger.info(
            f"Chargify integration created for organization {organization.name}"
        )
        messages.success(request, "Chargify/Maxio integration connected successfully!")

    return redirect("core:integrations")
