from datetime import datetime, timedelta
import pytest
from app.event_processor import EventProcessor, CustomerContext, EventType, Priority

def test_event_classification():
    """Test that events are properly classified with correct priority"""
    processor = EventProcessor()

    # Payment failure for high-value customer should be highest priority
    high_value_failure = {
        "event": "payment_failure",
        "customer": {
            "lifetime_value": 50000,
            "subscription_tier": "enterprise",
            "status": "active"
        }
    }
    event = processor.classify_event(high_value_failure)
    assert event.type == EventType.PAYMENT_FAILURE
    assert event.priority == Priority.URGENT
    assert event.response_sla == timedelta(hours=2)

    # Trial ending for active user should be high priority
    active_trial_end = {
        "event": "trial_end",
        "customer": {
            "trial_usage": "high",
            "last_active": datetime.now(),
            "feature_adoption": 0.8
        }
    }
    event = processor.classify_event(active_trial_end)
    assert event.type == EventType.TRIAL_END
    assert event.priority == Priority.HIGH
    assert event.response_sla == timedelta(hours=24)

    # Subscription upgrade should be medium priority
    upgrade_event = {
        "event": "subscription_upgrade",
        "customer": {
            "previous_plan": "basic",
            "new_plan": "pro"
        }
    }
    event = processor.classify_event(upgrade_event)
    assert event.type == EventType.UPGRADE
    assert event.priority == Priority.MEDIUM
    assert event.response_sla == timedelta(days=2)

def test_customer_context_enrichment():
    """Test that customer context is properly enriched with relevant data"""
    processor = EventProcessor()

    customer_data = {
        "customer": {
            "id": "cust_123",
            "name": "Acme Corp",
            "subscription_start": "2023-01-01",
            "current_plan": "pro"
        }
    }

    context = processor.enrich_customer_context(customer_data)
    assert isinstance(context, CustomerContext)
    assert context.customer_health_score > 0
    assert context.churn_risk_score > 0
    assert len(context.recent_interactions) > 0
    assert context.feature_usage is not None
    assert context.payment_history is not None

def test_action_item_generation():
    """Test that appropriate action items are generated based on event and context"""
    processor = EventProcessor()

    # Payment failure should generate urgent payment-related actions
    payment_failure_event = {
        "event": "payment_failure",
        "customer": {
            "payment_method": "card_expired",
            "billing_contact": "john@example.com"
        }
    }

    actions = processor.generate_action_items(payment_failure_event)
    assert len(actions) >= 3
    assert any(a.type == "contact_customer" for a in actions)
    assert any(a.type == "update_payment_method" for a in actions)
    assert all(a.link is not None for a in actions)

    # Trial end should generate conversion-focused actions
    trial_end_event = {
        "event": "trial_end",
        "customer": {
            "usage": "medium",
            "feedback": "positive"
        }
    }

    actions = processor.generate_action_items(trial_end_event)
    assert len(actions) >= 2
    assert any(a.type == "schedule_call" for a in actions)
    assert any(a.type == "send_case_studies" for a in actions)
    assert all(a.due_date is not None for a in actions)

def test_notification_formatting():
    """Test that notifications are properly formatted based on priority and content"""
    processor = EventProcessor()

    urgent_event = {
        "type": EventType.PAYMENT_FAILURE,
        "priority": Priority.URGENT,
        "customer": {
            "name": "Acme Corp",
            "tier": "enterprise"
        }
    }

    notification = processor.format_notification(urgent_event)
    assert "🚨" in notification.header  # Urgent events should have alert emoji
    assert notification.color == "#FF0000"  # Urgent should be red
    assert len(notification.action_buttons) > 0
    assert notification.customer_context is not None

    # Check that customer context is prominently displayed
    assert notification.sections[0].text.startswith("*Customer:*")

    # Verify action items are properly formatted
    action_section = next(s for s in notification.sections if "Actions Required" in s.text)
    assert action_section is not None
    assert all(action.deadline for action in action_section.actions)

def test_event_correlation():
    """Test that related events are properly correlated"""
    processor = EventProcessor()

    events = [
        {
            "event": "payment_failure",
            "customer_id": "cust_123",
            "timestamp": "2024-03-15T10:00:00Z"
        },
        {
            "event": "subscription_updated",
            "customer_id": "cust_123",
            "timestamp": "2024-03-15T10:05:00Z"
        },
        {
            "event": "payment_success",
            "customer_id": "cust_123",
            "timestamp": "2024-03-15T10:10:00Z"
        }
    ]

    correlated = processor.correlate_events(events)
    assert len(correlated.event_chain) == 3
    assert correlated.resolution == "payment_success"
    assert correlated.duration == timedelta(minutes=10)