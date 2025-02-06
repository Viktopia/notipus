from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import List, Optional, Dict, Any, Set


class EventType(Enum):
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
    """Event priority levels"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class CustomerValueTier(str, Enum):
    """Customer value tiers based on revenue and engagement"""

    ENTERPRISE = "enterprise"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class EngagementLevel(str, Enum):
    """Customer engagement levels based on feature usage"""

    POWER_USER = "power_user"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class FeatureUsage:
    """Represents usage data for a specific feature"""

    feature_id: str
    last_used: datetime
    usage_count: int
    is_key_feature: bool
    adoption_status: str  # "unused", "trying", "adopted"


@dataclass
class PaymentEvent:
    """Represents a payment-related event from any payment provider"""

    def __init__(
        self,
        id: str,
        event_type: str,
        customer_id: str,
        amount: float,
        currency: str,
        status: str,
        timestamp: datetime,
        metadata: Optional[Dict[str, Any]] = None,
    ):
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
        """Support dictionary-like access to event data"""
        if key == "type":
            return self.event_type
        if hasattr(self, key):
            return getattr(self, key)
        if key in self.metadata:
            return self.metadata[key]
        raise KeyError(f"'{key}' not found in event data")

    def get(self, key: str, default: Any = None) -> Any:
        """Get event data with a default value"""
        try:
            return self[key]
        except KeyError:
            return default


@dataclass
class CustomerInsight:
    """Comprehensive customer insights and analysis"""

    value_tier: CustomerValueTier
    engagement_level: EngagementLevel
    features_used: Set[str]
    key_features_missing: Set[str]
    recent_events: List[Dict[str, Any]]
    payment_success_rate: float
    days_since_signup: int
    recommendations: List[str]
    risk_factors: List[str]
    opportunities: List[str]


@dataclass
class CustomerContext:
    """Enriched customer context with insights"""

    customer_id: str
    name: str
    subscription_start: datetime
    current_plan: str
    customer_health_score: float
    churn_risk_score: float
    lifetime_value: float
    health_score: float
    recent_interactions: List[Dict[str, Any]]
    feature_usage: Dict[str, FeatureUsage]
    payment_history: List[Dict[str, Any]]
    insights: CustomerInsight
    metrics: Dict[str, Any] = field(default_factory=dict)
    customer_since: Optional[datetime] = None
    last_interaction: Optional[datetime] = None
    account_stage: Optional[str] = None


@dataclass
class ActionItem:
    """Actionable task for customer success"""

    type: str
    description: str
    link: str
    due_date: datetime
    priority: Priority
    context: Dict[str, Any]
    owner_role: Optional[str] = None
    expected_outcome: Optional[str] = None
    relevant_links: List[str] = field(default_factory=list)
    success_criteria: Optional[str] = None
    assigned_to: Optional[str] = None
    completed: bool = False
    deadline: Optional[datetime] = None


@dataclass
class NotificationSection:
    """Section of a notification message"""

    title: str
    fields: Dict[str, str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "section",
            "title": {"type": "plain_text", "text": self.title},
            "fields": [
                {"type": "mrkdwn", "text": f"*{k}*\n{v}"}
                for k, v in self.fields.items()
            ],
        }


@dataclass
class Notification:
    """Slack notification message"""

    title: str
    sections: List[NotificationSection]
    color: str = "#17a2b8"  # Default info color
    emoji: str = "ℹ️"  # Default info emoji
    action_buttons: List[Dict[str, str]] = field(default_factory=list)
    _status: str = field(default="info", init=False)

    def __post_init__(self):
        """Initialize status based on color"""
        self._status = self._get_status_from_color(self.color)

    def to_slack_message(self) -> Dict[str, Any]:
        """Convert to Slack message format"""
        blocks = []

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
        """Get notification status"""
        return self._status

    @status.setter
    def status(self, value: str) -> None:
        """Set notification status and update color"""
        self._status = value
        self.color = self._get_color_from_status(value)

    def _get_status_from_color(self, color: str) -> str:
        """Map color to status"""
        color_map = {
            "#28a745": "success",
            "#dc3545": "failed",
            "#ffc107": "warning",
            "#17a2b8": "info",
        }
        return color_map.get(color, "info")

    def _get_color_from_status(self, status: str) -> str:
        """Map status to color"""
        status_map = {
            "success": "#28a745",
            "failed": "#dc3545",
            "error": "#dc3545",
            "warning": "#ffc107",
            "info": "#17a2b8",
        }
        return status_map.get(status.lower(), "#17a2b8")


@dataclass
class Event:
    """Business event with enriched context"""

    type: EventType
    priority: Priority
    customer: CustomerContext
    data: Dict[str, Any]
    timestamp: datetime
    response_sla: timedelta
    insights: Optional[CustomerInsight] = None
    correlated_events: Optional[List["Event"]] = None


@dataclass
class EventCorrelation:
    """Group of related events"""

    event_chain: List[Event]
    resolution: Optional[str]
    duration: timedelta
    pattern: Optional[str] = None
    impact: Optional[str] = None
