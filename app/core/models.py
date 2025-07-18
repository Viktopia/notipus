import re
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from django.db.models import JSONField
from django.core.exceptions import ValidationError


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


def validate_domain(value):
    """Validate domain format"""
    # Remove protocol if present
    domain = (
        value.lower().replace("http://", "").replace("https://", "").replace("www.", "")
    )

    # Basic domain regex pattern
    domain_pattern = r"^([a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$"

    if not re.match(domain_pattern, domain):
        raise ValidationError(f'"{value}" is not a valid domain format')

    return domain


class Company(models.Model):
    domain = models.CharField(max_length=255, unique=True, validators=[validate_domain])
    name = models.CharField(max_length=255, blank=True, null=True)
    logo_url = models.URLField(blank=True, null=True)
    brand_info = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        """Additional validation and cleaning"""
        if self.domain:
            self.domain = validate_domain(self.domain)

    def save(self, *args, **kwargs):
        """Override save to ensure validation"""
        self.full_clean()
        super().save(*args, **kwargs)

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
