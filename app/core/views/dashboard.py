"""Dashboard and workspace management views.

This module handles the main dashboard and workspace settings.
"""

import logging
from typing import Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect, render

from ..models import UserProfile, Workspace, WorkspaceMember

logger = logging.getLogger(__name__)


@login_required
def dashboard(request: HttpRequest) -> HttpResponse | HttpResponseRedirect:
    """Main dashboard for authenticated users.

    Args:
        request: The HTTP request object.

    Returns:
        Dashboard page or redirect to workspace creation.
    """
    from core.services.dashboard import DashboardService

    dashboard_service = DashboardService()
    dashboard_data = dashboard_service.get_dashboard_data(request.user)

    if not dashboard_data:
        # User doesn't have a workspace yet - redirect to workspace creation
        return redirect("core:create_workspace")

    # Flatten the data for template compatibility
    context: dict[str, Any] = {
        "workspace": dashboard_data["workspace"],
        "user_profile": dashboard_data["user_profile"],
        "member": dashboard_data.get("member"),
        **dashboard_data["integrations"],  # has_slack, has_shopify, etc.
        "recent_activity": dashboard_data["recent_activity"],
        **dashboard_data["usage_data"],  # rate_limit_info, usage_stats, etc.
        **dashboard_data["trial_info"],  # trial_days_remaining, is_trial, etc.
    }

    return render(request, "core/dashboard.html.j2", context)


@login_required
def create_workspace(request: HttpRequest) -> HttpResponse | HttpResponseRedirect:
    """Workspace creation page.

    Args:
        request: The HTTP request object.

    Returns:
        Workspace creation form or redirect to dashboard on success.
    """
    if request.method == "POST":
        name = request.POST.get("name")
        shop_domain = request.POST.get("shop_domain")
        selected_plan = request.session.get("selected_plan", "trial")

        if name:
            # Create workspace
            # Use None for empty shop_domain to allow multiple orgs without domains
            # (PostgreSQL unique constraint allows multiple NULLs but not empty strings)
            workspace = Workspace.objects.create(
                name=name,
                shop_domain=shop_domain or None,
                subscription_plan=selected_plan,
            )

            # Create workspace member with owner role
            WorkspaceMember.objects.create(
                user=request.user,
                workspace=workspace,
                role="owner",
            )

            # Also create user profile for backward compatibility (slack_user_id)
            UserProfile.objects.create(
                user=request.user,
                workspace=workspace,
                slack_user_id="",  # Will be set when connecting Slack
            )

            messages.success(request, f"Workspace '{name}' created successfully!")
            return redirect("core:dashboard")

    return render(request, "core/create_workspace.html.j2")


@login_required
def workspace_settings(request: HttpRequest) -> HttpResponse | HttpResponseRedirect:
    """Workspace settings page.

    Args:
        request: The HTTP request object.

    Returns:
        Settings page or redirect to workspace creation.
    """
    try:
        # Try to get workspace from WorkspaceMember first
        member = WorkspaceMember.objects.filter(
            user=request.user, is_active=True
        ).first()
        if member:
            workspace = member.workspace
        else:
            # Fall back to UserProfile for backward compatibility
            user_profile = UserProfile.objects.get(user=request.user)
            workspace = user_profile.workspace

        if request.method == "POST":
            workspace.name = request.POST.get("name", workspace.name)
            workspace.shop_domain = request.POST.get(
                "shop_domain", workspace.shop_domain
            )
            workspace.save()
            messages.success(request, "Workspace settings updated!")
            return redirect("core:workspace_settings")

        context = {"workspace": workspace}
        return render(request, "core/workspace_settings.html.j2", context)

    except UserProfile.DoesNotExist:
        return redirect("core:create_workspace")
