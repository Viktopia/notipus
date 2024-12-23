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
    """Represents a payment-related event"""

    id: str
    event_type: str  # "payment_success", "payment_failure", "trial_end", etc.
    customer_id: str
    amount: float
    currency: str
    status: str
    timestamp: datetime
    subscription_id: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate event data"""
        if not self.event_type:
            raise ValueError("Event type is required")
        if not self.customer_id:
            raise ValueError("Customer ID is required")
        if self.amount < 0:
            raise ValueError("Amount cannot be negative")
        if not self.currency or len(self.currency) != 3:
            raise ValueError("Invalid currency code")
        if not self.status:
            raise ValueError("Status is required")
        if not isinstance(self.timestamp, datetime):
            raise ValueError("Timestamp must be a datetime object")

    def __getitem__(self, key: str) -> Any:
        """Support dictionary-like access to event data"""
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
            ]
        }


@dataclass
class Notification:
    """A notification to be sent to Slack"""

    title: str
    sections: List[NotificationSection]
    color: str
    emoji: str

    def to_slack_message(self) -> Dict[str, Any]:
        """Convert notification to Slack message format"""
        blocks = []

        # Add header
        blocks.append({
            "type": "header",
            "text": {"type": "plain_text", "text": f"{self.emoji} {self.title}"},
        })

        # Add sections
        for section in self.sections:
            blocks.append(section.to_dict())

        return {
            "blocks": blocks,
            "color": self.color,
        }


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
