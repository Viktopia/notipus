import re

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Organization(models.Model):
    STRIPE_PLANS = (
        ("trial", "14-Day Trial"),
        ("basic", "Basic Plan - $29/month"),
        ("pro", "Pro Plan - $99/month"),
        ("enterprise", "Enterprise Plan - $299/month"),
    )

    name = models.CharField(max_length=200)
    shop_domain = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    trial_end_date = models.DateTimeField(
        default=lambda: timezone.now() + timezone.timedelta(days=14)
    )
    billing_cycle_anchor = models.IntegerField(null=True, blank=True)
    stripe_customer_id = models.CharField(max_length=255, blank=True, default="")

    def __str__(self):
        return f"{self.name} ({self.shop_domain})"


class Integration(models.Model):
    INTEGRATION_TYPES = (
        ("stripe", "Stripe Payments"),
        ("shopify", "Shopify Ecommerce"),
        ("chargify", "Chargify Billing"),
    )

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    integration_type = models.CharField(max_length=50, choices=INTEGRATION_TYPES)
    is_active = models.BooleanField(default=True)
    config_data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("organization", "integration_type")

    def __str__(self):
        return f"{self.organization.name} - {self.get_integration_type_display()}"


def validate_domain(value):
    """Validate domain format"""
    # Remove protocol if present
    domain = (
        value.lower()
        .replace("http://", "")
        .replace("https://", "")
        .replace("www.", "")
    )

    # Basic domain regex pattern
    domain_pattern = r"^([a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$"

    if not re.match(domain_pattern, domain):
        raise ValidationError(f'"{value}" is not a valid domain format')

    return domain


class Company(models.Model):
    domain = models.CharField(
        max_length=255, unique=True, validators=[validate_domain]
    )
    name = models.CharField(max_length=255, blank=True, default="")
    logo_url = models.URLField(blank=True, default="")
    brand_info = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.domain})" if self.name else self.domain

    def save(self, *args, **kwargs):
        """Override save to ensure validation"""
        self.full_clean()
        super().save(*args, **kwargs)

    def clean(self):
        """Validate the domain"""
        if self.domain:
            self.domain = validate_domain(self.domain)


class UsageLimit(models.Model):
    plan = models.CharField(max_length=20, choices=Organization.STRIPE_PLANS)
    max_monthly_registrations = models.IntegerField()
    max_monthly_notifications = models.IntegerField()

    def __str__(self):
        return (
            f"{self.get_plan_display()} - "
            f"{self.max_monthly_registrations} registrations"
        )


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    slack_user_id = models.CharField(max_length=255, unique=True)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.user.username} ({self.organization.name})"


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
