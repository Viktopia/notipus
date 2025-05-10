from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from django.db.models import JSONField


class Organization(models.Model):
    STRIPE_PLANS = (
        ("trial", "14-Day Trial"),
        ("basic", "Basic ($20/month)"),
        ("pro", "Pro ($50/month)"),
        ("enterprise", "Enterprise ($200/month)"),
    )

    slack_team_id = models.CharField(max_length=255, unique=True)
    slack_domain = models.CharField(max_length=255, unique=True)
    name = models.CharField(max_length=255)

    stripe_customer_id = models.CharField(max_length=255, blank=True)
    subscription_plan = models.CharField(
        max_length=20, choices=STRIPE_PLANS, default="trial"
    )
    subscription_status = models.CharField(max_length=20, default="active")
    trial_end_date = models.DateTimeField(
        default=timezone.now() + timezone.timedelta(days=14)
    )
    billing_cycle_anchor = models.DateTimeField(null=True)
    payment_method_added = models.BooleanField(default=False)
    shop_domain = models.CharField(max_length=255, blank=True)


class Integration(models.Model):
    INTEGRATION_TYPES = (
        ("stripe", "Stripe Payments"),
        ("shopify", "Shopify Store"),
    )
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="integrations"
    )
    integration_type = models.CharField(
        max_length=20, choices=INTEGRATION_TYPES, db_index=True
    )
    auth_data = JSONField(default=dict)


class Company(models.Model):
    domain = models.CharField(max_length=255, unique=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    logo_url = models.URLField(blank=True, null=True)
    brand_info = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.domain})" if self.name else self.domain


class UsageLimit(models.Model):
    plan = models.CharField(max_length=20, choices=Organization.STRIPE_PLANS)
    max_monthly_registrations = models.IntegerField()
    max_daily_webhooks = models.IntegerField()
    features = models.JSONField(default=list)


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    slack_user_id = models.CharField(max_length=255, unique=True)
    slack_team_id = models.CharField(max_length=255)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)


class NotificationSettings(models.Model):
    organization = models.OneToOneField(
        Organization, on_delete=models.CASCADE, related_name="notification_settings"
    )

    # Payment events
    notify_payment_success = models.BooleanField(default=True)
    notify_payment_failure = models.BooleanField(default=True)

    # Subscription events
    notify_subscription_created = models.BooleanField(default=True)
    notify_subscription_updated = models.BooleanField(default=True)
    notify_subscription_canceled = models.BooleanField(default=True)

    # Trial events
    notify_trial_ending = models.BooleanField(default=True)
    notify_trial_expired = models.BooleanField(default=True)

    # Customer events
    notify_customer_updated = models.BooleanField(default=True)
    notify_signups = models.BooleanField(default=True)

    # Shopify events
    notify_shopify_order_created = models.BooleanField(default=True)
    notify_shopify_order_updated = models.BooleanField(default=True)
    notify_shopify_order_paid = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Notification Settings for {self.organization.name}"
