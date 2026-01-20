import re
import uuid

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone
from django.utils.text import slugify


def get_trial_end_date():
    """Return trial end date 14 days from now"""
    return timezone.now() + timezone.timedelta(days=14)


class Organization(models.Model):
    """
    An organization represents a tenant in our multi-tenant SaaS.
    Each organization has its own integrations, users, and settings.
    """

    STRIPE_PLANS = (
        ("trial", "14-Day Trial"),
        ("basic", "Basic Plan - $29/month"),
        ("pro", "Pro Plan - $99/month"),
        ("enterprise", "Enterprise Plan - $299/month"),
    )

    STATUS_CHOICES = (
        ("active", "Active"),
        ("trial", "Trial"),
        ("suspended", "Suspended"),
        ("cancelled", "Cancelled"),
    )

    # Basic fields
    uuid = models.UUIDField(
        default=uuid.uuid4, editable=False, unique=True, db_index=True
    )
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    shop_domain = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Billing and subscription
    subscription_plan = models.CharField(
        max_length=20, choices=STRIPE_PLANS, default="trial"
    )
    subscription_status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="trial"
    )
    trial_end_date = models.DateTimeField(default=get_trial_end_date)
    billing_cycle_anchor = models.IntegerField(null=True, blank=True)
    stripe_customer_id = models.CharField(max_length=255, blank=True, default="")
    payment_method_added = models.BooleanField(default=False)

    class Meta:
        app_label = "core"

    def __str__(self):
        return f"{self.name} ({self.shop_domain})"

    def save(self, *args, **kwargs):
        if not self.slug:
            self._generate_unique_slug()
        super().save(*args, **kwargs)

    def _generate_unique_slug(self):
        """Generate a unique slug in a race-condition-safe manner"""
        base_slug = slugify(self.name)
        slug = base_slug
        counter = 1

        # Use atomic transaction to prevent race conditions
        with transaction.atomic():
            while True:
                try:
                    # Try to save with current slug by using select_for_update
                    # to lock potential conflicting records
                    existing = (
                        Organization.objects.select_for_update()
                        .filter(slug=slug)
                        .exclude(pk=self.pk)
                        .first()
                    )

                    if not existing:
                        self.slug = slug
                        break

                    # Slug exists, try next variation
                    slug = f"{base_slug}-{counter}"
                    counter += 1

                    # Prevent infinite loops
                    if counter > 1000:
                        # Fallback to UUID if we can't find a unique slug
                        self.slug = f"{base_slug}-{uuid.uuid4().hex[:8]}"
                        break

                except Exception:
                    # If there's any database error, use UUID fallback
                    self.slug = f"{base_slug}-{uuid.uuid4().hex[:8]}"
                    break

    @property
    def webhook_token(self):
        """Return UUID as webhook token for URL obfuscation"""
        return str(self.uuid)

    @property
    def is_trial(self):
        """Check if organization is on trial"""
        return self.subscription_status == "trial"

    @property
    def is_active(self):
        """Check if organization is active"""
        return self.subscription_status in ["active", "trial"]


class OrganizationUser(models.Model):
    """
    Junction table for organization membership with roles.
    A user can belong to multiple organizations with different roles.
    """

    ROLE_CHOICES = (
        ("owner", "Owner"),
        ("admin", "Administrator"),
        ("member", "Member"),
        ("viewer", "Viewer"),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="member")
    joined_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        app_label = "core"
        unique_together = ("user", "organization")

    def __str__(self):
        return f"{self.user.username} - {self.organization.name} ({self.role})"


class Integration(models.Model):
    """
    Integrations for organizations - now supports both customer payment providers
    and workspace-specific notification integrations.
    """

    INTEGRATION_TYPES = (
        # Customer payment providers (organization-specific)
        ("stripe_customer", "Stripe Customer Payments"),
        ("shopify", "Shopify Ecommerce"),
        ("chargify", "Chargify / Maxio Advanced Billing"),
        # Notification integrations (organization-specific)
        ("slack_notifications", "Slack Notifications"),
    )

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="integrations"
    )
    integration_type = models.CharField(max_length=50, choices=INTEGRATION_TYPES)

    # OAuth and authentication data
    oauth_credentials = models.JSONField(default=dict, blank=True)
    webhook_secret = models.CharField(max_length=255, blank=True)

    # Integration-specific settings
    integration_settings = models.JSONField(default=dict, blank=True)

    # Status
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Legacy field for backward compatibility
    auth_data = models.JSONField(default=dict, blank=True)

    class Meta:
        app_label = "core"
        unique_together = ["organization", "integration_type"]

    def __str__(self):
        return f"{self.organization.name} - {self.get_integration_type_display()}"

    # Properties for Slack integration
    @property
    def slack_team_id(self):
        """Get Slack team ID from OAuth credentials."""
        return self.oauth_credentials.get("team", {}).get("id")

    @property
    def slack_channel(self):
        """Get Slack channel from integration settings."""
        return self.integration_settings.get("channel", "#general")

    @property
    def slack_bot_token(self):
        """Get Slack bot token from OAuth credentials."""
        return self.oauth_credentials.get("access_token")


class GlobalBillingIntegration(models.Model):
    """
    Global integrations for Notipus's own billing and authentication.
    These are not tied to any specific organization.
    """

    INTEGRATION_TYPES = (
        ("stripe_billing", "Stripe Billing (Notipus Revenue)"),
        ("slack_auth", "Slack Authentication (Global)"),
    )

    integration_type = models.CharField(
        max_length=50, choices=INTEGRATION_TYPES, unique=True
    )

    # OAuth and authentication data
    oauth_credentials = models.JSONField(default=dict, blank=True)
    webhook_secret = models.CharField(max_length=255, blank=True)

    # Integration-specific settings
    integration_settings = models.JSONField(default=dict, blank=True)

    # Status
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Global Billing Integration"
        verbose_name_plural = "Global Billing Integrations"
        ordering = ["integration_type"]

    def __str__(self):
        return f"Global {self.get_integration_type_display()}"


def validate_domain(value):
    """Validate domain format and return cleaned domain"""
    # Remove protocol if present and clean
    domain = (
        value.replace("https://", "").replace("http://", "").replace("www.", "").lower()
    )

    # Validate format - must have at least one dot for TLD
    domain_pattern = re.compile(
        r"^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$"
    )

    if not domain_pattern.match(domain):
        raise ValidationError("Enter a valid domain name.")

    return domain


class Company(models.Model):
    """
    Company model for storing enriched brand/company data.

    Used by DomainEnrichmentService to cache brand information
    retrieved from enrichment providers like Brandfetch.
    """

    name = models.CharField(max_length=255, blank=True, default="")
    domain = models.CharField(max_length=255, unique=True, validators=[validate_domain])
    logo_url = models.URLField(max_length=500, blank=True, default="")
    brand_info = models.JSONField(default=dict, blank=True)

    class Meta:
        app_label = "core"
        verbose_name_plural = "Companies"

    def __str__(self):
        display_name = self.name or self.domain
        return f"{display_name} ({self.domain})"

    def save(self, *args, **kwargs):
        self.full_clean()  # This calls clean() and validators
        super().save(*args, **kwargs)

    def clean(self):
        # Clean and validate domain
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


class Plan(models.Model):
    """
    Plan definitions with usage limits for organizations.
    """

    name = models.CharField(max_length=50, unique=True)
    display_name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    price_monthly = models.DecimalField(max_digits=10, decimal_places=2)
    price_yearly = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )

    # Limits
    max_users = models.IntegerField(default=1)
    max_integrations = models.IntegerField(default=1)
    max_monthly_notifications = models.IntegerField(default=1000)

    # Features
    features = models.JSONField(default=list)

    # Stripe integration
    stripe_price_id_monthly = models.CharField(max_length=100, blank=True)
    stripe_price_id_yearly = models.CharField(max_length=100, blank=True)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "core"

    def __str__(self):
        return self.display_name


class WebAuthnCredential(models.Model):
    """
    Store WebAuthn credentials for passwordless authentication.
    """

    user = models.ForeignKey(
        "auth.User", on_delete=models.CASCADE, related_name="webauthn_credentials"
    )

    # WebAuthn credential data
    credential_id = models.TextField(unique=True)  # Base64 encoded credential ID
    public_key = models.TextField()  # Base64 encoded public key
    sign_count = models.BigIntegerField(default=0)  # Authentication counter

    # Credential metadata
    name = models.CharField(
        max_length=100, help_text="User-friendly name for this credential"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_used = models.DateTimeField(null=True, blank=True)

    # Device info (optional)
    user_agent = models.TextField(blank=True)

    class Meta:
        app_label = "core"
        verbose_name = "WebAuthn Credential"
        verbose_name_plural = "WebAuthn Credentials"

    def __str__(self):
        return f"{self.user.username} - {self.name}"


class WebAuthnChallenge(models.Model):
    """
    Temporary storage for WebAuthn challenges during authentication flow.
    """

    challenge = models.CharField(max_length=255, unique=True)  # Base64 encoded
    user = models.ForeignKey(
        "auth.User", on_delete=models.CASCADE, null=True, blank=True
    )  # Null for registration challenges
    created_at = models.DateTimeField(auto_now_add=True)

    # Challenge type
    CHALLENGE_TYPES = (
        ("registration", "Registration"),
        ("authentication", "Authentication"),
    )
    challenge_type = models.CharField(max_length=20, choices=CHALLENGE_TYPES)

    class Meta:
        app_label = "core"
        verbose_name = "WebAuthn Challenge"
        verbose_name_plural = "WebAuthn Challenges"

    def __str__(self):
        user_str = self.user.username if self.user else "Anonymous"
        return f"{self.challenge_type} challenge for {user_str}"
