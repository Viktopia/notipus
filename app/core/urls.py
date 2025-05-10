from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("auth/slack/", views.slack_auth, name="slack_auth"),
    path("auth/slack/callback/", views.slack_callback, name="slack_callback"),
    path("connect/slack/", views.slack_connect, name="slack_connect"),
    path(
        "connect/slack/callback/",
        views.slack_connect_callback,
        name="slack_connect_callback",
    ),
    path("connect/shopify/", views.connect_shopify, name="connect_shopify"),
    path("connect/stripe/", views.connect_stripe, name="connect_stripe"),
    path(
        "notification-settings/",
        views.get_notification_settings,
        name="get_notification_settings",
    ),
    path(
        "notification-settings/update/",
        views.update_notification_settings,
        name="update_notification_settings",
    ),
]
