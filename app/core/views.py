from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.db.models import Q

import requests

from core.models import UserProfile, Organization

SLACK_CLIENT_ID = '8551300556885.8583299723987'
SLACK_CLIENT_SECRET = 'e1f6c5840c3eed438d4447387c7740f9'
SLACK_REDIRECT_URI = 'https://0b62-185-94-29-180.ngrok-free.app/auth/slack/callback'


def home(request):
    return HttpResponse("Welcome to the Django Project!")


def slack_auth(request):
    auth_url = f"https://slack.com/openid/connect/authorize?client_id={SLACK_CLIENT_ID}&scope=openid%20email%20profile&redirect_uri={SLACK_REDIRECT_URI}&response_type=code"
    return redirect(auth_url)


def slack_callback(request):
    code = request.GET.get('code')
    response = requests.post('https://slack.com/api/openid.connect.token', data={
        'client_id': SLACK_CLIENT_ID,
        'client_secret': SLACK_CLIENT_SECRET,
        'code': code,
        'redirect_uri': SLACK_REDIRECT_URI
    })
    data = response.json()
    if not data.get('ok'):
        return HttpResponse('Authentication failed', status=400)

    user_info_response = requests.get('https://slack.com/api/openid.connect.userInfo', headers={"Authorization": f"{data.get('token_type')} {data.get('access_token')}"})
    user_info = user_info_response.json()
    if not user_info.get('ok'):
        return HttpResponse('Get user info failed', status=400)

    slack_user_id = user_info.get('sub')
    email = user_info.get('email')
    slack_team_id = user_info.get('https://slack.com/team_id')
    slack_domain = user_info.get('https://slack.com/team_domain')
    name = user_info.get('name')

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
                slack_team_id=slack_team_id,
                slack_domain=slack_domain,
                name=name
            )

        user_profile, created = UserProfile.objects.get_or_create(
            user=user,
            defaults={
                'slack_user_id': slack_user_id,
                'slack_team_id': slack_team_id,
                'organization': organization
            }
        )
        if not created:
            user_profile.slack_user_id = slack_user_id
            user_profile.slack_team_id = slack_team_id
            user_profile.organization = organization
            user_profile.save()

    login(request, user)
    return JsonResponse({
        "slack_user_id": user_profile.slack_user_id,
        "email": user.email,
        "slack_team_id": user_profile.slack_team_id,
        "slack_domain": user_profile.organization.slack_team_id,
        "name": user.username,
    }, status=200)
