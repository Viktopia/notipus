from datetime import datetime, timedelta
from typing import Dict, Any, List

from .models import (
    CustomerInsight,
    CustomerValueTier,
    EngagementLevel,
    FeatureUsage,
    PaymentEvent,
)


class CustomerInsightAnalyzer:
    """Analyzes customer data to generate actionable insights"""

    # Key features that indicate strong product adoption
    KEY_FEATURES = {
        "api_integration",
        "dashboard_customization",
        "webhook_configuration",
        "team_collaboration",
        "advanced_reporting",
    }

    def analyze_customer(
        self, event: PaymentEvent, customer_data: Dict[str, Any]
    ) -> CustomerInsight:
        """Generate comprehensive customer insights from event and customer data"""
        feature_usage = self._analyze_feature_usage(customer_data)
        value_tier = self._determine_value_tier(customer_data)
        engagement_level = self._calculate_engagement_level(feature_usage)

        return CustomerInsight(
            value_tier=value_tier,
            engagement_level=engagement_level,
            features_used=set(feature_usage.keys()),
            key_features_missing=self.KEY_FEATURES - set(feature_usage.keys()),
            recent_events=customer_data.get("recent_events", [])[:5],
            payment_success_rate=self._calculate_payment_success_rate(customer_data),
            days_since_signup=self._calculate_account_age(customer_data),
            recommendations=self._generate_recommendations(
                event, feature_usage, value_tier, engagement_level
            ),
            risk_factors=self._identify_risk_factors(customer_data, feature_usage),
            opportunities=self._identify_opportunities(customer_data, feature_usage),
        )

    def _analyze_feature_usage(
        self, customer_data: Dict[str, Any]
    ) -> Dict[str, FeatureUsage]:
        """Analyze how the customer is using different features"""
        usage = {}
        raw_usage = customer_data.get("feature_usage", {})

        for feature_id, usage_data in raw_usage.items():
            usage[feature_id] = FeatureUsage(
                feature_id=feature_id,
                last_used=datetime.fromisoformat(usage_data.get("last_used", "")),
                usage_count=usage_data.get("count", 0),
                is_key_feature=feature_id in self.KEY_FEATURES,
                adoption_status=self._determine_adoption_status(usage_data),
            )

        return usage

    def _determine_value_tier(self, customer_data: Dict[str, Any]) -> CustomerValueTier:
        """Determine customer value tier based on revenue and engagement"""
        mrr = customer_data.get("mrr", 0)
        lifetime_value = customer_data.get("lifetime_value", 0)
        team_size = customer_data.get("team_size", 1)

        if mrr > 1000 or lifetime_value > 10000 or team_size > 20:
            return CustomerValueTier.ENTERPRISE
        elif mrr > 500 or lifetime_value > 5000 or team_size > 10:
            return CustomerValueTier.HIGH
        elif mrr > 100 or lifetime_value > 1000 or team_size > 5:
            return CustomerValueTier.MEDIUM
        return CustomerValueTier.LOW

    def _calculate_engagement_level(
        self, feature_usage: Dict[str, FeatureUsage]
    ) -> EngagementLevel:
        """Calculate engagement level based on feature usage"""
        key_features_used = sum(
            1 for f in feature_usage.values() if f.is_key_feature and f.usage_count > 0
        )
        total_usage = sum(f.usage_count for f in feature_usage.values())
        adoption_rate = len(feature_usage) / len(self.KEY_FEATURES)

        if key_features_used >= 4 and total_usage > 100 and adoption_rate > 0.8:
            return EngagementLevel.POWER_USER
        elif key_features_used >= 3 and total_usage > 50 and adoption_rate > 0.6:
            return EngagementLevel.HIGH
        elif key_features_used >= 2 and total_usage > 20 and adoption_rate > 0.4:
            return EngagementLevel.MEDIUM
        return EngagementLevel.LOW

    def _calculate_payment_success_rate(self, customer_data: Dict[str, Any]) -> float:
        """Calculate payment success rate from payment history"""
        payment_history = customer_data.get("payment_history", [])
        if not payment_history:
            return 1.0

        successful = sum(1 for p in payment_history if p.get("status") == "success")
        return successful / len(payment_history)

    def _calculate_account_age(self, customer_data: Dict[str, Any]) -> int:
        """Calculate account age in days"""
        created_at = customer_data.get("created_at")
        if not created_at:
            return 0

        created_date = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        return (datetime.now() - created_date).days

    def _generate_recommendations(
        self,
        event: PaymentEvent,
        feature_usage: Dict[str, FeatureUsage],
        value_tier: CustomerValueTier,
        engagement_level: EngagementLevel,
    ) -> List[str]:
        """Generate personalized recommendations based on event and customer data"""
        recommendations = []

        if event.event_type == "trial_end":
            recommendations.extend(self._get_trial_recommendations(feature_usage))
        elif event.event_type == "payment_failure":
            recommendations.extend(
                self._get_payment_recommendations(value_tier, engagement_level)
            )

        # Add general recommendations based on engagement
        if engagement_level in {EngagementLevel.LOW, EngagementLevel.MEDIUM}:
            unused_key_features = [
                f
                for f in feature_usage.values()
                if f.is_key_feature and f.adoption_status == "unused"
            ]
            if unused_key_features:
                recommendations.append(
                    f"Schedule product walkthrough focusing on: "
                    f"{', '.join(f.feature_id for f in unused_key_features)}"
                )

        return recommendations

    def _get_trial_recommendations(
        self, feature_usage: Dict[str, FeatureUsage]
    ) -> List[str]:
        """Get recommendations for trial users"""
        recommendations = []

        # Check API usage
        api_usage = feature_usage.get("api_integration")
        if not api_usage or api_usage.adoption_status == "unused":
            recommendations.append(
                "Schedule technical demo focusing on API capabilities and integration"
            )

        # Check dashboard usage
        dashboard_usage = feature_usage.get("dashboard_customization")
        if not dashboard_usage or dashboard_usage.adoption_status == "unused":
            recommendations.append(
                "Share dashboard setup guide and customer success stories"
            )

        return recommendations

    def _get_payment_recommendations(
        self, value_tier: CustomerValueTier, engagement_level: EngagementLevel
    ) -> List[str]:
        """Get recommendations for payment failures"""
        recommendations = []

        if value_tier in {CustomerValueTier.HIGH, CustomerValueTier.ENTERPRISE}:
            recommendations.append(
                "High-value customer: Immediate outreach from account manager"
            )

        if engagement_level in {EngagementLevel.HIGH, EngagementLevel.POWER_USER}:
            recommendations.append(
                "Highly engaged: Offer payment flexibility or alternative methods"
            )

        return recommendations

    def _identify_risk_factors(
        self, customer_data: Dict[str, Any], feature_usage: Dict[str, FeatureUsage]
    ) -> List[str]:
        """Identify potential risk factors from customer data"""
        risks = []

        # Check for declining usage
        for feature in feature_usage.values():
            if (
                feature.is_key_feature
                and feature.last_used
                and datetime.now() - feature.last_used > timedelta(days=30)
            ):
                risks.append(f"No usage of {feature.feature_id} in last 30 days")

        # Check for payment issues
        payment_history = customer_data.get("payment_history", [])
        recent_failures = sum(
            1 for p in payment_history[-3:] if p.get("status") == "failed"
        )
        if recent_failures >= 2:
            risks.append("Multiple recent payment failures")

        return risks

    def _identify_opportunities(
        self, customer_data: Dict[str, Any], feature_usage: Dict[str, FeatureUsage]
    ) -> List[str]:
        """Identify growth opportunities from customer data"""
        opportunities = []

        # Check for upgrade potential
        team_size = customer_data.get("team_size", 0)
        plan_limit = customer_data.get("plan_limit", float("inf"))
        if team_size > plan_limit * 0.8:
            opportunities.append("Approaching team size limit - upgrade opportunity")

        # Check for unused premium features
        premium_features = customer_data.get("available_premium_features", [])
        for feature in premium_features:
            if feature not in feature_usage:
                opportunities.append(f"Unused premium feature: {feature}")

        return opportunities

    def _determine_adoption_status(self, usage_data: Dict[str, Any]) -> str:
        """Determine feature adoption status from usage data"""
        usage_count = usage_data.get("count", 0)
        if usage_count == 0:
            return "unused"
        elif usage_count < 5:
            return "trying"
        return "adopted"
