import logging
import uuid
from typing import Any

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .exceptions import (
    WebhookError,
    WebhookSignatureError,
    create_error_response,
    create_success_response,
)

logger = logging.getLogger(__name__)


@require_http_methods(["GET"])
def health_check(request: HttpRequest) -> JsonResponse:
    """Health check endpoint for webhook service"""
    try:
        if settings.SLACK_CLIENT:
            settings.SLACK_CLIENT.send_message({"text": "health_check"})
        return JsonResponse(create_success_response("Health check passed"))
    except Exception as e:
        error_response = create_error_response(e, 500)
        return JsonResponse(error_response, status=500)


def _process_webhook(
    request: HttpRequest, provider: Any, provider_name: str
) -> JsonResponse:
    """Common webhook processing logic with standardized error handling"""
    try:
        # Validate webhook signature
        if not provider.validate_webhook(request):
            raise WebhookSignatureError()

        # Parse webhook data
        event_data = provider.parse_webhook(request)
        if not event_data:
            return JsonResponse(
                create_success_response("Test webhook received"), status=200
            )

        # Get customer data
        customer_data = provider.get_customer_data(event_data["customer_id"])

        # Format notification
        notification = settings.EVENT_PROCESSOR.format_notification(
            event_data, customer_data
        )

        # Send to Slack
        settings.SLACK_CLIENT.send_message(notification)

        return JsonResponse(
            create_success_response(f"{provider_name} webhook processed successfully"),
            status=200,
        )

    except WebhookSignatureError as e:
        logger.warning(f"Invalid signature for {provider_name} webhook")
        error_response = create_error_response(e, 400)
        return JsonResponse(error_response, status=400)

    except WebhookError as e:
        logger.warning(f"Webhook validation error for {provider_name}: {str(e)}")
        error_response = create_error_response(e, 400)
        return JsonResponse(error_response, status=400)

    except Exception as e:
        logger.error(f"Unexpected error in {provider_name} webhook", exc_info=True)
        error_response = create_error_response(e, 500)
        return JsonResponse(error_response, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def shopify_webhook(request: HttpRequest) -> JsonResponse:
    """Handle Shopify webhook requests"""
    logger.info(
        "Processing Shopify webhook",
        extra={"content_type": request.content_type, "headers": dict(request.headers)},
    )

    return _process_webhook(request, settings.SHOPIFY_PROVIDER, "shopify")


@csrf_exempt
@require_http_methods(["POST"])
def chargify_webhook(request: HttpRequest) -> JsonResponse:
    """Handle Chargify webhook requests"""
    logger.info(
        "Processing Chargify webhook",
        extra={"content_type": request.content_type, "headers": dict(request.headers)},
    )

    return _process_webhook(request, settings.CHARGIFY_PROVIDER, "chargify")


@csrf_exempt
@require_http_methods(["POST"])
def stripe_webhook(request: HttpRequest) -> JsonResponse:
    """Handle Stripe webhook requests"""
    logger.info(
        "Processing Stripe webhook",
        extra={"content_type": request.content_type, "headers": dict(request.headers)},
    )

    return _process_webhook(request, settings.STRIPE_PROVIDER, "stripe")


@csrf_exempt
@require_http_methods(["GET"])
def ephemeral_webhook(request: HttpRequest) -> JsonResponse:
    """Handle ephemeral webhook requests that can be from multiple providers"""
    try:
        # Determine provider based on headers
        topic = request.headers.get("X-Shopify-Topic")
        if topic is not None:
            provider = settings.SHOPIFY_PROVIDER
            provider_name = "shopify"
        else:
            signature = request.headers.get("Stripe-Signature")
            if signature is not None:
                provider = settings.STRIPE_PROVIDER
                provider_name = "stripe"
            else:
                raise WebhookError(
                    "Required provider headers missing", "MISSING_HEADERS"
                )

        logger.info(
            f"Processing ephemeral webhook for {provider_name}",
            extra={"provider": provider_name, "content_type": request.content_type},
        )

        return _process_webhook(request, provider, f"ephemeral_{provider_name}")

    except WebhookError as e:
        error_response = create_error_response(e, 400)
        return JsonResponse(error_response, status=400)

    except Exception as e:
        logger.error("Unexpected error in ephemeral webhook", exc_info=True)
        error_response = create_error_response(e, 500)
        return JsonResponse(error_response, status=500)


# === NEW CUSTOMER PAYMENT WEBHOOKS (organization-specific) ===

def _get_organization_integration(organization_uuid: uuid.UUID, integration_type: str):
    """Get organization integration for customer webhooks"""
    from core.models import Integration, Organization

    organization = get_object_or_404(Organization, uuid=organization_uuid)
    integration = get_object_or_404(
        Integration,
        organization=organization,
        integration_type=integration_type,
        is_active=True
    )
    return organization, integration


def _create_organization_provider(integration, provider_class):
    """Create provider instance with organization-specific credentials"""
    return provider_class(webhook_secret=integration.webhook_secret)


@csrf_exempt
@require_http_methods(["POST"])
def customer_shopify_webhook(request: HttpRequest, organization_uuid: uuid.UUID) -> JsonResponse:
    """Handle Shopify customer payment webhooks for a specific organization"""
    logger.info(
        "Processing customer Shopify webhook",
        extra={"organization_uuid": str(organization_uuid), "content_type": request.content_type}
    )

    try:
        organization, integration = _get_organization_integration(organization_uuid, "shopify")

        from .providers.shopify import ShopifyProvider
        provider = _create_organization_provider(integration, ShopifyProvider)

        return _process_webhook(request, provider, f"customer_shopify_{organization.id}")

    except Exception as e:
        logger.error(f"Error in customer Shopify webhook: {str(e)}", exc_info=True)
        error_response = create_error_response(e, 500)
        return JsonResponse(error_response, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def customer_chargify_webhook(request: HttpRequest, organization_uuid: uuid.UUID) -> JsonResponse:
    """Handle Chargify customer payment webhooks for a specific organization"""
    logger.info(
        "Processing customer Chargify webhook",
        extra={"organization_uuid": str(organization_uuid), "content_type": request.content_type}
    )

    try:
        organization, integration = _get_organization_integration(organization_uuid, "chargify")

        from .providers.chargify import ChargifyProvider
        provider = _create_organization_provider(integration, ChargifyProvider)

        return _process_webhook(request, provider, f"customer_chargify_{organization.id}")

    except Exception as e:
        logger.error(f"Error in customer Chargify webhook: {str(e)}", exc_info=True)
        error_response = create_error_response(e, 500)
        return JsonResponse(error_response, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def customer_stripe_webhook(request: HttpRequest, organization_uuid: uuid.UUID) -> JsonResponse:
    """Handle Stripe customer payment webhooks for a specific organization"""
    logger.info(
        "Processing customer Stripe webhook",
        extra={"organization_uuid": str(organization_uuid), "content_type": request.content_type}
    )

    try:
        organization, integration = _get_organization_integration(organization_uuid, "stripe_customer")

        from .providers.stripe import StripeProvider
        provider = _create_organization_provider(integration, StripeProvider)

        return _process_webhook(request, provider, f"customer_stripe_{organization.id}")

    except Exception as e:
        logger.error(f"Error in customer Stripe webhook: {str(e)}", exc_info=True)
        error_response = create_error_response(e, 500)
        return JsonResponse(error_response, status=500)


# === GLOBAL BILLING WEBHOOKS (Notipus revenue) ===

@csrf_exempt
@require_http_methods(["POST"])
def billing_stripe_webhook(request: HttpRequest) -> JsonResponse:
    """Handle global Stripe billing webhooks for Notipus revenue"""
    logger.info(
        "Processing global billing Stripe webhook",
        extra={"content_type": request.content_type}
    )

    try:
        from core.models import GlobalBillingIntegration

        from .providers.stripe import StripeProvider

        billing_integration = get_object_or_404(
            GlobalBillingIntegration,
            integration_type="stripe_billing",
            is_active=True
        )

        provider = StripeProvider(webhook_secret=billing_integration.webhook_secret)

        return _process_webhook(request, provider, "billing_stripe")

    except Exception as e:
        logger.error(f"Error in billing Stripe webhook: {str(e)}", exc_info=True)
        error_response = create_error_response(e, 500)
        return JsonResponse(error_response, status=500)
