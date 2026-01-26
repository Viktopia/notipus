import json
import logging
from typing import Any, Dict, Optional

from core.models import Integration, Workspace
from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .exceptions import WebhookError, WebhookSignatureError
from .services.event_consolidation import event_consolidation_service
from .services.rate_limiter import RateLimitException, rate_limiter
from .services.webhook_storage import webhook_storage_service

logger = logging.getLogger(__name__)


def _log_webhook_payload(
    request: HttpRequest, provider_name: str, workspace_uuid: Optional[str] = None
) -> None:
    """
    Log the raw webhook payload for analysis when LOG_WEBHOOKS is enabled.

    This logs the complete request body and relevant headers to help with
    debugging and understanding webhook patterns from providers.
    """
    if not settings.LOG_WEBHOOKS:
        return

    try:
        # Get the raw body
        raw_body = request.body.decode("utf-8")

        # Try to parse as JSON for prettier logging
        try:
            body_data = json.loads(raw_body)
            body_str = json.dumps(body_data, indent=2, default=str)
        except (json.JSONDecodeError, TypeError):
            # Not JSON, log as-is (could be form data)
            body_str = raw_body

        # Extract relevant headers (excluding sensitive auth headers)
        relevant_headers = {
            "Content-Type": request.headers.get("Content-Type"),
            "Content-Length": request.headers.get("Content-Length"),
            "User-Agent": request.headers.get("User-Agent"),
            "X-Forwarded-For": request.headers.get("X-Forwarded-For"),
        }

        # Add provider-specific signature headers for reference
        signature_headers = [
            "X-Shopify-Hmac-SHA256",
            "Stripe-Signature",
            "X-Chargify-Webhook-Signature-Hmac-Sha-256",
        ]
        for header in signature_headers:
            if header in request.headers:
                # Log presence of signature but not the value for security
                relevant_headers[header] = "[PRESENT]"

        logger.info(
            f"WEBHOOK_LOG [{provider_name}] "
            f"workspace={workspace_uuid or 'global'} "
            f"method={request.method} path={request.path}",
            extra={
                "webhook_provider": provider_name,
                "workspace_uuid": workspace_uuid,
                "headers": relevant_headers,
                "body": body_str,
            },
        )

        # Store raw webhook in Redis for debugging (7-day retention)
        webhook_storage_service.store_webhook(request, provider_name, workspace_uuid)

    except Exception as e:
        # Don't let logging errors break webhook processing
        logger.warning(f"Failed to log webhook payload: {e}")


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
        logger.debug(
            f"No active Slack integration found for workspace {workspace.uuid}"
        )
        return None


def _get_telegram_credentials(
    workspace: Optional[Workspace],
) -> Optional[Dict[str, str]]:
    """Get Telegram credentials for a workspace.

    Returns:
        Dict with 'bot_token' and 'chat_id' if configured, None otherwise.
    """
    if not workspace:
        return None

    try:
        telegram_integration = Integration.objects.get(
            workspace=workspace,
            integration_type="telegram_notifications",
            is_active=True,
        )
        bot_token = telegram_integration.oauth_credentials.get("bot_token")
        chat_id = telegram_integration.oauth_credentials.get("chat_id")

        if bot_token and chat_id:
            return {"bot_token": bot_token, "chat_id": chat_id}
        return None
    except Integration.DoesNotExist:
        logger.debug(
            f"No active Telegram integration found for workspace {workspace.uuid}"
        )
        return None


def _send_to_slack(
    workspace: Optional[Workspace],
    notification: Any,
    registry: Any,
) -> bool:
    """Send notification to Slack if configured.

    Args:
        workspace: The workspace to send for.
        notification: RichNotification object.
        registry: PluginRegistry instance.

    Returns:
        True if sent successfully or not configured, False on error.
    """
    from plugins.base import PluginType
    from plugins.destinations.base import BaseDestinationPlugin

    slack_webhook_url = _get_slack_webhook_url(workspace)
    if not slack_webhook_url:
        return True  # Not configured is not an error

    slack_plugin = registry.get(PluginType.DESTINATION, "slack")
    if slack_plugin is None or not isinstance(slack_plugin, BaseDestinationPlugin):
        logger.error("Slack destination plugin not found or not configured")
        return False

    try:
        formatted = slack_plugin.format(notification)
        slack_plugin.send(formatted, {"webhook_url": slack_webhook_url})
        logger.debug(
            f"Sent Slack notification for workspace "
            f"{workspace.uuid if workspace else 'unknown'}"
        )
        return True
    except Exception as e:
        logger.error(
            f"Failed to send Slack notification for workspace "
            f"{workspace.uuid if workspace else 'unknown'}: {str(e)}"
        )
        return False


def _send_to_telegram(
    workspace: Optional[Workspace],
    notification: Any,
    registry: Any,
) -> bool:
    """Send notification to Telegram if configured.

    Args:
        workspace: The workspace to send for.
        notification: RichNotification object.
        registry: PluginRegistry instance.

    Returns:
        True if sent successfully or not configured, False on error.
    """
    from plugins.base import PluginType
    from plugins.destinations.base import BaseDestinationPlugin

    telegram_credentials = _get_telegram_credentials(workspace)
    if not telegram_credentials:
        return True  # Not configured is not an error

    telegram_plugin = registry.get(PluginType.DESTINATION, "telegram")
    if not telegram_plugin or not isinstance(telegram_plugin, BaseDestinationPlugin):
        logger.error("Telegram destination plugin not found or not configured")
        return False

    try:
        formatted = telegram_plugin.format(notification)
        telegram_plugin.send(formatted, telegram_credentials)
        logger.debug(
            f"Sent Telegram notification for workspace "
            f"{workspace.uuid if workspace else 'unknown'}"
        )
        return True
    except Exception as e:
        logger.error(
            f"Failed to send Telegram notification for workspace "
            f"{workspace.uuid if workspace else 'unknown'}: {str(e)}"
        )
        return False


def _process_webhook_data(
    event_data: Dict[str, Any],
    provider: Any,
    provider_name: str,
    workspace: Optional[Workspace] = None,
) -> JsonResponse:
    """Process webhook data and return success response.

    Includes event consolidation to prevent notification spam when
    multiple related events fire in quick succession.

    Sends notifications to all configured destinations (Slack, Telegram).
    Each destination operates independently - failure in one doesn't block others.
    """
    from plugins.registry import PluginRegistry

    # Get customer data from webhook payload
    # (We can't call provider APIs - we only have the webhook data)
    customer_data = provider.get_customer_data(event_data["customer_id"])

    # Check event consolidation - should we send a notification?
    event_type = event_data.get("type", "")
    customer_id = event_data.get("customer_id", "")
    workspace_id = str(workspace.uuid) if workspace else ""
    external_id = event_data.get("external_id", "")
    idempotency_key = event_data.get("idempotency_key")

    # Check for idempotency-based duplicate (same Stripe API request)
    # This catches multiple events from the same action (e.g., subscription.created
    # and invoice.paid from the same subscription creation)
    if event_consolidation_service.is_duplicate_by_idempotency(
        workspace_id, idempotency_key
    ):
        logger.info(
            f"Skipping event {event_type} with idempotency key {idempotency_key} "
            f"for workspace {workspace_id} (already processed different event "
            f"from same action)"
        )
        return JsonResponse(
            create_success_response(
                f"{provider_name} webhook processed (idempotency duplicate)"
            ),
            status=200,
        )

    # Check for exact duplicate (same external_id)
    if event_consolidation_service.is_duplicate(workspace_id, external_id):
        logger.info(
            f"Skipping duplicate event {external_id} for workspace {workspace_id}"
        )
        return JsonResponse(
            create_success_response(
                f"{provider_name} webhook processed (duplicate suppressed)"
            ),
            status=200,
        )

    # Check if this event should be suppressed due to consolidation
    # Pass amount to filter out $0 payment events (trial invoices)
    should_notify = event_consolidation_service.should_send_notification(
        event_type=event_type,
        customer_id=customer_id,
        workspace_id=workspace_id,
        amount=event_data.get("amount"),
    )

    if not should_notify:
        # Record the event for deduplication, but don't send notification
        event_consolidation_service.record_event(
            event_type=event_type,
            customer_id=customer_id,
            workspace_id=workspace_id,
            external_id=external_id,
        )
        # Also record idempotency key to suppress related events
        event_consolidation_service.record_idempotency_key(
            workspace_id, idempotency_key
        )
        return JsonResponse(
            create_success_response(
                f"{provider_name} webhook processed (consolidated)"
            ),
            status=200,
        )

    # Build rich notification once (target-agnostic)
    notification = settings.EVENT_PROCESSOR.build_rich_notification(
        event_data, customer_data
    )

    # Get plugin registry for destination lookups
    registry = PluginRegistry.instance()

    # Send to all configured destinations
    # Each destination operates independently - failure in one doesn't block others
    slack_sent = _send_to_slack(workspace, notification, registry)
    telegram_sent = _send_to_telegram(workspace, notification, registry)

    # Check if at least one destination was configured
    slack_configured = _get_slack_webhook_url(workspace) is not None
    telegram_configured = _get_telegram_credentials(workspace) is not None

    if not slack_configured and not telegram_configured:
        logger.warning(
            f"No notification destinations configured for workspace "
            f"{workspace.uuid if workspace else 'unknown'}"
        )
    else:
        # Record the event after attempting to send
        # (even if some destinations failed, we don't want to retry)
        event_consolidation_service.record_event(
            event_type=event_type,
            customer_id=customer_id,
            workspace_id=workspace_id,
            external_id=external_id,
        )
        # Record idempotency key to suppress related events from same action
        event_consolidation_service.record_idempotency_key(
            workspace_id, idempotency_key
        )

    # Log summary of send results
    if slack_configured or telegram_configured:
        destinations_summary = []
        if slack_configured:
            destinations_summary.append(f"Slack={'ok' if slack_sent else 'failed'}")
        if telegram_configured:
            destinations_summary.append(
                f"Telegram={'ok' if telegram_sent else 'failed'}"
            )
        summary = ", ".join(destinations_summary)
        logger.info(f"Notification dispatch for {provider_name}: {summary}")

    return JsonResponse(
        create_success_response(f"{provider_name} webhook processed successfully"),
        status=200,
    )


def _handle_webhook_exceptions(e: Exception, provider_name: str) -> JsonResponse:
    """Handle different types of webhook exceptions."""
    from webhooks.services.rate_limiter import RateLimitException

    if isinstance(e, WebhookSignatureError):
        logger.warning(f"Invalid signature for {provider_name} webhook")
        error_response = create_error_response(e, 400)
        return JsonResponse(error_response, status=400)
    elif isinstance(e, RateLimitException):
        # Rate limiting is expected behavior, not an error
        logger.info(f"Rate limit exceeded for {provider_name} webhook: {e!s}")
        error_response = create_error_response(e, 429)
        return JsonResponse(error_response, status=429)
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
    # Log raw webhook payload before any processing
    _log_webhook_payload(request, "shopify", organization_uuid)

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

        from plugins.sources.shopify import ShopifySourcePlugin

        provider = ShopifySourcePlugin(webhook_secret=integration.webhook_secret)

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
    # Log raw webhook payload before any processing
    _log_webhook_payload(request, "chargify", organization_uuid)

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

        from plugins.sources.chargify import ChargifySourcePlugin

        provider = ChargifySourcePlugin(webhook_secret=integration.webhook_secret)

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
    # Log raw webhook payload before any processing
    _log_webhook_payload(request, "stripe", organization_uuid)

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

        from plugins.sources.stripe import StripeSourcePlugin

        provider = StripeSourcePlugin(webhook_secret=integration.webhook_secret)

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
    # Log raw webhook payload before any processing
    _log_webhook_payload(request, "stripe_billing")

    logger.info(
        "Processing global billing Stripe webhook",
        extra={"content_type": request.content_type},
    )

    try:
        from core.models import GlobalBillingIntegration
        from plugins.sources.stripe import StripeSourcePlugin

        billing_integration = GlobalBillingIntegration.objects.filter(
            integration_type="stripe_billing", is_active=True
        ).first()

        if not billing_integration:
            # Return 200 to acknowledge receipt - don't trigger Stripe retries
            # Log error so we know configuration is missing
            logger.error(
                "GlobalBillingIntegration not configured for stripe_billing. "
                "Create record with integration_type='stripe_billing', is_active=True."
            )
            return JsonResponse(
                {"status": "error", "message": "Billing integration not configured"},
                status=200,  # 200 to prevent Stripe retries
            )

        provider = StripeSourcePlugin(webhook_secret=billing_integration.webhook_secret)

        return _process_webhook(request, provider, "billing_stripe")

    except Exception as e:
        logger.error(f"Error in billing Stripe webhook: {str(e)}", exc_info=True)
        # Return 200 to acknowledge receipt - prevents infinite retries
        return JsonResponse(
            {"status": "error", "message": "Internal error processing webhook"},
            status=200,
        )
