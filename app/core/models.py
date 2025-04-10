from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User


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
