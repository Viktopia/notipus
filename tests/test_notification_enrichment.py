from datetime import datetime, timedelta
import pytest
from app.enrichment import NotificationEnricher
from app.models import CustomerContext, Priority

def test_payment_failure_includes_payment_history():
    """Test that payment failure notifications include relevant payment history"""
    enricher = NotificationEnricher()

    event = {
        "type": "payment_failure",
        "customer_id": "cust_123",
        "amount": 500,
        "currency": "USD",
        "payment_method": "card_expired"
    }

    enriched = enricher.enrich_notification(event)

    # Should include payment history context
    assert "payment_history" in enriched.context
    history = enriched.context["payment_history"]
    assert "last_successful_payment" in history
    assert "total_successful_payments" in history
    assert "average_payment_amount" in history

    # Should include risk assessment
    assert "risk_factors" in enriched.context
    assert isinstance(enriched.context["risk_factors"], list)

    # Should prioritize based on customer value
    assert "priority" in enriched
    assert isinstance(enriched.priority, Priority)

def test_trial_ending_includes_usage_metrics():
    """Test that trial ending notifications include relevant usage data"""
    enricher = NotificationEnricher()

    event = {
        "type": "trial_ending",
        "customer_id": "cust_456",
        "trial_start": "2024-02-15",
        "trial_end": "2024-03-15"
    }

    enriched = enricher.enrich_notification(event)

    # Should include usage metrics
    assert "usage_metrics" in enriched.context
    metrics = enriched.context["usage_metrics"]
    assert "active_users" in metrics
    assert "feature_adoption_rate" in metrics
    assert "engagement_score" in metrics

    # Should include comparison to successful conversions
    assert "conversion_indicators" in enriched.context
    indicators = enriched.context["conversion_indicators"]
    assert "similar_customers_conversion_rate" in indicators
    assert "positive_signals" in indicators
    assert "areas_of_concern" in indicators

def test_customer_context_is_comprehensive():
    """Test that customer context includes all relevant business metrics"""
    enricher = NotificationEnricher()

    customer_id = "cust_789"
    context = enricher.get_customer_context(customer_id)

    assert isinstance(context, CustomerContext)

    # Business metrics
    assert context.lifetime_value > 0
    assert context.churn_risk_score >= 0
    assert context.health_score >= 0

    # Usage and engagement
    assert "active_users_trend" in context.metrics
    assert "feature_usage" in context.metrics
    assert "support_tickets" in context.metrics

    # Customer journey
    assert context.customer_since is not None
    assert context.last_interaction is not None
    assert context.account_stage is not None

def test_action_items_are_specific_and_actionable():
    """Test that generated action items are specific and actionable"""
    enricher = NotificationEnricher()

    event = {
        "type": "payment_failure",
        "customer_id": "cust_123",
        "amount": 500,
        "currency": "USD"
    }

    actions = enricher.generate_action_items(event)

    for action in actions:
        # Each action should have clear ownership
        assert action.owner_role is not None

        # Each action should have a deadline
        assert action.due_date is not None
        assert isinstance(action.due_date, datetime)

        # Each action should have a clear outcome
        assert action.expected_outcome is not None

        # Each action should have relevant links/tools
        assert len(action.relevant_links) > 0

        # Each action should be measurable
        assert action.success_criteria is not None

def test_notification_correlates_related_events():
    """Test that notifications include correlated events for context"""
    enricher = NotificationEnricher()

    event = {
        "type": "subscription_cancelled",
        "customer_id": "cust_123",
        "timestamp": "2024-03-15T10:00:00Z"
    }

    enriched = enricher.enrich_notification(event)

    # Should include related events
    assert "related_events" in enriched.context
    related = enriched.context["related_events"]

    # Should look back at least 30 days
    earliest_event = min(e["timestamp"] for e in related)
    assert datetime.now() - datetime.fromisoformat(earliest_event) <= timedelta(days=30)

    # Should identify event patterns
    assert "event_patterns" in enriched.context
    patterns = enriched.context["event_patterns"]
    assert isinstance(patterns, list)

    # Should suggest pattern-based actions
    assert "pattern_based_recommendations" in enriched.context