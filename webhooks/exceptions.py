class WebhookError(Exception):
    """Base class for webhook-related errors"""

    pass


class InvalidEventType(WebhookError):
    """Raised when the event type is invalid"""

    pass


class MissingCustomerData(WebhookError):
    """Raised when required customer data is missing"""

    pass


class InvalidDataError(WebhookError):
    """Raised when webhook data is invalid"""

    pass


class CustomerNotFoundError(WebhookError):
    """Raised when a customer cannot be found"""

    pass
