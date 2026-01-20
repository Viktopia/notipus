"""Domain models for webhook processing and notification handling.

This module contains the core domain models used throughout the webhook
processing pipeline, including payment events, customer insights, and
notification structures.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Any, TypeAlias

# Type aliases for commonly used complex types
EventData: TypeAlias = dict[str, Any]
CustomerData: TypeAlias = dict[str, Any]
MetadataDict: TypeAlias = dict[str, Any]


class EventType(Enum):
    """Types of business events that can be processed.

    These represent the normalized event types from various payment
    providers (Stripe, Chargify, Shopify).
    """

    PAYMENT_FAILURE = auto()
    PAYMENT_SUCCESS = auto()
    TRIAL_END = auto()
    TRIAL_CONVERTED = auto()
    UPGRADE = auto()
    DOWNGRADE = auto()
    SUBSCRIPTION_CANCELLED = auto()
    SUBSCRIPTION_CREATED = auto()
    UNKNOWN = auto()


class Priority(Enum):
    """Event priority levels for notification routing.

    Priority determines how urgently a notification should be
    delivered and how it should be highlighted in Slack.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class CustomerValueTier(str, Enum):
    """Customer value tiers based on revenue and engagement.

    Used for segmenting customers and prioritizing support
    and success efforts.
    """

    ENTERPRISE = "enterprise"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class EngagementLevel(str, Enum):
    """Customer engagement levels based on feature usage.

    Derived from product analytics to understand how actively
    a customer is using the platform.
    """

    POWER_USER = "power_user"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(slots=True)
class FeatureUsage:
    """Represents usage data for a specific feature.

    Tracks how a customer interacts with individual product features
    to help identify adoption patterns and opportunities.

    Attributes:
        feature_id: Unique identifier for the feature.
        last_used: Timestamp of the most recent usage.
        usage_count: Total number of times the feature was used.
        is_key_feature: Whether this is a key feature for retention.
        adoption_status: One of "unused", "trying", or "adopted".
    """

    feature_id: str
    last_used: datetime
    usage_count: int
    is_key_feature: bool
    adoption_status: str


@dataclass
class PaymentEvent:
    """Represents a payment-related event from any payment provider.

    This class provides a normalized interface for payment events from
    Stripe, Chargify, or other payment providers. It includes validation
    and dictionary-like access for compatibility with existing code.

    Attributes:
        id: Unique identifier for the event.
        event_type: Type of payment event (e.g., "payment_success").
        customer_id: Identifier of the customer involved.
        amount: Payment amount (must be non-negative).
        currency: Three-letter ISO currency code.
        status: Current status of the payment.
        timestamp: When the event occurred.
        metadata: Additional provider-specific data.

    Raises:
        ValueError: If any required field is missing or invalid.
    """

    id: str
    event_type: str
    customer_id: str
    amount: float
    currency: str
    status: str
    timestamp: datetime
    metadata: MetadataDict = field(default_factory=dict)

    def __init__(
        self,
        id: str,
        event_type: str,
        customer_id: str,
        amount: float,
        currency: str,
        status: str,
        timestamp: datetime,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Initialize a PaymentEvent with validation.

        Args:
            id: Unique identifier for the event.
            event_type: Type of payment event.
            customer_id: Identifier of the customer.
            amount: Payment amount (must be >= 0).
            currency: Three-letter ISO currency code.
            status: Current status of the payment.
            timestamp: When the event occurred.
            metadata: Optional additional data.

        Raises:
            ValueError: If validation fails for any field.
        """
        if not event_type:
            raise ValueError("Event type is required")
        if not customer_id:
            raise ValueError("Customer ID is required")
        if amount < 0:
            raise ValueError("Amount cannot be negative")
        if not currency or len(currency) != 3:
            raise ValueError("Invalid currency code")
        if not status:
            raise ValueError("Status is required")
        if not isinstance(timestamp, datetime):
            raise ValueError("Timestamp must be a datetime object")

        self.id = id
        self.event_type = event_type
        self.customer_id = customer_id
        self.amount = amount
        self.currency = currency
        self.status = status
        self.timestamp = timestamp
        self.metadata = metadata or {}

    def __getitem__(self, key: str) -> Any:
        """Support dictionary-like access to event data.

        Args:
            key: The attribute or metadata key to access.

        Returns:
            The value associated with the key.

        Raises:
            KeyError: If the key is not found in the event data.
        """
        if key == "type":
            return self.event_type
        if hasattr(self, key):
            return getattr(self, key)
        if key in self.metadata:
            return self.metadata[key]
        raise KeyError(f"'{key}' not found in event data")

    def get(self, key: str, default: Any = None) -> Any:
        """Get event data with a default value.

        Args:
            key: The attribute or metadata key to access.
            default: Value to return if key is not found.

        Returns:
            The value associated with the key, or the default.
        """
        try:
            return self[key]
        except KeyError:
            return default


@dataclass(slots=True)
class CustomerInsight:
    """Comprehensive customer insights and analysis.

    Aggregates various metrics and signals about a customer
    to provide actionable intelligence for customer success teams.

    Attributes:
        value_tier: Customer's value segment.
        engagement_level: How actively they use the product.
        features_used: Set of feature IDs the customer has used.
        key_features_missing: Important features not yet adopted.
        recent_events: List of recent event data dictionaries.
        payment_success_rate: Percentage of successful payments.
        days_since_signup: Number of days since account creation.
        recommendations: Suggested actions for the account.
        risk_factors: Identified churn risk indicators.
        opportunities: Potential upsell/expansion opportunities.
    """

    value_tier: CustomerValueTier
    engagement_level: EngagementLevel
    features_used: set[str]
    key_features_missing: set[str]
    recent_events: list[EventData]
    payment_success_rate: float
    days_since_signup: int
    recommendations: list[str]
    risk_factors: list[str]
    opportunities: list[str]


@dataclass(slots=True, kw_only=True)
class CustomerContext:
    """Enriched customer context with insights.

    Provides comprehensive customer information for notification
    enrichment and contextual decision-making.

    Attributes:
        customer_id: Unique customer identifier.
        name: Customer or company name.
        subscription_start: When the subscription began.
        current_plan: Name of the current subscription plan.
        customer_health_score: Overall health score (0-100).
        churn_risk_score: Probability of churning (0-1).
        lifetime_value: Total revenue from this customer.
        health_score: Alternative health metric.
        recent_interactions: List of recent interaction records.
        feature_usage: Map of feature ID to usage data.
        payment_history: List of historical payment records.
        insights: Aggregated customer insights.
        metrics: Additional custom metrics.
        customer_since: When they became a customer.
        last_interaction: Most recent interaction timestamp.
        account_stage: Current stage in customer lifecycle.
    """

    customer_id: str
    name: str
    subscription_start: datetime
    current_plan: str
    customer_health_score: float
    churn_risk_score: float
    lifetime_value: float
    health_score: float
    recent_interactions: list[EventData]
    feature_usage: dict[str, FeatureUsage]
    payment_history: list[EventData]
    insights: CustomerInsight
    metrics: MetadataDict = field(default_factory=dict)
    customer_since: datetime | None = None
    last_interaction: datetime | None = None
    account_stage: str | None = None


@dataclass(slots=True, kw_only=True)
class ActionItem:
    """Actionable task for customer success.

    Represents a specific action that should be taken in response
    to a customer event or insight.

    Attributes:
        type: Category of action (e.g., "outreach", "review").
        description: Human-readable description of the action.
        link: URL to relevant dashboard or tool.
        due_date: When the action should be completed.
        priority: Urgency level of the action.
        context: Additional context for the action.
        owner_role: Role responsible for this action.
        expected_outcome: What success looks like.
        relevant_links: Additional helpful URLs.
        success_criteria: How to measure completion.
        assigned_to: Specific person assigned.
        completed: Whether the action is done.
        deadline: Hard deadline if different from due_date.
    """

    type: str
    description: str
    link: str
    due_date: datetime
    priority: Priority
    context: MetadataDict
    owner_role: str | None = None
    expected_outcome: str | None = None
    relevant_links: list[str] = field(default_factory=list)
    success_criteria: str | None = None
    assigned_to: str | None = None
    completed: bool = False
    deadline: datetime | None = None


@dataclass(slots=True)
class NotificationSection:
    """Section of a notification message.

    Represents a logical grouping of fields within a Slack
    notification message.

    Attributes:
        title: Section header text.
        fields: Key-value pairs to display.
    """

    title: str
    fields: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        """Convert section to Slack block format.

        Returns:
            Dictionary representing a Slack block kit section.
        """
        return {
            "type": "section",
            "title": {"type": "plain_text", "text": self.title},
            "fields": [
                {"type": "mrkdwn", "text": f"*{k}*\n{v}"}
                for k, v in self.fields.items()
            ],
        }


@dataclass(slots=True)
class Notification:
    """Slack notification message.

    Represents a complete notification ready to be sent to Slack,
    including header, sections, and optional action buttons.

    Attributes:
        title: Main notification title.
        sections: List of content sections.
        color: Sidebar color (hex code).
        emoji: Emoji to display with title.
        action_buttons: Optional interactive buttons.
    """

    title: str
    sections: list[NotificationSection]
    color: str = "#17a2b8"
    emoji: str = "ℹ️"
    action_buttons: list[dict[str, str]] = field(default_factory=list)
    _status: str = field(default="info", init=False)

    def __post_init__(self) -> None:
        """Initialize status based on color."""
        self._status = self._get_status_from_color(self.color)

    def to_slack_message(self) -> dict[str, Any]:
        """Convert to Slack message format.

        Returns:
            Dictionary containing blocks and color for Slack API.
        """
        blocks: list[dict[str, Any]] = []

        # Add title block with emoji
        blocks.append(
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{self.emoji} {self.title}",
                    "emoji": True,
                },
            }
        )

        # Add sections
        for section in self.sections:
            blocks.append(section.to_dict())

        # Add action buttons if any
        if self.action_buttons:
            blocks.append(
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": button["text"]},
                            "url": button["url"],
                            "style": button.get("style", "default"),
                        }
                        for button in self.action_buttons
                    ],
                }
            )

        return {
            "blocks": blocks,
            "color": self.color,
        }

    @property
    def status(self) -> str:
        """Get notification status.

        Returns:
            Current status string (success, failed, warning, info).
        """
        return self._status

    @status.setter
    def status(self, value: str) -> None:
        """Set notification status and update color.

        Args:
            value: New status value.
        """
        self._status = value
        self.color = self._get_color_from_status(value)

    def _get_status_from_color(self, color: str) -> str:
        """Map color to status.

        Args:
            color: Hex color code.

        Returns:
            Status string corresponding to the color.
        """
        color_map = {
            "#28a745": "success",
            "#dc3545": "failed",
            "#ffc107": "warning",
            "#17a2b8": "info",
        }
        return color_map.get(color, "info")

    def _get_color_from_status(self, status: str) -> str:
        """Map status to color.

        Args:
            status: Status string.

        Returns:
            Hex color code for the status.
        """
        status_map = {
            "success": "#28a745",
            "failed": "#dc3545",
            "error": "#dc3545",
            "warning": "#ffc107",
            "info": "#17a2b8",
        }
        return status_map.get(status.lower(), "#17a2b8")


@dataclass(slots=True, kw_only=True)
class Event:
    """Business event with enriched context.

    Represents a fully processed and enriched business event
    ready for notification generation.

    Attributes:
        type: Normalized event type.
        priority: Event priority level.
        customer: Enriched customer context.
        data: Raw event data.
        timestamp: When the event occurred.
        response_sla: Time within which to respond.
        insights: Optional customer insights.
        correlated_events: Related events if any.
    """

    type: EventType
    priority: Priority
    customer: CustomerContext
    data: EventData
    timestamp: datetime
    response_sla: timedelta
    insights: CustomerInsight | None = None
    correlated_events: list["Event"] | None = None


@dataclass(slots=True, kw_only=True)
class EventCorrelation:
    """Group of related events.

    Tracks a sequence of related events to identify patterns
    and provide context for analysis.

    Attributes:
        event_chain: Ordered list of related events.
        resolution: How the event chain was resolved.
        duration: Total time span of the event chain.
        pattern: Identified pattern name if any.
        impact: Business impact assessment.
    """

    event_chain: list[Event]
    resolution: str | None
    duration: timedelta
    pattern: str | None = None
    impact: str | None = None
