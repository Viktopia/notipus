"""Billing and subscription management views.

This module handles plan selection, billing dashboard, payment methods,
and checkout flows.
"""

import logging
from typing import Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.utils import timezone
from webhooks.services.rate_limiter import rate_limiter

from ..models import Plan, UserProfile

logger = logging.getLogger(__name__)


def select_plan(request: HttpRequest) -> HttpResponse | HttpResponseRedirect:
    """Plan selection page.

    Args:
        request: The HTTP request object.

    Returns:
        Plan selection page or redirect on successful selection.
    """
    if request.method == "POST":
        selected_plan = request.POST.get("plan")
        # Validate against available plans
        if Plan.objects.filter(name=selected_plan, is_active=True).exists():
            request.session["selected_plan"] = selected_plan
            return redirect("core:plan_selected")

    # Get plans from database
    plans_queryset = Plan.objects.filter(is_active=True).order_by("price_monthly")
    plans: list[dict[str, Any]] = []

    for plan in plans_queryset:
        price_display = (
            "Free" if plan.price_monthly == 0 else f"${plan.price_monthly:.0f}/month"
        )
        plans.append(
            {
                "name": plan.name,
                "display_name": plan.display_name,
                "price": price_display,
                "features": plan.features,
                "description": plan.description,
            }
        )

    return render(request, "core/select_plan.html.j2", {"plans": plans})


def plan_selected(request: HttpRequest) -> HttpResponse | HttpResponseRedirect:
    """Plan confirmation page.

    Args:
        request: The HTTP request object.

    Returns:
        Plan confirmation page or redirect if no plan selected.
    """
    selected_plan = request.session.get("selected_plan")
    if not selected_plan:
        return redirect("core:select_plan")

    return render(
        request, "core/plan_selected.html.j2", {"selected_plan": selected_plan}
    )


@login_required
def billing_dashboard(request: HttpRequest) -> HttpResponse | HttpResponseRedirect:
    """Billing dashboard showing current plan, usage, and billing info.

    Args:
        request: The HTTP request object.

    Returns:
        Billing dashboard page or redirect to organization creation.
    """
    from core.services.dashboard import BillingService

    try:
        user_profile = UserProfile.objects.get(user=request.user)
        organization = user_profile.organization

        billing_service = BillingService()
        billing_data = billing_service.get_billing_dashboard_data(organization)

        # Flatten data for template compatibility
        context: dict[str, Any] = {
            "organization": billing_data["organization"],
            "user_profile": user_profile,
            **billing_data["usage_data"],  # rate_limit_info, usage_stats, etc.
            **billing_data["trial_info"],  # trial_days_remaining, is_trial, etc.
            "available_plans": billing_data["available_plans"],
            "current_plan": billing_data["current_plan"],
        }

        return render(request, "core/billing_dashboard.html.j2", context)

    except UserProfile.DoesNotExist:
        return redirect("core:create_organization")


@login_required
def upgrade_plan(request: HttpRequest) -> HttpResponse | HttpResponseRedirect:
    """Plan upgrade/downgrade page.

    Args:
        request: The HTTP request object.

    Returns:
        Upgrade plan page or redirect to organization creation.
    """
    from core.services.dashboard import BillingService

    try:
        user_profile = UserProfile.objects.get(user=request.user)
        organization = user_profile.organization

        billing_service = BillingService()
        available_plans = billing_service.get_available_plans(
            organization.subscription_plan
        )

        context: dict[str, Any] = {
            "organization": organization,
            "plans": available_plans,
            "current_plan": organization.subscription_plan,
        }
        return render(request, "core/upgrade_plan.html.j2", context)

    except UserProfile.DoesNotExist:
        return redirect("core:create_organization")


@login_required
def payment_methods(request: HttpRequest) -> HttpResponse | HttpResponseRedirect:
    """Payment method management page.

    Args:
        request: The HTTP request object.

    Returns:
        Payment methods page or redirect to organization creation.
    """
    try:
        user_profile = UserProfile.objects.get(user=request.user)
        organization = user_profile.organization

        # In a real implementation, you would fetch payment methods from Stripe
        # using organization.stripe_customer_id
        payment_methods_list: list[dict[str, Any]] = []

        context: dict[str, Any] = {
            "organization": organization,
            "payment_methods": payment_methods_list,
            "has_payment_method": organization.payment_method_added,
        }
        return render(request, "core/payment_methods.html.j2", context)

    except UserProfile.DoesNotExist:
        return redirect("core:create_organization")


@login_required
def billing_history(request: HttpRequest) -> HttpResponse | HttpResponseRedirect:
    """Billing history and invoices page.

    Args:
        request: The HTTP request object.

    Returns:
        Billing history page or redirect to organization creation.
    """
    try:
        user_profile = UserProfile.objects.get(user=request.user)
        organization = user_profile.organization

        # In a real implementation, you would fetch invoices from Stripe
        invoices: list[dict[str, Any]] = []

        # Get current month billing amount from Plan model
        current_month_amount = 0.00
        if organization.subscription_status != "trial":
            try:
                plan = Plan.objects.get(
                    name=organization.subscription_plan, is_active=True
                )
                current_month_amount = float(plan.price_monthly)
            except Plan.DoesNotExist:
                current_month_amount = 0.00

        # Get rate limit info for next payment date
        is_allowed, rate_limit_info = rate_limiter.check_rate_limit(organization)

        # Calculate trial days remaining
        trial_days_remaining = 0
        if organization.subscription_status == "trial" and organization.trial_end_date:
            trial_days_remaining = max(
                0, (organization.trial_end_date - timezone.now()).days
            )

        context: dict[str, Any] = {
            "organization": organization,
            "invoices": invoices,
            "current_month_amount": current_month_amount,
            "rate_limit_info": rate_limit_info,
            "trial_days_remaining": trial_days_remaining,
        }
        return render(request, "core/billing_history.html.j2", context)

    except UserProfile.DoesNotExist:
        return redirect("core:create_organization")


@login_required
def checkout(
    request: HttpRequest, plan_name: str
) -> HttpResponse | HttpResponseRedirect:
    """Stripe checkout page for plan upgrades.

    Args:
        request: The HTTP request object.
        plan_name: Name of the plan to checkout.

    Returns:
        Checkout page or redirect on invalid plan.
    """
    try:
        user_profile = UserProfile.objects.get(user=request.user)
        organization = user_profile.organization

        # Validate plan
        valid_plans = ["basic", "pro", "enterprise"]
        if plan_name not in valid_plans:
            messages.error(request, "Invalid plan selected.")
            return redirect("core:upgrade_plan")

        # Get plan details
        plan_details = {
            "basic": {
                "name": "Basic Plan",
                "price": 29,
                "stripe_price_id": "price_basic_monthly",
            },
            "pro": {
                "name": "Pro Plan",
                "price": 99,
                "stripe_price_id": "price_pro_monthly",
            },
            "enterprise": {
                "name": "Enterprise Plan",
                "price": 299,
                "stripe_price_id": "price_enterprise_monthly",
            },
        }

        plan = plan_details[plan_name]

        # Store plan selection in session for checkout success
        request.session["checkout_plan"] = plan_name

        context: dict[str, Any] = {
            "organization": organization,
            "plan": plan,
            "plan_name": plan_name,
            # In a real implementation, you would create a Stripe checkout session here
            "stripe_checkout_url": f"#checkout-{plan_name}",  # Placeholder
        }
        return render(request, "core/checkout.html.j2", context)

    except UserProfile.DoesNotExist:
        return redirect("core:create_organization")


@login_required
def checkout_success(request: HttpRequest) -> HttpResponse | HttpResponseRedirect:
    """Checkout success page.

    Args:
        request: The HTTP request object.

    Returns:
        Success page or redirect to billing dashboard.
    """
    plan_name = request.session.get("checkout_plan")
    if not plan_name:
        return redirect("core:billing_dashboard")

    # Clear session
    request.session.pop("checkout_plan", None)

    context: dict[str, Any] = {
        "plan_name": plan_name,
    }
    return render(request, "core/checkout_success.html.j2", context)


@login_required
def checkout_cancel(request: HttpRequest) -> HttpResponse:
    """Checkout cancelled page.

    Args:
        request: The HTTP request object.

    Returns:
        Checkout cancel page.
    """
    # Clear session
    request.session.pop("checkout_plan", None)

    return render(request, "core/checkout_cancel.html.j2")
