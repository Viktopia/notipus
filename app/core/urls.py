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
    # Billing management
    path("billing/", views.billing_dashboard, name="billing_dashboard"),
    path("billing/portal/", views.billing_portal, name="billing_portal"),
    path("billing/upgrade/", views.upgrade_plan, name="upgrade_plan"),
    path("billing/payment-methods/", views.payment_methods, name="payment_methods"),
    path("billing/history/", views.billing_history, name="billing_history"),
    path("billing/checkout/<str:plan_name>/", views.checkout, name="checkout"),
    path("billing/checkout/success/", views.checkout_success, name="checkout_success"),
    path("billing/checkout/cancel/", views.checkout_cancel, name="checkout_cancel"),
    # Organization management
    path("organization/create/", views.create_organization, name="create_organization"),
    path(
        "organization/settings/",
        views.organization_settings,
        name="organization_settings",
    ),
    # OAuth integrations (to be implemented)
    path("integrations/", views.integrations, name="integrations"),
    path("integrate/slack/", views.integrate_slack, name="integrate_slack"),
    path("integrate/shopify/", views.integrate_shopify, name="integrate_shopify"),
    path("integrate/chargify/", views.integrate_chargify, name="integrate_chargify"),
    path("integrate/stripe/", views.integrate_stripe, name="integrate_stripe"),
    # Legacy API endpoints (working views)
    path("api/auth/slack/", views.slack_auth, name="slack_auth"),
    path(
        "api/auth/slack/callback/",
        views.slack_auth_callback,
        name="slack_auth_callback",
    ),
    path("api/connect/slack/", views.slack_connect, name="slack_connect"),
    path(
        "api/connect/slack/callback/",
        views.slack_connect_callback,
        name="slack_connect_callback",
    ),
    path(
        "api/disconnect/slack/",
        views.disconnect_slack,
        name="disconnect_slack",
    ),
    path(
        "api/test/slack/",
        views.test_slack,
        name="test_slack",
    ),
    path(
        "api/slack/channels/",
        views.get_slack_channels,
        name="get_slack_channels",
    ),
    path(
        "api/slack/configure/",
        views.configure_slack,
        name="configure_slack",
    ),
    path("api/connect/stripe/", views.stripe_connect, name="stripe_connect"),
    path(
        "api/connect/stripe/callback/",
        views.stripe_connect_callback,
        name="stripe_connect_callback",
    ),
    path(
        "api/disconnect/stripe/",
        views.disconnect_stripe,
        name="disconnect_stripe",
    ),
    # WebAuthn endpoints
    path(
        "webauthn/register/begin/",
        views.webauthn_register_begin,
        name="webauthn_register_begin",
    ),
    path(
        "webauthn/register/complete/",
        views.webauthn_register_complete,
        name="webauthn_register_complete",
    ),
    path(
        "webauthn/authenticate/begin/",
        views.webauthn_authenticate_begin,
        name="webauthn_authenticate_begin",
    ),
    path(
        "webauthn/authenticate/complete/",
        views.webauthn_authenticate_complete,
        name="webauthn_authenticate_complete",
    ),
    path(
        "webauthn/credentials/",
        views.webauthn_credentials,
        name="webauthn_credentials",
    ),
    # WebAuthn signup endpoints (passwordless registration)
    path(
        "webauthn/signup/begin/",
        views.webauthn_signup_begin,
        name="webauthn_signup_begin",
    ),
    path(
        "webauthn/signup/complete/",
        views.webauthn_signup_complete,
        name="webauthn_signup_complete",
    ),
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
