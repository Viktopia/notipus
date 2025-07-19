import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class WebhookError(Exception):
    """Base class for webhook-related errors"""

    def __init__(self, message: str, error_code: str = "WEBHOOK_ERROR"):
        self.message = message
        self.error_code = error_code
        super().__init__(message)


class InvalidEventType(WebhookError):
    """Raised when the event type is invalid"""

    def __init__(self, message: str = "Invalid event type"):
        super().__init__(message, "INVALID_EVENT_TYPE")


class MissingCustomerData(WebhookError):
    """Raised when required customer data is missing"""

    def __init__(self, message: str = "Required customer data is missing"):
        super().__init__(message, "MISSING_CUSTOMER_DATA")


class InvalidDataError(WebhookError):
    """Raised when webhook data is invalid"""

    def __init__(self, message: str = "Invalid webhook data"):
        super().__init__(message, "INVALID_DATA")


class CustomerNotFoundError(WebhookError):
    """Raised when a customer cannot be found"""

    def __init__(self, message: str = "Customer not found"):
        super().__init__(message, "CUSTOMER_NOT_FOUND")


class WebhookSignatureError(WebhookError):
    """Raised when webhook signature validation fails"""

    def __init__(self, message: str = "Invalid webhook signature"):
        super().__init__(message, "INVALID_SIGNATURE")


class WebhookProcessingError(WebhookError):
    """Raised when webhook processing fails"""

    def __init__(self, message: str = "Webhook processing failed"):
        super().__init__(message, "PROCESSING_ERROR")


def create_error_response(error: Exception, status_code: int = 500) -> Dict[str, Any]:
    """Create a standardized error response that doesn't leak internal details"""

    if isinstance(error, WebhookError):
        # Safe to expose webhook-specific errors
        logger.warning(
            f"Webhook error: {error.error_code}",
            extra={"error_code": error.error_code, "error_message": error.message},
        )
        return {
            "error": {"code": error.error_code, "message": error.message},
            "status": "error",
        }

    # For unexpected errors, log details but return generic message
    logger.error(f"Unexpected error in webhook processing: {str(error)}", exc_info=True)

    if status_code >= 500:
        # Internal server errors - don't expose details
        return {
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An internal error occurred while processing the webhook",
            },
            "status": "error",
        }
    else:
        # Client errors - can be more specific but still safe
        return {
            "error": {
                "code": "REQUEST_ERROR",
                "message": "The webhook request could not be processed",
            },
            "status": "error",
        }


def create_success_response(
    message: str = "Webhook processed successfully",
) -> Dict[str, Any]:
    """Create a standardized success response"""
    return {"status": "success", "message": message}
