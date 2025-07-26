from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    # Landing and dashboard
    path("", views.landing, name="landing"),
    path("dashboard/", views.dashboard, name="dashboard"),

    # Plan selection flow
    path("select-plan/", views.select_plan, name="select_plan"),
    path("plan/selected/", views.plan_selected, name="plan_selected"),

    # Organization management
    path("organization/create/", views.create_organization, name="create_organization"),
    path("organization/settings/", views.organization_settings, name="organization_settings"),

    # OAuth integrations (to be implemented)
    path("integrations/", views.integrations, name="integrations"),
    path("integrate/slack/", views.integrate_slack, name="integrate_slack"),
    path("integrate/shopify/", views.integrate_shopify, name="integrate_shopify"),

    # Legacy API endpoints (working views)
    path("api/auth/slack/", views.slack_auth, name="slack_auth"),
    path("api/auth/slack/callback/", views.slack_auth_callback, name="slack_auth_callback"),
    path("api/connect/slack/", views.slack_connect, name="slack_connect"),
    path("api/connect/slack/callback/", views.slack_connect_callback, name="slack_connect_callback"),
    path("api/connect/shopify/", views.connect_shopify, name="connect_shopify"),
    path("api/connect/stripe/", views.connect_stripe, name="connect_stripe"),
    path(
        "api/notification-settings/",
        views.get_notification_settings,
        name="get_notification_settings",
    ),
    path(
        "api/notification-settings/update/",
        views.update_notification_settings,
        name="update_notification_settings",
    ),
]
