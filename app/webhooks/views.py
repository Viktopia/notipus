import logging

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .providers.base import InvalidDataError

logger = logging.getLogger(__name__)


@require_http_methods(["POST"])
def shopify_webhook(request):
    """Handle Shopify webhooks"""
    try:
        provider = settings.SHOPIFY_PROVIDER

        # Validate webhook
        if not provider.validate_webhook(request):
            return JsonResponse({"error": "Invalid webhook signature"}, status=401)

        # Parse webhook data
        event_data = provider.parse_webhook(request)
        if not event_data:
            return JsonResponse(
                {"status": "success", "message": "Test webhook received"}, status=200
            )

        # Get customer data
        customer_data = provider.get_customer_data(event_data["customer_id"])

        # Format notification
        notification = settings.EVENT_PROCESSOR.format_notification(
            event_data, customer_data
        )

        # Send to Slack
        settings.SLACK_CLIENT.send_notification(notification)

        return JsonResponse(
            {"status": "success", "message": "Webhook processed successfully"},
            status=200,
        )

    except InvalidDataError as e:
        logger.warning("Invalid webhook data", exc_info=True)
        return JsonResponse({"error": str(e)}, status=400)
    except Exception as e:
        logger.error("Server error in Shopify webhook", exc_info=True)
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def chargify_webhook(request):
    """Handle Chargify webhooks"""
    try:
        provider = settings.CHARGIFY_PROVIDER

        # Log webhook data for debugging
        logger.info(
            "Parsing Chargify webhook data",
            extra={
                "content_type": request.content_type,
                "form_data": request.POST.dict(),
                "headers": dict(request.headers),
            },
        )

        # Validate webhook
        if not provider.validate_webhook(request):
            return JsonResponse({"error": "Invalid webhook signature"}, status=401)

        # Parse webhook data
        event_data = provider.parse_webhook(request)
        if not event_data:
            return JsonResponse(
                {"status": "success", "message": "Test webhook received"}, status=200
            )

        # Get customer data
        customer_data = provider.get_customer_data(event_data["customer_id"])

        # Format notification
        notification = settings.EVENT_PROCESSOR.format_notification(
            event_data, customer_data
        )

        # Send to Slack
        settings.SLACK_CLIENT.send_notification(notification)

        return JsonResponse(
            {"status": "success", "message": "Webhook processed successfully"},
            status=200,
        )

    except InvalidDataError as e:
        logger.warning("Invalid webhook data", exc_info=True)
        return JsonResponse({"error": str(e)}, status=400)
    except Exception as e:
        logger.error("Server error in Chargify webhook", exc_info=True)
        return JsonResponse({"error": str(e)}, status=500)


@require_http_methods(["GET"])
def health_check(request):
    """Health check endpoint"""
    return JsonResponse({"status": "healthy"}, status=200)
