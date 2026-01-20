"""Notification settings views.

This module handles notification preference management.
"""

import json
import logging
from typing import Any

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, JsonResponse

from ..models import NotificationSettings, UserProfile

logger = logging.getLogger(__name__)


@login_required
def get_notification_settings(request: HttpRequest) -> JsonResponse:
    """Get notification settings for the user's organization.

    Args:
        request: The HTTP request object.

    Returns:
        JSON response with notification settings or error.
    """
    try:
        user_profile = UserProfile.objects.get(user=request.user)
        organization = user_profile.organization
        settings_obj, created = NotificationSettings.objects.get_or_create(
            organization=organization
        )

        settings_data: dict[str, bool] = {
            "notify_payment_success": settings_obj.notify_payment_success,
            "notify_payment_failure": settings_obj.notify_payment_failure,
            "notify_subscription_created": settings_obj.notify_subscription_created,
            "notify_subscription_updated": settings_obj.notify_subscription_updated,
            "notify_subscription_canceled": settings_obj.notify_subscription_canceled,
            "notify_trial_ending": settings_obj.notify_trial_ending,
            "notify_trial_expired": settings_obj.notify_trial_expired,
            "notify_customer_updated": settings_obj.notify_customer_updated,
            "notify_signups": settings_obj.notify_signups,
            "notify_shopify_order_created": settings_obj.notify_shopify_order_created,
            "notify_shopify_order_updated": settings_obj.notify_shopify_order_updated,
            "notify_shopify_order_paid": settings_obj.notify_shopify_order_paid,
        }

        return JsonResponse(settings_data)

    except UserProfile.DoesNotExist:
        return JsonResponse({"error": "User profile not found"}, status=404)
    except Exception:
        logger.exception("Error retrieving notification settings")
        return JsonResponse({"error": "An internal error occurred"}, status=500)


@login_required
def update_notification_settings(request: HttpRequest) -> JsonResponse:
    """Update notification settings for the user's organization.

    Args:
        request: The HTTP request object.

    Returns:
        JSON response with success status or error.
    """
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        user_profile = UserProfile.objects.get(user=request.user)
        organization = user_profile.organization
        settings_obj, created = NotificationSettings.objects.get_or_create(
            organization=organization
        )

        data: dict[str, Any] = json.loads(request.body)

        # Update settings
        for field, value in data.items():
            if hasattr(settings_obj, field) and isinstance(value, bool):
                setattr(settings_obj, field, value)

        settings_obj.save()

        return JsonResponse({"success": True})

    except UserProfile.DoesNotExist:
        return JsonResponse({"error": "User profile not found"}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON data"}, status=400)
    except Exception:
        logger.exception("Error updating notification settings")
        return JsonResponse({"error": "An internal error occurred"}, status=500)
