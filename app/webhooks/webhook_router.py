import logging
from typing import Any, Dict, Optional

from core.models import Integration, Workspace
from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .exceptions import WebhookError, WebhookSignatureError
from .services.rate_limiter import RateLimitException, rate_limiter

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


def _handle_rate_limiting(workspace: Workspace) -> Optional[JsonResponse]:
    """
    Handle rate limiting for workspace.
    Returns response if rate limited, None otherwise.
    """
    if not workspace:
        return None

    try:
        rate_limit_info = rate_limiter.enforce_rate_limit(workspace)
        logger.info(
            f"Rate limit check passed for workspace {workspace.uuid}: "
            f"{rate_limit_info['current_usage']}/{rate_limit_info['limit']}"
        )
        return None  # No rate limiting
    except RateLimitException as e:
        logger.warning(f"Rate limit exceeded for workspace {workspace.uuid}: {str(e)}")
        error_response = create_error_response(e, 429)
        response = JsonResponse(error_response, status=429)

        # Add rate limit headers
        rate_limit_headers = rate_limiter.get_rate_limit_headers(
            {
                "limit": e.limit,
                "current_usage": e.current_usage,
                "remaining": 0,
                "reset_time": e.reset_time,
                "plan": workspace.subscription_plan,
            }
        )
        for header_name, header_value in rate_limit_headers.items():
            response[header_name] = header_value

        return response


def _validate_and_parse_webhook(
    request: HttpRequest, provider: Any
) -> Optional[Dict[str, Any]]:
    """Validate and parse webhook. Returns None for test webhooks."""
    if not provider.validate_webhook(request):
        raise WebhookSignatureError()

    event_data = provider.parse_webhook(request)
    return event_data


def _add_rate_limit_headers(
    response: JsonResponse, rate_limit_info: Optional[Dict[str, Any]]
) -> None:
    """Add rate limit headers to response if rate_limit_info is provided."""
    if rate_limit_info:
        rate_limit_headers = rate_limiter.get_rate_limit_headers(rate_limit_info)
        for header_name, header_value in rate_limit_headers.items():
            response[header_name] = header_value


def _get_slack_webhook_url(workspace: Optional[Workspace]) -> Optional[str]:
    """Get Slack webhook URL for a workspace."""
    if not workspace:
        return None

    try:
        slack_integration = Integration.objects.get(
            workspace=workspace,
            integration_type="slack_notifications",
            is_active=True,
        )
        # Get webhook URL from incoming_webhook in oauth_credentials
        incoming_webhook = slack_integration.oauth_credentials.get(
            "incoming_webhook", {}
        )
        return incoming_webhook.get("url")
    except Integration.DoesNotExist:
        logger.warning(
            f"No active Slack integration found for workspace {workspace.uuid}"
        )
        return None


def _process_webhook_data(
    event_data: Dict[str, Any],
    provider: Any,
    provider_name: str,
    workspace: Optional[Workspace] = None,
) -> JsonResponse:
    """Process webhook data and return success response."""
    from .services.slack_client import SlackClient

    # Get customer data
    customer_data = provider.get_customer_data(event_data["customer_id"])

    # Format notification
    notification = settings.EVENT_PROCESSOR.format_notification(
        event_data, customer_data
    )

    # Send to Slack using workspace-specific integration
    slack_webhook_url = _get_slack_webhook_url(workspace)

    if slack_webhook_url:
        slack_client = SlackClient(webhook_url=slack_webhook_url)
        try:
            slack_client.send_notification(notification)
        except Exception as e:
            logger.error(
                f"Failed to send Slack notification for workspace "
                f"{workspace.uuid if workspace else 'unknown'}: {str(e)}"
            )
            # Continue processing even if Slack notification fails
    else:
        logger.warning(
            f"No Slack webhook URL configured for workspace "
            f"{workspace.uuid if workspace else 'unknown'}, "
            f"skipping notification"
        )

    return JsonResponse(
        create_success_response(f"{provider_name} webhook processed successfully"),
        status=200,
    )


def _handle_webhook_exceptions(e: Exception, provider_name: str) -> JsonResponse:
    """Handle different types of webhook exceptions."""
    if isinstance(e, WebhookSignatureError):
        logger.warning(f"Invalid signature for {provider_name} webhook")
        error_response = create_error_response(e, 400)
        return JsonResponse(error_response, status=400)
    elif isinstance(e, WebhookError):
        logger.warning(f"Webhook validation error for {provider_name}: {str(e)}")
        error_response = create_error_response(e, 400)
        return JsonResponse(error_response, status=400)
    else:
        logger.error(f"Unexpected error in {provider_name} webhook", exc_info=True)
        error_response = create_error_response(e, 500)
        return JsonResponse(error_response, status=500)


def _process_webhook(
    request: HttpRequest,
    provider: Any,
    provider_name: str,
    workspace: Workspace = None,
) -> JsonResponse:
    """
    Common webhook processing logic with standardized error handling
    and rate limiting.

    Uses workspace-specific Slack integration for notifications.
    """
    try:
        # Handle rate limiting
        rate_limit_response = _handle_rate_limiting(workspace)
        if rate_limit_response:
            return rate_limit_response

        # Get rate limit info for headers
        rate_limit_info = None
        if workspace:
            rate_limit_info = rate_limiter.enforce_rate_limit(workspace)

        # Validate and parse webhook
        event_data = _validate_and_parse_webhook(request, provider)

        # Handle test webhooks
        if not event_data:
            response = JsonResponse(
                create_success_response("Test webhook received"), status=200
            )
            _add_rate_limit_headers(response, rate_limit_info)
            return response

        # Process webhook data with workspace for Slack notifications
        response = _process_webhook_data(event_data, provider, provider_name, workspace)
        _add_rate_limit_headers(response, rate_limit_info)
        return response

    except Exception as e:
        return _handle_webhook_exceptions(e, provider_name)


@csrf_exempt
@require_http_methods(["GET"])
def health_check(request: HttpRequest) -> JsonResponse:
    """Health check endpoint"""
    return JsonResponse({"status": "healthy", "service": "webhook-processor"})


# Legacy webhook endpoints removed to enforce multi-tenancy
# All webhooks must now use organization-specific endpoints:
# - /webhook/customer/{uuid}/shopify/
# - /webhook/customer/{uuid}/chargify/
# - /webhook/customer/{uuid}/stripe/
# - /webhook/billing/stripe/ (for Notipus billing only)


# === CUSTOMER-SPECIFIC WEBHOOKS ===


@csrf_exempt
@require_http_methods(["POST"])
def customer_shopify_webhook(
    request: HttpRequest, organization_uuid: str
) -> JsonResponse:
    """Handle customer-specific Shopify webhook requests with rate limiting"""
    logger.info(
        f"Processing customer Shopify webhook for workspace {organization_uuid}",
        extra={
            "content_type": request.content_type,
            "workspace_uuid": organization_uuid,
        },
    )

    try:
        # Get workspace for rate limiting
        workspace = get_object_or_404(Workspace, uuid=organization_uuid)

        # Get workspace's Shopify integration
        integration = get_object_or_404(
            Integration,
            workspace=workspace,
            integration_type="shopify",
            is_active=True,
        )

        from .providers.shopify import ShopifyProvider

        provider = ShopifyProvider(webhook_secret=integration.webhook_secret)

        return _process_webhook(request, provider, "customer_shopify", workspace)

    except Exception as e:
        logger.error(f"Error in customer Shopify webhook: {str(e)}", exc_info=True)
        error_response = create_error_response(e, 500)
        return JsonResponse(error_response, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def customer_chargify_webhook(
    request: HttpRequest, organization_uuid: str
) -> JsonResponse:
    """Handle customer-specific Chargify/Maxio webhook requests with rate limiting"""
    logger.info(
        f"Processing customer Chargify/Maxio webhook "
        f"for workspace {organization_uuid}",
        extra={
            "workspace_uuid": organization_uuid,
            "content_type": request.content_type,
        },
    )

    try:
        # Get workspace
        workspace = Workspace.objects.get(uuid=organization_uuid)

        # Get workspace's Chargify/Maxio integration
        integration = Integration.objects.get(
            workspace=workspace, integration_type="chargify", is_active=True
        )

        from .providers.chargify import ChargifyProvider

        provider = ChargifyProvider(webhook_secret=integration.webhook_secret)

        return _process_webhook(request, provider, "customer_chargify", workspace)

    except Exception as e:
        logger.error(
            f"Error in customer Chargify/Maxio webhook: {str(e)}", exc_info=True
        )
        error_response = create_error_response(e, 500)
        return JsonResponse(error_response, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def customer_stripe_webhook(
    request: HttpRequest, organization_uuid: str
) -> JsonResponse:
    """Handle customer-specific Stripe webhook requests with rate limiting"""
    logger.info(
        f"Processing customer Stripe webhook for workspace {organization_uuid}",
        extra={
            "content_type": request.content_type,
            "workspace_uuid": organization_uuid,
        },
    )

    try:
        # Get workspace for rate limiting
        workspace = get_object_or_404(Workspace, uuid=organization_uuid)

        # Get workspace's Stripe integration
        integration = get_object_or_404(
            Integration,
            workspace=workspace,
            integration_type="stripe_customer",
            is_active=True,
        )

        from .providers.stripe import StripeProvider

        provider = StripeProvider(webhook_secret=integration.webhook_secret)

        return _process_webhook(request, provider, "customer_stripe", workspace)

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
        extra={"content_type": request.content_type},
    )

    try:
        from core.models import GlobalBillingIntegration

        from .providers.stripe import StripeProvider

        billing_integration = get_object_or_404(
            GlobalBillingIntegration, integration_type="stripe_billing", is_active=True
        )

        provider = StripeProvider(webhook_secret=billing_integration.webhook_secret)

        return _process_webhook(request, provider, "billing_stripe")

    except Exception as e:
        logger.error(f"Error in billing Stripe webhook: {str(e)}", exc_info=True)
        error_response = create_error_response(e, 500)
        return JsonResponse(error_response, status=500)
