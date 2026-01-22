"""Base classes and utilities for integration views.

This module provides the foundation for the plugin-based integration architecture,
including shared utilities, protocols, and helper functions.
"""

import logging
from typing import Protocol

from django.contrib import messages
from django.http import HttpRequest, HttpResponseRedirect
from django.shortcuts import redirect

from ...models import Organization, UserProfile

logger = logging.getLogger(__name__)

# Default timeout for external API requests (seconds)
DEFAULT_API_TIMEOUT = 30


class IntegrationProtocol(Protocol):
    """Protocol defining the interface for integration handlers.

    Integration handlers can implement any subset of these methods
    depending on their connection flow (OAuth vs manual configuration).
    """

    integration_type: str
    display_name: str

    def start_connect(self, request: HttpRequest) -> HttpResponseRedirect:
        """Start the integration connection flow.

        Args:
            request: The HTTP request object.

        Returns:
            Redirect to OAuth provider or setup page.
        """
        ...

    def handle_callback(self, request: HttpRequest) -> HttpResponseRedirect:
        """Handle OAuth callback from the provider.

        Args:
            request: The HTTP request object.

        Returns:
            Redirect to integrations page with success/error message.
        """
        ...

    def disconnect(self, request: HttpRequest) -> HttpResponseRedirect:
        """Disconnect the integration.

        Args:
            request: The HTTP request object.

        Returns:
            Redirect to integrations page.
        """
        ...


def get_user_organization(request: HttpRequest) -> Organization | None:
    """Get the organization for the authenticated user.

    Args:
        request: The HTTP request object.

    Returns:
        The user's organization or None if not found.
    """
    if not request.user.is_authenticated:
        return None

    try:
        user_profile = UserProfile.objects.get(user=request.user)
        return user_profile.organization
    except UserProfile.DoesNotExist:
        return None


def require_organization(
    request: HttpRequest,
) -> tuple[Organization | None, HttpResponseRedirect | None]:
    """Require the user to have an organization.

    Args:
        request: The HTTP request object.

    Returns:
        Tuple of (organization, redirect_response).
        If organization exists, redirect is None.
        If organization doesn't exist, organization is None and redirect is set.
    """
    organization = get_user_organization(request)
    if organization is None:
        if not request.user.is_authenticated:
            return None, redirect("account_login")
        return None, redirect("core:create_organization")
    return organization, None


def handle_disconnect_error(
    request: HttpRequest, integration_name: str
) -> HttpResponseRedirect:
    """Handle common disconnect error scenarios.

    Args:
        request: The HTTP request object.
        integration_name: Display name of the integration.

    Returns:
        Redirect to integrations page with error message.
    """
    messages.warning(request, f"No active {integration_name} integration found")
    return redirect("core:integrations")


def require_post_method(
    request: HttpRequest,
) -> HttpResponseRedirect | None:
    """Ensure request is a POST request.

    Args:
        request: The HTTP request object.

    Returns:
        Redirect with error if not POST, None otherwise.
    """
    if request.method != "POST":
        messages.error(request, "Invalid request method")
        return redirect("core:integrations")
    return None
