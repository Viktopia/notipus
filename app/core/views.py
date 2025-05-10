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
from app.webhooks.services.slack_client import SlackClient

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

    settings.DOMAIN_ENRICHMENT_SERVICE.enrich_domain(slack_domain)

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
                settings.DOMAIN_ENRICHMENT_SERVICE.enrich_domain(
                    organization.shop_domain
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
                "notify_payment_success": settings.notify_payment_success,
                "notify_payment_failure": settings.notify_payment_failure,
                # Add all other settings fields
            }
        )
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@login_required
def update_notification_settings(request):
    try:
        user_profile = request.user.userprofile
        settings = user_profile.organization.notification_settings

        data = json.loads(request.body)
        for field in NotificationSettings._meta.get_fields():
            if field.name in data and field.name not in [
                "id",
                "organization",
                "created_at",
                "updated_at",
            ]:
                setattr(settings, field.name, data[field.name])

        settings.save()
        return JsonResponse({"status": "success"})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)
