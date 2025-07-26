from django.urls import path, re_path

from . import webhook_router

app_name = "webhooks"

urlpatterns = [
    # Health check
    path("health/", webhook_router.health_check, name="health_check"),
    # Customer payment webhooks (organization-specific with UUID obfuscation)
    re_path(
        r"^customer/(?P<organization_uuid>[0-9a-f-]+)/shopify/$",
        webhook_router.customer_shopify_webhook,
        name="customer_shopify_webhook",
    ),
    re_path(
        r"^customer/(?P<organization_uuid>[0-9a-f-]+)/chargify/$",
        webhook_router.customer_chargify_webhook,
        name="customer_chargify_webhook",
    ),
    re_path(
        r"^customer/(?P<organization_uuid>[0-9a-f-]+)/stripe/$",
        webhook_router.customer_stripe_webhook,
        name="customer_stripe_webhook",
    ),
    # Global billing webhooks (Notipus revenue)
    path(
        "billing/stripe/",
        webhook_router.billing_stripe_webhook,
        name="billing_stripe_webhook",
    ),
    # Legacy webhook endpoints (no organization-specific credentials)
    path("shopify/", webhook_router.shopify_webhook, name="shopify_webhook"),
    path("chargify/", webhook_router.chargify_webhook, name="chargify_webhook"),
    path("stripe/", webhook_router.stripe_webhook, name="stripe_webhook"),
    path("ephemeral/", webhook_router.ephemeral_webhook, name="ephemeral_webhook"),
]
