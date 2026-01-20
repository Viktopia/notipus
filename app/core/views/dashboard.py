"""Dashboard and organization management views.

This module handles the main dashboard and organization settings.
"""

import logging
from typing import Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect, render

from ..models import Organization, UserProfile

logger = logging.getLogger(__name__)


@login_required
def dashboard(request: HttpRequest) -> HttpResponse | HttpResponseRedirect:
    """Main dashboard for authenticated users.

    Args:
        request: The HTTP request object.

    Returns:
        Dashboard page or redirect to organization creation.
    """
    from core.services.dashboard import DashboardService

    dashboard_service = DashboardService()
    dashboard_data = dashboard_service.get_dashboard_data(request.user)

    if not dashboard_data:
        # User doesn't have a profile yet - redirect to organization creation
        return redirect("core:create_organization")

    # Flatten the data for template compatibility
    context: dict[str, Any] = {
        "organization": dashboard_data["organization"],
        "user_profile": dashboard_data["user_profile"],
        **dashboard_data["integrations"],  # has_slack, has_shopify, etc.
        "recent_activity": dashboard_data["recent_activity"],
        **dashboard_data["usage_data"],  # rate_limit_info, usage_stats, etc.
        **dashboard_data["trial_info"],  # trial_days_remaining, is_trial, etc.
    }

    return render(request, "core/dashboard.html.j2", context)


@login_required
def create_organization(request: HttpRequest) -> HttpResponse | HttpResponseRedirect:
    """Organization creation page.

    Args:
        request: The HTTP request object.

    Returns:
        Organization creation form or redirect to dashboard on success.
    """
    if request.method == "POST":
        name = request.POST.get("name")
        shop_domain = request.POST.get("shop_domain")
        selected_plan = request.session.get("selected_plan", "trial")

        if name:
            # Create organization
            organization = Organization.objects.create(
                name=name,
                shop_domain=shop_domain or "",  # Allow empty domain
                subscription_plan=selected_plan,
            )

            # Create user profile
            UserProfile.objects.create(
                user=request.user,
                organization=organization,
                slack_user_id="",  # Will be set when connecting Slack
            )

            messages.success(request, f"Organization '{name}' created successfully!")
            return redirect("core:dashboard")

    return render(request, "core/create_organization.html.j2")


@login_required
def organization_settings(request: HttpRequest) -> HttpResponse | HttpResponseRedirect:
    """Organization settings page.

    Args:
        request: The HTTP request object.

    Returns:
        Settings page or redirect to organization creation.
    """
    try:
        user_profile = UserProfile.objects.get(user=request.user)
        organization = user_profile.organization

        if request.method == "POST":
            organization.name = request.POST.get("name", organization.name)
            organization.shop_domain = request.POST.get(
                "shop_domain", organization.shop_domain
            )
            organization.save()
            messages.success(request, "Organization settings updated!")
            return redirect("core:organization_settings")

        context = {"organization": organization}
        return render(request, "core/organization_settings.html.j2", context)

    except UserProfile.DoesNotExist:
        return redirect("core:create_organization")
