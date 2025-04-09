from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.db.models import Q
from django.conf import settings
from django.utils import timezone

import requests
import logging
import json

from core.models import UserProfile, Organization, Integration
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

                response = requests.post(
                    "https://api.stripe.com/v1/customers",
                    headers={"Authorization": f"Bearer {settings.STRIPE_SECRET_KEY}"},
                    data=customer_data,
                )

                if response.status_code == 200:
                    organization.stripe_customer_id = response.json()["id"]
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


def stripe_connect(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)

    state = {
        "user_id": request.user.id,
        "organization_id": request.user.userprofile.organization.id,
    }
    auth_url = f"https://com.example.notipus/oauth/v2/authorize?client_id=${settings.STRIPE_CLIENT_ID}&redirect_uri=${settings.STRIPE_REDIRECT_URI}&state=${state}"
    return redirect(auth_url)


def stripe_connect_callback(request):
    try:
        state_json = request.GET.get("state")
        if not state_json:
            logger.error("Missing state parameter in Stripe callback")
            return HttpResponse("Invalid request: missing state", status=400)

        state = json.loads(state_json)
        user_id = state.get("user_id")
        organization_id = state.get("organization_id")

        if not user_id or not organization_id:
            logger.error("Invalid state content in Stripe callback")
            return HttpResponse("Invalid state content", status=400)

        try:
            organization = Organization.objects.get(id=organization_id)
        except Organization.DoesNotExist:
            logger.error(f"Organization not found: {organization_id}")
            return HttpResponse("Organization not found", status=404)

        code = request.GET.get("code")
        response = requests.post(
            "https://api.stripe.com/v1/oauth/token",
            data={
                "client_id": settings.STRIPE_CLIENT_ID,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.STRIPE_REDIRECT_URI,
            },
        )
        if not response.status_code == 200:
            return HttpResponse("Authentication failed", status=400)

        data = response.json()
        stripe_user_id = data.get("stripe_user_id")

        if not stripe_user_id:
            return JsonResponse({"error": "Missing Stripe user ID"}, status=400)

        integration, create = Integration.objects.update_or_create(
            organization=organization,
            integration_type="stripe",
            defaults={
                "auth_data": {
                    "stripe_user_id": stripe_user_id,
                    "access_token": data.get("access_token"),
                    "refresh_token": data.get("refresh_token"),
                    "token_type": data.get("token_type"),
                    "scope": data.get("scope"),
                    "livemode": data.get("livemode", False),
                    "connected_at": timezone.now().isoformat(),
                    "connected_by": user_id,
                }
            },
        )

        return JsonResponse(
            {
                "status": "success",
                "integration": {
                    "id": integration.id,
                    "type": integration.integration_type,
                    "connected_at": integration.auth_data.get("connected_at"),
                    "livemode": integration.auth_data.get("livemode"),
                },
            }
        )
    except Exception as e:
        logger.error(f"Error in stripe_connect_callback: {str(e)}", exc_info=True)
        return JsonResponse({"error": "Internal server error"}, status=500)
