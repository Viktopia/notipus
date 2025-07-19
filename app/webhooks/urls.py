from django.urls import path

from . import webhook_router

urlpatterns = [
    path(
        "webhook/health_check/",
        webhook_router.health_check,
        name="webhook_health_check",
    ),
    path(
        "webhook/shopify/",
        webhook_router.shopify_webhook,
        name="shopify_webhook",
    ),
    path(
        "webhook/chargify/",
        webhook_router.chargify_webhook,
        name="chargify_webhook",
    ),
    path(
        "webhook/stripe/",
        webhook_router.stripe_webhook,
        name="stripe_webhook",
    ),
    path(
        "webhook/ephemeral/",
        webhook_router.ephemeral_webhook,
        name="ephemeral_webhook",
    ),
]
