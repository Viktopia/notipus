from django.http import HttpRequest, JsonResponse
from django.conf import settings
from ninja import Router
import logging

from .providers.base import InvalidDataError

logger = logging.getLogger(__name__)
webhook_router = Router()


@webhook_router.post("/webhook/shopify/")
async def shopify_webhook(request: HttpRequest):
    try:
        provider = settings.SHOPIFY_PROVIDER

        if not provider.validate_webhook(request):
            return JsonResponse({"error": "Invalid webhook signature"}, status=401)

        event_data = provider.parse_webhook(request)
        if not event_data:
            return JsonResponse(
                {"status": "success", "message": "Test webhook received"}, status=200
            )

        customer_data = provider.get_customer_data(event_data["customer_id"])

        notification = settings.EVENT_PROCESSOR.format_notification(
            event_data, customer_data
        )

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


@webhook_router.post("/webhook/chargify/")
async def chargify_webhook(request: HttpRequest):
    try:
        provider = settings.CHARGIFY_PROVIDER

        logger.info(
            "Parsing Chargify webhook data",
            extra={
                "content_type": request.content_type,
                "form_data": request.body,
                "headers": dict(request.headers),
            },
        )

        if not provider.validate_webhook(request):
            return JsonResponse({"error": "Invalid webhook signature"}, status=401)

        event_data = provider.parse_webhook(request)
        if not event_data:
            return JsonResponse(
                {"status": "success", "message": "Test webhook received"}, status=200
            )

        customer_data = provider.get_customer_data(event_data["customer_id"])

        notification = settings.EVENT_PROCESSOR.format_notification(
            event_data, customer_data
        )

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
