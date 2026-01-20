"""Core views package.

This package organizes views into logical modules for better maintainability.
"""

from .auth import (
    home,
    landing,
    slack_auth,
    slack_auth_callback,
)
from .billing import (
    billing_dashboard,
    billing_history,
    billing_portal,
    checkout,
    checkout_cancel,
    checkout_success,
    payment_methods,
    plan_selected,
    select_plan,
    upgrade_plan,
)
from .dashboard import (
    create_organization,
    dashboard,
    organization_settings,
)
from .integrations import (
    connect_shopify,
    connect_stripe,
    integrate_chargify,
    integrate_shopify,
    integrate_slack,
    integrations,
    slack_connect,
    slack_connect_callback,
)
from .settings import (
    get_notification_settings,
    update_notification_settings,
)
from .webauthn import (
    webauthn_authenticate_begin,
    webauthn_authenticate_complete,
    webauthn_credentials,
    webauthn_register_begin,
    webauthn_register_complete,
    webauthn_signup_begin,
    webauthn_signup_complete,
)

__all__ = [
    # Auth
    "home",
    "landing",
    "slack_auth",
    "slack_auth_callback",
    # Dashboard
    "dashboard",
    "create_organization",
    "organization_settings",
    # Integrations
    "integrations",
    "integrate_slack",
    "integrate_shopify",
    "integrate_chargify",
    "slack_connect",
    "slack_connect_callback",
    "connect_shopify",
    "connect_stripe",
    # Settings
    "get_notification_settings",
    "update_notification_settings",
    # Billing
    "select_plan",
    "plan_selected",
    "billing_dashboard",
    "billing_portal",
    "upgrade_plan",
    "payment_methods",
    "billing_history",
    "checkout",
    "checkout_success",
    "checkout_cancel",
    # WebAuthn
    "webauthn_register_begin",
    "webauthn_register_complete",
    "webauthn_authenticate_begin",
    "webauthn_authenticate_complete",
    "webauthn_credentials",
    "webauthn_signup_begin",
    "webauthn_signup_complete",
]
