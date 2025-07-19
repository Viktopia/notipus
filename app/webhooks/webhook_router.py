import logging
from typing import Any

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from ninja import Router

from .exceptions import (
    WebhookError,
    WebhookSignatureError,
    create_error_response,
    create_success_response,
)

logger = logging.getLogger(__name__)
webhook_router = Router()


@webhook_router.get("/webhook/health_check/")
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
        if settings.SLACK_CLIENT:
            settings.SLACK_CLIENT.send_notification(notification)

        return JsonResponse(
            create_success_response("Webhook processed successfully"), status=200
        )

    except WebhookError as e:
        # Known webhook errors - safe to expose
        error_response = create_error_response(e, 400)
        return JsonResponse(error_response, status=400)

    except Exception as e:
        # Unexpected errors - don't expose details
        logger.error(
            f"Unexpected error in {provider_name} webhook",
            extra={"provider": provider_name},
            exc_info=True,
        )
        error_response = create_error_response(e, 500)
        return JsonResponse(error_response, status=500)


@webhook_router.post("/webhook/shopify/")
async def shopify_webhook(request: HttpRequest) -> JsonResponse:
    """Handle Shopify webhook requests"""
    logger.info(
        "Processing Shopify webhook",
        extra={"content_type": request.content_type, "headers": dict(request.headers)},
    )

    return _process_webhook(request, settings.SHOPIFY_PROVIDER, "shopify")


@webhook_router.post("/webhook/chargify/")
async def chargify_webhook(request: HttpRequest) -> JsonResponse:
    """Handle Chargify webhook requests"""
    logger.info(
        "Processing Chargify webhook",
        extra={"content_type": request.content_type, "headers": dict(request.headers)},
    )

    return _process_webhook(request, settings.CHARGIFY_PROVIDER, "chargify")


@webhook_router.post("/webhook/stripe/")
async def stripe_webhook(request: HttpRequest) -> JsonResponse:
    """Handle Stripe webhook requests"""
    logger.info(
        "Processing Stripe webhook",
        extra={"content_type": request.content_type, "headers": dict(request.headers)},
    )

    return _process_webhook(request, settings.STRIPE_PROVIDER, "stripe")


@webhook_router.get("/webhook/ephemeral/")
async def ephemeral_webhook(request: HttpRequest) -> JsonResponse:
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
