"""Webhook models package.

Exports notification-related models for webhook processing.
"""

from .notification import Notification, Section
from .rich_notification import (
    EVENT_CATEGORY_MAP,
    ActionButton,
    CompanyInfo,
    CustomerInfo,
    DetailField,
    DetailSection,
    EventCategory,
    InsightInfo,
    NotificationSeverity,
    NotificationType,
    PaymentInfo,
    RichNotification,
)

__all__ = [
    # Legacy notification models
    "Notification",
    "Section",
    # New multi-target notification models
    "ActionButton",
    "CompanyInfo",
    "CustomerInfo",
    "DetailField",
    "DetailSection",
    "EVENT_CATEGORY_MAP",
    "EventCategory",
    "InsightInfo",
    "NotificationSeverity",
    "NotificationType",
    "PaymentInfo",
    "RichNotification",
]
