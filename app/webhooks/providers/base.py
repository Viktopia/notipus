"""Base classes and exceptions for payment provider implementations.

This module defines the abstract base class for payment providers and
common exceptions used across all provider implementations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.http import HttpRequest


class WebhookValidationError(Exception):
    """Raised when webhook validation fails.

    This exception indicates that the webhook signature or payload
    could not be verified, typically due to an invalid signature or
    tampered data.
    """


class WebhookError(Exception):
    """Base class for webhook-related errors.

    All webhook-specific exceptions should inherit from this class
    to allow for unified error handling.
    """


class InvalidDataError(WebhookError):
    """Raised when webhook data is invalid or malformed.

    This exception indicates that the webhook payload does not contain
    the expected fields or has invalid data formats.
    """


class CustomerNotFoundError(WebhookError):
    """Raised when customer data cannot be found.

    This exception indicates that the customer referenced in a webhook
    could not be located in the database or external service.
    """


class APIError(Exception):
    """Raised when an external API request fails.

    This exception wraps errors from external API calls to payment
    providers or other services.
    """


class InvalidEventType(WebhookError):
    """Raised when event type is not supported.

    This exception indicates that the webhook contains an event type
    that is not recognized or handled by the provider.
    """


@dataclass(slots=True)
class CustomerData:
    """Customer information from a payment provider.

    Attributes:
        id: Unique customer identifier.
        email: Customer email address.
        name: Customer display name.
        created_at: Account creation timestamp.
        subscription_status: Current subscription state.
        subscription_id: Active subscription identifier.
        trial_end_date: When the trial period ends.
        payment_method: Payment method type/identifier.
        tags: Customer tags or labels.
    """

    id: str
    email: str
    name: str
    created_at: datetime
    subscription_status: str | None = None
    subscription_id: str | None = None
    trial_end_date: datetime | None = None
    payment_method: str | None = None
    tags: list[str] | None = None


@dataclass(slots=True)
class SubscriptionData:
    """Subscription information from a payment provider.

    Attributes:
        id: Unique subscription identifier.
        status: Current subscription status.
        plan_name: Name of the subscription plan.
        created_at: Subscription creation timestamp.
        trial_end_date: When the trial period ends.
        next_billing_date: Next scheduled billing date.
        amount: Subscription amount.
        currency: Currency code for the amount.
    """

    id: str
    status: str
    plan_name: str
    created_at: datetime
    trial_end_date: datetime | None = None
    next_billing_date: datetime | None = None
    amount: float | None = None
    currency: str | None = None


@dataclass(slots=True)
class PaymentEvent:
    """Payment event data from a provider webhook.

    Attributes:
        id: Unique event identifier.
        event_type: Type of payment event.
        customer_id: Associated customer identifier.
        amount: Payment amount.
        currency: Currency code.
        status: Payment status.
        timestamp: When the event occurred.
        subscription_id: Associated subscription if any.
        error_message: Error details for failures.
        retry_count: Number of retry attempts.
    """

    id: str
    event_type: str
    customer_id: str
    amount: float
    currency: str
    status: str
    timestamp: datetime
    subscription_id: str | None = None
    error_message: str | None = None
    retry_count: int | None = None


class PaymentProvider(ABC):
    """Abstract base class for payment provider implementations.

    Defines the interface that all payment providers must implement
    to handle webhooks and retrieve customer/payment data.

    Attributes:
        webhook_secret: Secret key for validating webhook signatures.
    """

    def __init__(self, webhook_secret: str) -> None:
        """Initialize the provider with webhook credentials.

        Args:
            webhook_secret: Secret key for webhook validation.
        """
        self.webhook_secret = webhook_secret

    @abstractmethod
    def validate_webhook(self, request: HttpRequest) -> bool:
        """Validate webhook signature and authenticity.

        Args:
            request: The incoming HTTP request containing the webhook.

        Returns:
            True if the webhook is valid, False otherwise.
        """

    @abstractmethod
    def parse_webhook(
        self, request: HttpRequest, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Parse webhook data into a standardized format.

        Args:
            request: The incoming HTTP request containing the webhook.
            **kwargs: Additional provider-specific arguments.

        Returns:
            Parsed webhook data dictionary, or None for test webhooks.

        Raises:
            InvalidDataError: If the webhook data is invalid.
        """

    def get_payment_history(self, customer_id: str) -> list[dict[str, Any]]:
        """Get payment history for a customer.

        Args:
            customer_id: The customer's unique identifier.

        Returns:
            List of payment records.
        """
        return []

    def get_usage_metrics(self, customer_id: str) -> dict[str, Any]:
        """Get usage metrics for a customer.

        Args:
            customer_id: The customer's unique identifier.

        Returns:
            Dictionary of usage metrics.
        """
        return {}

    def get_customer_data(self, customer_id: str) -> dict[str, Any]:
        """Get customer data from the provider.

        Args:
            customer_id: The customer's unique identifier.

        Returns:
            Dictionary of customer information.
        """
        return {}

    def get_related_events(self, customer_id: str) -> list[dict[str, Any]]:
        """Get related events for a customer.

        Args:
            customer_id: The customer's unique identifier.

        Returns:
            List of related event records.
        """
        return []
