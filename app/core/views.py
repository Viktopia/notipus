from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.db.models import Q
from django.conf import settings

import requests
import logging
import json

from .models import UserProfile, Organization, Integration, NotificationSettings
from .services.stripe import StripeAPI
from .services.shopify import ShopifyAPI
from webhooks.services.slack_client import SlackClient

logger = logging.getLogger(__name__)


def home(request):
    return HttpResponse("Welcome to the Django Project!")


def slack_auth(request):
    scopes = "openid,email,profile"
    auth_url = f"https://slack.com/openid/connect/authorize?client_id={settings.SLACK_CLIENT_ID}&scope={scopes}&redirect_uri={settings.SLACK_REDIRECT_URI}&response_type=code"
    return redirect(auth_url)


def slack_callback(request):
    code = request.GET.get("code")
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
        return HttpResponse("Authentication failed", status=400)

    user_info_response = requests.get(
        "https://slack.com/api/openid.connect.userInfo",
        headers={
            "Authorization": f"{data.get('token_type')} {data.get('access_token')}"
        },
    )
    user_info = user_info_response.json()
    if not user_info.get("ok"):
        return HttpResponse("Get user info failed", status=400)

    slack_user_id = user_info.get("sub")
    email = user_info.get("email")
    slack_team_id = user_info.get("https://slack.com/team_id")
    slack_domain = user_info.get("https://slack.com/team_domain")
    name = user_info.get("name")

    # Enrich domain if available
    if slack_domain:
        try:
            settings.DOMAIN_ENRICHMENT_SERVICE.enrich_domain(slack_domain)
        except Exception as e:
            logger.warning(f"Failed to enrich slack domain {slack_domain}: {str(e)}")
    else:
        logger.warning("No slack domain found in user info")

    try:
        user_profile = UserProfile.objects.get(slack_user_id=slack_user_id)
        user = user_profile.user
    except UserProfile.DoesNotExist:
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            user = User.objects.create_user(username=name, email=email)
            user.set_unusable_password()
            user.save()

        try:
            organization = Organization.objects.get(
                Q(slack_team_id=slack_team_id) | Q(slack_domain=slack_domain)
            )
        except Organization.DoesNotExist:
            organization = Organization.objects.create(
                slack_team_id=slack_team_id, slack_domain=slack_domain, name=name
            )
            if not organization.stripe_customer_id:
                customer_data = {
                    "email": user.email,
                    "name": organization.name,
                    "metadata": {"slack_team_id": organization.slack_team_id},
                }

                stripe_customer_data = StripeAPI.create_stripe_customer(customer_data)

                organization.stripe_customer_id = stripe_customer_data["id"]
                organization.save()

            if not organization.shop_domain:
                organization.shop_domain = ShopifyAPI.get_shop_domain()
                if organization.shop_domain:
                    try:
                        settings.DOMAIN_ENRICHMENT_SERVICE.enrich_domain(
                            organization.shop_domain
                        )
                    except Exception as e:
                        logger.warning(
                            f"Failed to enrich shop domain {organization.shop_domain}: {str(e)}"
                        )
                organization.save()

        user_profile, created = UserProfile.objects.get_or_create(
            user=user,
            defaults={
                "slack_user_id": slack_user_id,
                "slack_team_id": slack_team_id,
                "organization": organization,
            },
        )
        if not created:
            user_profile.slack_user_id = slack_user_id
            user_profile.slack_team_id = slack_team_id
            user_profile.organization = organization
            user_profile.save()

    login(request, user)
    return JsonResponse(
        {
            "slack_user_id": user_profile.slack_user_id,
            "email": user.email,
            "slack_team_id": user_profile.slack_team_id,
            "slack_domain": user_profile.organization.slack_team_id,
            "name": user.username,
        },
        status=200,
    )


def slack_connect(request):
    scopes = "incoming-webhook,commands"
    auth_url = f"https://slack.com/oauth/authorize?client_id={settings.SLACK_CLIENT_BOT_ID}&scope={scopes}&redirect_uri={settings.SLACK_REDIRECT_BOT_URI}"
    return redirect(auth_url)


def slack_connect_callback(request):
    code = request.GET.get("code")
    response = requests.post(
        "https://slack.com/api/oauth.access",
        data={
            "client_id": settings.SLACK_CLIENT_BOT_ID,
            "client_secret": settings.SLACK_CLIENT_BOT_SECRET,
            "code": code,
            "redirect_uri": settings.SLACK_REDIRECT_BOT_URI,
        },
    )
    data = response.json()
    if not data.get("ok"):
        return HttpResponse("Authentication failed", status=400)

    settings.SLACK_CLIENT = SlackClient(webhook_url=data["incoming_webhook"]["url"])

    return JsonResponse({"success": True}, status=200)


def connect_shopify(request):
    try:
        user_profile = request.user.userprofile
        organization = user_profile.organization

        integration, created = Integration.objects.get_or_create(
            organization=organization,
            integration_type="shopify",
            defaults={"auth_data": {"access_token": settings.SHOPIFY_ACCESS_TOKEN}},
        )

        if not created:
            integration.auth_data = {"access_token": settings.SHOPIFY_ACCESS_TOKEN}
            integration.save()

        return JsonResponse(
            {
                "status": "success",
                "message": "Shopify connected successfully",
                "shop_domain": organization.shop_domain,
            },
            status=200,
        )
    except Exception as e:
        logging.error(f"Error connecting Shopify: {str(e)}")
        return JsonResponse({"error": str(e)}, status=500)


def connect_stripe(request):
    try:
        user_profile = request.user.userprofile
        organization = user_profile.organization

        integration, created = Integration.objects.get_or_create(
            organization=organization,
            integration_type="stripe",
            defaults={"auth_data": {"secret_key": settings.STRIPE_SECRET_KEY}},
        )

        if not created:
            integration.auth_data = {"secret_key": settings.STRIPE_SECRET_KEY}
            integration.save()

        return JsonResponse(
            {
                "status": "success",
                "message": "Stripe connected successfully",
                "customer_id": organization.stripe_customer_id,
            },
            status=200,
        )
    except Exception as e:
        logging.error(f"Error connecting Stripe: {str(e)}")
        return JsonResponse({"error": str(e)}, status=500)


@login_required
def get_notification_settings(request):
    try:
        user_profile = request.user.userprofile
        settings = user_profile.organization.notification_settings
        return JsonResponse(
            {
                # Payment events
                "notify_payment_success": settings.notify_payment_success,
                "notify_payment_failure": settings.notify_payment_failure,
                # Subscription events
                "notify_subscription_created": settings.notify_subscription_created,
                "notify_subscription_updated": settings.notify_subscription_updated,
                "notify_subscription_canceled": settings.notify_subscription_canceled,
                # Trial events
                "notify_trial_ending": settings.notify_trial_ending,
                "notify_trial_expired": settings.notify_trial_expired,
                # Customer events
                "notify_customer_updated": settings.notify_customer_updated,
                "notify_signups": settings.notify_signups,
                # Shopify events
                "notify_shopify_order_created": settings.notify_shopify_order_created,
                "notify_shopify_order_updated": settings.notify_shopify_order_updated,
                "notify_shopify_order_paid": settings.notify_shopify_order_paid,
            }
        )
    except UserProfile.DoesNotExist:
        return JsonResponse({"error": "User profile not found"}, status=404)
    except NotificationSettings.DoesNotExist:
        return JsonResponse({"error": "Notification settings not found"}, status=404)
    except Exception as e:
        logger.error(f"Error getting notification settings: {str(e)}")
        return JsonResponse({"error": "Internal server error"}, status=500)


@login_required
def update_notification_settings(request):
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        user_profile = request.user.userprofile
        settings = user_profile.organization.notification_settings

        data = json.loads(request.body)

        # Define allowed fields for explicit validation
        allowed_fields = {
            # Payment events
            "notify_payment_success",
            "notify_payment_failure",
            # Subscription events
            "notify_subscription_created",
            "notify_subscription_updated",
            "notify_subscription_canceled",
            # Trial events
            "notify_trial_ending",
            "notify_trial_expired",
            # Customer events
            "notify_customer_updated",
            "notify_signups",
            # Shopify events
            "notify_shopify_order_created",
            "notify_shopify_order_updated",
            "notify_shopify_order_paid",
        }

        # Validate and update only allowed fields
        updated_fields = []
        for field_name, value in data.items():
            if field_name in allowed_fields:
                if isinstance(value, bool):
                    setattr(settings, field_name, value)
                    updated_fields.append(field_name)
                else:
                    return JsonResponse(
                        {"error": f"Field '{field_name}' must be a boolean value"},
                        status=400,
                    )
            elif field_name not in allowed_fields:
                return JsonResponse(
                    {"error": f"Field '{field_name}' is not allowed to be updated"},
                    status=400,
                )

        if updated_fields:
            settings.save(update_fields=updated_fields)

        return JsonResponse({"status": "success", "updated_fields": updated_fields})

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON data"}, status=400)
    except UserProfile.DoesNotExist:
        return JsonResponse({"error": "User profile not found"}, status=404)
    except NotificationSettings.DoesNotExist:
        return JsonResponse({"error": "Notification settings not found"}, status=404)
    except Exception as e:
        logger.error(f"Error updating notification settings: {str(e)}")
        return JsonResponse({"error": "Internal server error"}, status=500)
