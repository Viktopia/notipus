import json
import logging

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

# Import services for Redis-based webhook activity
from webhooks.services.rate_limiter import rate_limiter

from .models import Integration, NotificationSettings, Organization, UserProfile
from .services.shopify import ShopifyAPI
from .services.stripe import StripeAPI
from .services.webauthn import WebAuthnService

logger = logging.getLogger(__name__)


def home(request):
    return HttpResponse("Welcome to the Django Project!")


def slack_auth(request):
    scopes = "openid,email,profile"
    auth_url = f"https://slack.com/openid/connect/authorize?client_id={settings.SLACK_CLIENT_ID}&scope={scopes}&redirect_uri={settings.SLACK_REDIRECT_URI}&response_type=code"
    return redirect(auth_url)


def _get_slack_token(code):
    """Exchange OAuth code for access token"""
    response = requests.post(
        "https://slack.com/api/openid.connect.token",
        data={
            "client_id": settings.SLACK_CLIENT_ID,
            "client_secret": settings.SLACK_CLIENT_SECRET,
            "code": code,
            "redirect_uri": settings.SLACK_REDIRECT_URI,
        },
    )
    data = response.json()
    if not data.get("ok"):
        return None
    return data


def _get_slack_user_info(access_token):
    """Get user information from Slack"""
    response = requests.get(
        "https://slack.com/api/openid.connect.userInfo",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    data = response.json()
    if not data.get("ok"):
        return None
    return data


def slack_auth_callback(request):
    code = request.GET.get("code")
    if not code:
        return HttpResponse("Authorization failed: No code provided", status=400)

    # Exchange code for token
    token_data = _get_slack_token(code)
    if not token_data:
        return HttpResponse("Failed to get access token", status=400)

    # Get user info
    user_info = _get_slack_user_info(token_data["access_token"])
    if not user_info:
        return HttpResponse("Failed to get user information", status=400)

    # Extract user details
    slack_id = user_info.get("sub")
    email = user_info.get("email")
    name = user_info.get("name", "")

    if not slack_id or not email:
        return HttpResponse("Invalid user data from Slack", status=400)

    # Find or create user
    user, created = User.objects.get_or_create(
        email=email, defaults={"username": email, "first_name": name}
    )

    if created:
        logger.info(f"Created new user: {email}")

    # Try to find existing UserProfile
    try:
        profile = UserProfile.objects.get(slack_user_id=slack_id)
        if profile.user != user:
            # Link existing profile to this user account
            profile.user = user
            profile.save()
        user = profile.user
    except UserProfile.DoesNotExist:
        # Check if user already has a profile with different slack_id
        try:
            profile = UserProfile.objects.get(user=user)
            profile.slack_user_id = slack_id
            profile.save()
        except UserProfile.DoesNotExist:
            # No profile exists - this is handled later when joining a team
            pass

    # Log the user in
    login(request, user)

    return redirect("core:dashboard")


def slack_connect(request):
    """Initialize Slack connection for workspace notifications"""
    scopes = "incoming-webhook,chat:write,channels:read"
    auth_url = f"https://slack.com/oauth/v2/authorize?client_id={settings.SLACK_CLIENT_ID}&scope={scopes}&redirect_uri={settings.SLACK_CONNECT_REDIRECT_URI}&response_type=code"
    return redirect(auth_url)


def slack_connect_callback(request):
    """Handle Slack OAuth callback for workspace notifications"""
    code = request.GET.get("code")
    if not code:
        return HttpResponse("Authorization failed: No code provided", status=400)

    # Exchange code for token
    response = requests.post(
        "https://slack.com/api/oauth.v2.access",
        data={
            "client_id": settings.SLACK_CLIENT_ID,
            "client_secret": settings.SLACK_CLIENT_SECRET,
            "code": code,
            "redirect_uri": settings.SLACK_CONNECT_REDIRECT_URI,
        },
    )
    data = response.json()

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


def connect_shopify(request):
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
        shopify_api = ShopifyAPI(access_token, shop_url)
        shop_domain = shopify_api.get_shop_domain()

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


def connect_stripe(request):
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
def get_notification_settings(request):
    try:
        user_profile = UserProfile.objects.get(user=request.user)
        organization = user_profile.organization
        settings_obj, created = NotificationSettings.objects.get_or_create(
            organization=organization
        )

        settings_data = {
            "notify_payment_success": settings_obj.notify_payment_success,
            "notify_payment_failure": settings_obj.notify_payment_failure,
            "notify_subscription_created": settings_obj.notify_subscription_created,
            "notify_subscription_updated": settings_obj.notify_subscription_updated,
            "notify_subscription_canceled": settings_obj.notify_subscription_canceled,
            "notify_trial_ending": settings_obj.notify_trial_ending,
            "notify_trial_expired": settings_obj.notify_trial_expired,
            "notify_customer_updated": settings_obj.notify_customer_updated,
            "notify_signups": settings_obj.notify_signups,
            "notify_shopify_order_created": settings_obj.notify_shopify_order_created,
            "notify_shopify_order_updated": settings_obj.notify_shopify_order_updated,
            "notify_shopify_order_paid": settings_obj.notify_shopify_order_paid,
        }

        return JsonResponse(settings_data)

    except UserProfile.DoesNotExist:
        return JsonResponse({"error": "User profile not found"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
def update_notification_settings(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        user_profile = UserProfile.objects.get(user=request.user)
        organization = user_profile.organization
        settings_obj, created = NotificationSettings.objects.get_or_create(
            organization=organization
        )

        data = json.loads(request.body)

        # Update settings
        for field, value in data.items():
            if hasattr(settings_obj, field) and isinstance(value, bool):
                setattr(settings_obj, field, value)

        settings_obj.save()

        return JsonResponse({"success": True})

    except UserProfile.DoesNotExist:
        return JsonResponse({"error": "User profile not found"}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON data"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


# === NEW USER FLOW VIEWS ===


def landing(request):
    """Landing page for new users"""
    if request.user.is_authenticated:
        return redirect("core:dashboard")
    return render(request, "core/landing.html.j2")


@login_required
def dashboard(request):
    """Main dashboard for authenticated users"""
    from core.services.dashboard import DashboardService

    dashboard_service = DashboardService()
    dashboard_data = dashboard_service.get_dashboard_data(request.user)

    if not dashboard_data:
        # User doesn't have a profile yet - redirect to organization creation
        return redirect("core:create_organization")

    # Flatten the data for template compatibility
    context = {
        "organization": dashboard_data["organization"],
        "user_profile": dashboard_data["user_profile"],
        **dashboard_data["integrations"],  # has_slack, has_shopify, etc.
        "recent_activity": dashboard_data["recent_activity"],
        **dashboard_data["usage_data"],  # rate_limit_info, usage_stats, etc.
        **dashboard_data["trial_info"],  # trial_days_remaining, is_trial, etc.
    }

    return render(request, "core/dashboard.html.j2", context)


def select_plan(request):
    """Plan selection page"""
    from core.models import Plan

    if request.method == "POST":
        selected_plan = request.POST.get("plan")
        # Validate against available plans
        if Plan.objects.filter(name=selected_plan, is_active=True).exists():
            request.session["selected_plan"] = selected_plan
            return redirect("core:plan_selected")

    # Get plans from database
    plans_queryset = Plan.objects.filter(is_active=True).order_by("price_monthly")
    plans = []

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


def plan_selected(request):
    """Plan confirmation page"""
    selected_plan = request.session.get("selected_plan")
    if not selected_plan:
        return redirect("core:select_plan")

    return render(
        request, "core/plan_selected.html.j2", {"selected_plan": selected_plan}
    )


@login_required
def create_organization(request):
    """Organization creation page"""
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
def organization_settings(request):
    """Organization settings page"""
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


@login_required
def integrations(request):
    """Integrations overview page"""
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
def integrate_slack(request):
    """Start Slack integration flow"""
    return redirect("core:slack_connect")


@login_required
def integrate_shopify(request):
    """Shopify integration setup page"""
    try:
        user_profile = UserProfile.objects.get(user=request.user)
        organization = user_profile.organization

        context = {"organization": organization}
        return render(request, "core/integrate_shopify.html.j2", context)

    except UserProfile.DoesNotExist:
        return redirect("core:create_organization")


@login_required
def integrate_chargify(request):
    """Chargify integration page"""
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

        context = {
            "organization": organization,
            "existing_integration": existing_integration,
            "webhook_url": webhook_url,
        }
        return render(request, "core/integrate_chargify.html.j2", context)

    except UserProfile.DoesNotExist:
        return redirect("core:create_organization")


@login_required
def billing_dashboard(request):
    """Billing dashboard showing current plan, usage, and billing info"""
    from core.services.dashboard import BillingService

    try:
        user_profile = UserProfile.objects.get(user=request.user)
        organization = user_profile.organization

        billing_service = BillingService()
        billing_data = billing_service.get_billing_dashboard_data(organization)

        # Flatten data for template compatibility
        context = {
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
def upgrade_plan(request):
    """Plan upgrade/downgrade page"""
    from core.services.dashboard import BillingService

    try:
        user_profile = UserProfile.objects.get(user=request.user)
        organization = user_profile.organization

        billing_service = BillingService()
        available_plans = billing_service.get_available_plans(
            organization.subscription_plan
        )

        context = {
            "organization": organization,
            "plans": available_plans,
            "current_plan": organization.subscription_plan,
        }
        return render(request, "core/upgrade_plan.html.j2", context)

    except UserProfile.DoesNotExist:
        return redirect("core:create_organization")


@login_required
def payment_methods(request):
    """Payment method management page"""
    try:
        user_profile = UserProfile.objects.get(user=request.user)
        organization = user_profile.organization

        # In a real implementation, you would fetch payment methods from Stripe
        # using organization.stripe_customer_id
        payment_methods = []

        context = {
            "organization": organization,
            "payment_methods": payment_methods,
            "has_payment_method": organization.payment_method_added,
        }
        return render(request, "core/payment_methods.html.j2", context)

    except UserProfile.DoesNotExist:
        return redirect("core:create_organization")


@login_required
def billing_history(request):
    """Billing history and invoices page"""
    try:
        user_profile = UserProfile.objects.get(user=request.user)
        organization = user_profile.organization

        # In a real implementation, you would fetch invoices from Stripe
        # using organization.stripe_customer_id
        invoices = []

        # Get current month billing amount from Plan model
        current_month_amount = 0.00
        if organization.subscription_status != "trial":
            from core.models import Plan

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

        context = {
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
def checkout(request, plan_name):
    """Stripe checkout page for plan upgrades"""
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

        context = {
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
def checkout_success(request):
    """Checkout success page"""
    plan_name = request.session.get("checkout_plan")
    if not plan_name:
        return redirect("core:billing_dashboard")

    # Clear session
    request.session.pop("checkout_plan", None)

    context = {
        "plan_name": plan_name,
    }
    return render(request, "core/checkout_success.html.j2", context)


@login_required
def checkout_cancel(request):
    """Checkout cancelled page"""
    # Clear session
    request.session.pop("checkout_plan", None)

    return render(request, "core/checkout_cancel.html.j2")


# === WEBAUTHN VIEWS ===


@csrf_exempt
@require_http_methods(["POST"])
def webauthn_register_begin(request):
    """Start WebAuthn registration flow for adding a passkey."""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)

    try:
        webauthn_service = WebAuthnService()
        options = webauthn_service.generate_registration_options(request.user)
        return JsonResponse({"success": True, "options": options})
    except Exception as e:
        logger.error(f"WebAuthn registration begin error: {e}")
        return JsonResponse({"error": "Failed to start registration"}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def webauthn_register_complete(request):
    """Complete WebAuthn registration and store the credential."""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)

    try:
        data = json.loads(request.body)
        credential_data = data.get("credential")
        credential_name = data.get("name", "Passkey")

        if not credential_data:
            return JsonResponse({"error": "Missing credential data"}, status=400)

        webauthn_service = WebAuthnService()
        success = webauthn_service.verify_registration(
            request.user, credential_data, credential_name
        )

        if success:
            return JsonResponse(
                {"success": True, "message": "Passkey registered successfully"}
            )
        else:
            return JsonResponse(
                {"error": "Registration verification failed"}, status=400
            )

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON data"}, status=400)
    except Exception as e:
        logger.error(f"WebAuthn registration complete error: {e}")
        return JsonResponse({"error": "Failed to complete registration"}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def webauthn_authenticate_begin(request):
    """Start WebAuthn authentication flow for passkey login."""
    try:
        data = json.loads(request.body)
        username = data.get("username")  # Optional for usernameless flow

        webauthn_service = WebAuthnService()
        options = webauthn_service.generate_authentication_options(username)
        return JsonResponse({"success": True, "options": options})

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON data"}, status=400)
    except Exception as e:
        logger.error(f"WebAuthn authentication begin error: {e}")
        return JsonResponse({"error": "Failed to start authentication"}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def webauthn_authenticate_complete(request):
    """Complete WebAuthn authentication and log the user in."""
    try:
        data = json.loads(request.body)
        credential_data = data.get("credential")

        if not credential_data:
            return JsonResponse({"error": "Missing credential data"}, status=400)

        webauthn_service = WebAuthnService()
        user = webauthn_service.verify_authentication(credential_data)

        if user:
            # Log the user in
            login(request, user)
            return JsonResponse(
                {
                    "success": True,
                    "message": "Authentication successful",
                    "redirect_url": "/dashboard/",
                }
            )
        else:
            return JsonResponse(
                {"error": "Authentication verification failed"}, status=401
            )

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON data"}, status=400)
    except Exception as e:
        logger.error(f"WebAuthn authentication complete error: {e}")
        return JsonResponse({"error": "Failed to complete authentication"}, status=500)


@login_required
def webauthn_credentials(request):
    """View and manage user's WebAuthn credentials."""
    if request.method == "GET":
        # Return user's existing credentials
        from .models import WebAuthnCredential

        credentials = WebAuthnCredential.objects.filter(user=request.user).values(
            "id", "name", "created_at", "last_used"
        )
        return JsonResponse({"credentials": list(credentials)})

    elif request.method == "DELETE":
        # Delete a specific credential
        try:
            data = json.loads(request.body)
            credential_id = data.get("credential_id")

            if not credential_id:
                return JsonResponse({"error": "Missing credential_id"}, status=400)

            from .models import WebAuthnCredential

            WebAuthnCredential.objects.filter(
                id=credential_id, user=request.user
            ).delete()

            return JsonResponse({"success": True, "message": "Credential deleted"})

        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON data"}, status=400)
        except Exception as e:
            logger.error(f"WebAuthn credential deletion error: {e}")
            return JsonResponse({"error": "Failed to delete credential"}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def webauthn_signup_begin(request):
    """Start WebAuthn registration flow for passwordless signup."""
    try:
        data = json.loads(request.body)
        username = data.get("username", "").strip()
        email = data.get("email", "").strip()

        if not username or not email:
            return JsonResponse(
                {"error": "Username and email are required"}, status=400
            )

        # Check if username or email already exists
        if User.objects.filter(username=username).exists():
            return JsonResponse({"error": "Username already exists"}, status=400)

        if User.objects.filter(email=email).exists():
            return JsonResponse({"error": "Email already exists"}, status=400)

        webauthn_service = WebAuthnService()
        options = webauthn_service.generate_signup_registration_options(username, email)
        return JsonResponse({"success": True, "options": options})

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON data"}, status=400)
    except Exception as e:
        logger.error(f"WebAuthn signup begin error: {e}")
        return JsonResponse({"error": "Failed to start registration"}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def webauthn_signup_complete(request):
    """Complete WebAuthn registration and create user account."""
    try:
        data = json.loads(request.body)
        credential_data = data.get("credential")
        username = data.get("username", "").strip()
        email = data.get("email", "").strip()

        if not credential_data or not username or not email:
            return JsonResponse({"error": "Missing required data"}, status=400)

        webauthn_service = WebAuthnService()
        user = webauthn_service.complete_signup_registration(
            credential_data, username, email
        )

        if user:
            # Log the user in
            from django.contrib.auth import login

            login(request, user)

            return JsonResponse(
                {
                    "success": True,
                    "message": "Account created successfully with passkey",
                    "redirect_url": "/dashboard/",
                }
            )
        else:
            return JsonResponse(
                {"error": "Registration verification failed"}, status=400
            )

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON data"}, status=400)
    except Exception as e:
        logger.error(f"WebAuthn signup complete error: {e}")
        return JsonResponse({"error": "Failed to complete registration"}, status=500)
