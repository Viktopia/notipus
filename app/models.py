from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import List, Optional, Dict, Any

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
    URGENT = auto()
    HIGH = auto()
    MEDIUM = auto()
    LOW = auto()

@dataclass
class CustomerContext:
    customer_id: str
    name: str
    subscription_start: datetime
    current_plan: str
    customer_health_score: float
    churn_risk_score: float
    lifetime_value: float
    health_score: float
    recent_interactions: List[Dict[str, Any]]
    feature_usage: Dict[str, float]
    payment_history: List[Dict[str, Any]]
    metrics: Dict[str, Any] = field(default_factory=dict)
    customer_since: Optional[datetime] = None
    last_interaction: Optional[datetime] = None
    account_stage: Optional[str] = None

@dataclass
class ActionItem:
    type: str
    description: str
    link: str
    due_date: datetime
    priority: Priority
    owner_role: Optional[str] = None
    expected_outcome: Optional[str] = None
    relevant_links: List[str] = field(default_factory=list)
    success_criteria: Optional[str] = None
    assigned_to: Optional[str] = None
    completed: bool = False
    deadline: Optional[datetime] = None

@dataclass
class NotificationSection:
    text: str
    actions: Optional[List[ActionItem]] = None

@dataclass
class Notification:
    header: str
    color: str
    sections: List[NotificationSection]
    customer_context: CustomerContext
    action_buttons: List[Dict[str, str]]
    priority: Priority
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class Event:
    type: EventType
    priority: Priority
    customer: CustomerContext
    data: Dict[str, Any]
    timestamp: datetime
    response_sla: timedelta
    correlated_events: Optional[List['Event']] = None

@dataclass
class EventCorrelation:
    event_chain: List[Event]
    resolution: Optional[str]
    duration: timedelta