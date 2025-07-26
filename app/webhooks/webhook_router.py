import logging
import uuid
from typing import Any

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from core.models import Integration, Organization
from .exceptions import WebhookError, WebhookSignatureError
from .services.rate_limiter import rate_limiter, RateLimitException

logger = logging.getLogger(__name__)


def create_success_response(message: str) -> dict:
    """Create standardized success response"""
    return {"status": "success", "message": message}


def create_error_response(error: Exception, status_code: int = 500) -> dict:
    """Create standardized error response"""
    return {
        "status": "error",
        "error": type(error).__name__,
        "message": str(error),
        "code": status_code,
    }


def _process_webhook(
    request: HttpRequest, provider: Any, provider_name: str, organization: Organization = None
) -> JsonResponse:
    """Common webhook processing logic with standardized error handling and rate limiting"""
    try:
        # Apply rate limiting if organization is provided
        rate_limit_info = None
        if organization:
            try:
                rate_limit_info = rate_limiter.enforce_rate_limit(organization)
                logger.info(f"Rate limit check passed for org {organization.uuid}: {rate_limit_info['current_usage']}/{rate_limit_info['limit']}")
            except RateLimitException as e:
                logger.warning(f"Rate limit exceeded for org {organization.uuid}: {str(e)}")
                error_response = create_error_response(e, 429)
                response = JsonResponse(error_response, status=429)

                # Add rate limit headers
                rate_limit_headers = rate_limiter.get_rate_limit_headers({
                    "limit": e.limit,
                    "current_usage": e.current_usage,
                    "remaining": 0,
                    "reset_time": e.reset_time,
                    "plan": organization.subscription_plan,
                })
                for header_name, header_value in rate_limit_headers.items():
                    response[header_name] = header_value

                return response

        # Validate webhook signature
        if not provider.validate_webhook(request):
            raise WebhookSignatureError()

        # Parse webhook data
        event_data = provider.parse_webhook(request)
        if not event_data:
            response = JsonResponse(
                create_success_response("Test webhook received"), status=200
            )
            # Add rate limit headers to successful responses
            if rate_limit_info:
                rate_limit_headers = rate_limiter.get_rate_limit_headers(rate_limit_info)
                for header_name, header_value in rate_limit_headers.items():
                    response[header_name] = header_value
            return response

        # Get customer data
        customer_data = provider.get_customer_data(event_data["customer_id"])

        # Format notification
        notification = settings.EVENT_PROCESSOR.format_notification(
            event_data, customer_data
        )

        # Send to Slack
        settings.SLACK_CLIENT.send_message(notification)

        response = JsonResponse(
            create_success_response(f"{provider_name} webhook processed successfully"),
            status=200,
        )

        # Add rate limit headers to successful responses
        if rate_limit_info:
            rate_limit_headers = rate_limiter.get_rate_limit_headers(rate_limit_info)
            for header_name, header_value in rate_limit_headers.items():
                response[header_name] = header_value

        return response

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
@require_http_methods(["GET"])
def health_check(request: HttpRequest) -> JsonResponse:
    """Health check endpoint"""
    return JsonResponse({"status": "healthy", "service": "webhook-processor"})


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
    """Handle Chargify/Maxio webhook requests"""
    logger.info(
        "Processing Chargify/Maxio webhook",
        extra={
            "http_method": request.method,
            "content_type": request.content_type,
        },
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


# === CUSTOMER-SPECIFIC WEBHOOKS ===

@csrf_exempt
@require_http_methods(["POST"])
def customer_shopify_webhook(request: HttpRequest, organization_uuid: str) -> JsonResponse:
    """Handle customer-specific Shopify webhook requests with rate limiting"""
    logger.info(
        f"Processing customer Shopify webhook for organization {organization_uuid}",
        extra={"content_type": request.content_type, "organization_uuid": organization_uuid},
    )

    try:
        # Get organization for rate limiting
        organization = get_object_or_404(Organization, uuid=organization_uuid)

        # Get organization's Shopify integration
        integration = get_object_or_404(
            Integration,
            organization=organization,
            integration_type="shopify",
            is_active=True
        )

        from .providers.shopify import ShopifyProvider
        provider = ShopifyProvider(webhook_secret=integration.webhook_secret)

        return _process_webhook(request, provider, "customer_shopify", organization)

    except Exception as e:
        logger.error(f"Error in customer Shopify webhook: {str(e)}", exc_info=True)
        error_response = create_error_response(e, 500)
        return JsonResponse(error_response, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def customer_chargify_webhook(request: HttpRequest, organization_uuid: str) -> JsonResponse:
    """Handle customer-specific Chargify/Maxio webhook requests with rate limiting"""
    logger.info(
        f"Processing customer Chargify/Maxio webhook for organization {organization_uuid}",
        extra={
            "organization_uuid": organization_uuid,
            "http_method": request.method,
        },
    )

    try:
        # Get organization
        organization = Organization.objects.get(uuid=organization_uuid)

        # Get organization's Chargify/Maxio integration
        integration = Integration.objects.get(
            organization=organization,
            integration_type="chargify",
            is_active=True
        )

        from .providers.chargify import ChargifyProvider
        provider = ChargifyProvider(webhook_secret=integration.webhook_secret)

        return _process_webhook(request, provider, "customer_chargify", organization)

    except Exception as e:
        logger.error(f"Error in customer Chargify/Maxio webhook: {str(e)}", exc_info=True)
        error_response = create_error_response(e, 500)
        return JsonResponse(error_response, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def customer_stripe_webhook(request: HttpRequest, organization_uuid: str) -> JsonResponse:
    """Handle customer-specific Stripe webhook requests with rate limiting"""
    logger.info(
        f"Processing customer Stripe webhook for organization {organization_uuid}",
        extra={"content_type": request.content_type, "organization_uuid": organization_uuid},
    )

    try:
        # Get organization for rate limiting
        organization = get_object_or_404(Organization, uuid=organization_uuid)

        # Get organization's Stripe integration
        integration = get_object_or_404(
            Integration,
            organization=organization,
            integration_type="stripe_customer",
            is_active=True
        )

        from .providers.stripe import StripeProvider
        provider = StripeProvider(webhook_secret=integration.webhook_secret)

        return _process_webhook(request, provider, "customer_stripe", organization)

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
