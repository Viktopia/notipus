"""Core Django models for the Notipus application.

This module contains all the core domain models including organizations,
users, integrations, billing, and authentication-related models.
"""

import re
import uuid
from datetime import datetime
from typing import Any, ClassVar

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone
from django.utils.text import slugify


def get_trial_end_date() -> datetime:
    """Return trial end date 14 days from now.

    Returns:
        datetime: Trial end date.
    """
    return timezone.now() + timezone.timedelta(days=14)


class Organization(models.Model):
    """An organization represents a tenant in our multi-tenant SaaS.

    Each organization has its own integrations, users, and settings.
    Organizations are the primary billing and access control entity.

    Attributes:
        uuid: Unique identifier for webhook URLs.
        name: Display name of the organization.
        slug: URL-friendly identifier.
        shop_domain: Associated Shopify domain.
        subscription_plan: Current billing plan.
        subscription_status: Current subscription state.
    """

    STRIPE_PLANS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("free", "Free Plan"),
        ("trial", "14-Day Trial"),
        ("basic", "Basic Plan - $29/month"),
        ("pro", "Pro Plan - $99/month"),
        ("enterprise", "Enterprise Plan - $299/month"),
    )

    STATUS_CHOICES: ClassVar[tuple[tuple[str, str], ...]] = (
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

    def __str__(self) -> str:
        """Return string representation of the organization.

        Returns:
            Organization name and shop domain.
        """
        return f"{self.name} ({self.shop_domain})"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save the organization, generating a unique slug if needed.

        Args:
            *args: Positional arguments for parent save method.
            **kwargs: Keyword arguments for parent save method.
        """
        if not self.slug:
            self._generate_unique_slug()
        super().save(*args, **kwargs)

    def _generate_unique_slug(self) -> None:
        """Generate a unique slug in a race-condition-safe manner.

        Uses atomic transactions and select_for_update to prevent
        duplicate slugs in concurrent requests.
        """
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
    def webhook_token(self) -> str:
        """Return UUID as webhook token for URL obfuscation.

        Returns:
            String representation of the UUID.
        """
        return str(self.uuid)

    @property
    def is_trial(self) -> bool:
        """Check if organization is on trial.

        Returns:
            True if on trial, False otherwise.
        """
        return self.subscription_status == "trial"

    @property
    def is_active(self) -> bool:
        """Check if organization is active.

        Returns:
            True if active or on trial, False otherwise.
        """
        return self.subscription_status in ["active", "trial"]


class OrganizationUser(models.Model):
    """Junction table for organization membership with roles.

    A user can belong to multiple organizations with different roles.
    This enables multi-organization membership for enterprise users.

    Attributes:
        user: The Django user.
        organization: The organization they belong to.
        role: Their role within the organization.
        is_active: Whether membership is currently active.
    """

    ROLE_CHOICES: ClassVar[tuple[tuple[str, str], ...]] = (
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

    def __str__(self) -> str:
        """Return string representation of the membership.

        Returns:
            Username, organization name, and role.
        """
        return f"{self.user.username} - {self.organization.name} ({self.role})"


class Integration(models.Model):
    """Integrations for organizations.

    Supports both customer payment providers and workspace-specific
    notification integrations. Each organization can have one of each type.

    Attributes:
        organization: The owning organization.
        integration_type: Type of integration (stripe, shopify, etc.).
        oauth_credentials: OAuth tokens and credentials.
        webhook_secret: Secret for webhook validation.
        is_active: Whether the integration is currently enabled.
    """

    INTEGRATION_TYPES: ClassVar[tuple[tuple[str, str], ...]] = (
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

    def __str__(self) -> str:
        """Return string representation of the integration.

        Returns:
            Organization name and integration type display.
        """
        return f"{self.organization.name} - {self.get_integration_type_display()}"

    @property
    def slack_team_id(self) -> str | None:
        """Get Slack team ID from OAuth credentials.

        Returns:
            Slack team ID or None if not available.
        """
        return self.oauth_credentials.get("team", {}).get("id")

    @property
    def slack_channel(self) -> str:
        """Get Slack channel from integration settings.

        Returns:
            Slack channel name, defaults to #general.
        """
        return self.integration_settings.get("channel", "#general")

    @property
    def slack_bot_token(self) -> str | None:
        """Get Slack bot token from OAuth credentials.

        Returns:
            Slack bot token or None if not available.
        """
        return self.oauth_credentials.get("access_token")


class GlobalBillingIntegration(models.Model):
    """Global integrations for Notipus's own billing and authentication.

    These are not tied to any specific organization and are used for
    platform-wide functionality like Stripe billing for Notipus itself.

    Attributes:
        integration_type: Type of global integration.
        oauth_credentials: OAuth tokens and credentials.
        webhook_secret: Secret for webhook validation.
        is_active: Whether the integration is enabled.
    """

    INTEGRATION_TYPES: ClassVar[tuple[tuple[str, str], ...]] = (
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

    def __str__(self) -> str:
        """Return string representation of the global integration.

        Returns:
            Integration type display name.
        """
        return f"Global {self.get_integration_type_display()}"


def validate_domain(value: str) -> str:
    """Validate domain format and return cleaned domain.

    Removes protocol prefixes and validates the domain format
    against a standard domain name pattern.

    Args:
        value: Raw domain input string.

    Returns:
        Cleaned and validated domain string.

    Raises:
        ValidationError: If domain format is invalid.
    """
    # Remove protocol if present and clean
    domain = (
        value.replace("https://", "").replace("http://", "").replace("www.", "").lower()
    )

    # Validate format - must have at least one dot for TLD
    domain_pattern = re.compile(
        r"^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
        r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$"
    )

    if not domain_pattern.match(domain):
        raise ValidationError("Enter a valid domain name.")

    return domain


class Company(models.Model):
    """Company model for storing enriched brand/company data.

    Used by DomainEnrichmentService to cache brand information
    retrieved from enrichment providers like Brandfetch.

    Attributes:
        name: Company display name.
        domain: Unique domain identifier.
        logo_url: URL to company logo.
        brand_info: JSON blob with additional brand data.
    """

    name = models.CharField(max_length=255, blank=True, default="")
    domain = models.CharField(max_length=255, unique=True, validators=[validate_domain])
    logo_url = models.URLField(max_length=500, blank=True, default="")
    brand_info = models.JSONField(default=dict, blank=True)

    class Meta:
        app_label = "core"
        verbose_name_plural = "Companies"

    def __str__(self) -> str:
        """Return string representation of the company.

        Returns:
            Company name (or domain) with domain in parentheses.
        """
        display_name = self.name or self.domain
        return f"{display_name} ({self.domain})"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save the company after validation.

        Args:
            *args: Positional arguments for parent save method.
            **kwargs: Keyword arguments for parent save method.
        """
        self.full_clean()  # This calls clean() and validators
        super().save(*args, **kwargs)

    def clean(self) -> None:
        """Clean and validate model fields.

        Ensures domain is properly formatted and validated.
        """
        # Clean and validate domain
        if self.domain:
            self.domain = validate_domain(self.domain)


class UsageLimit(models.Model):
    """Usage limits per subscription plan.

    Defines the monthly limits for registrations and notifications
    for each subscription plan tier.

    Attributes:
        plan: The subscription plan name.
        max_monthly_registrations: Maximum registrations per month.
        max_monthly_notifications: Maximum notifications per month.
    """

    plan = models.CharField(max_length=20, choices=Organization.STRIPE_PLANS)
    max_monthly_registrations = models.IntegerField()
    max_monthly_notifications = models.IntegerField()

    def __str__(self) -> str:
        """Return string representation of the usage limit.

        Returns:
            Plan name and registration limit.
        """
        return (
            f"{self.get_plan_display()} - "
            f"{self.max_monthly_registrations} registrations"
        )


class UserProfile(models.Model):
    """Extended user profile with organization membership.

    Links Django users to their primary organization and
    stores Slack integration data.

    Attributes:
        user: The associated Django user.
        slack_user_id: Slack user identifier.
        organization: Primary organization membership.
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    slack_user_id = models.CharField(max_length=255, unique=True)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)

    def __str__(self) -> str:
        """Return string representation of the user profile.

        Returns:
            Username and organization name.
        """
        return f"{self.user.username} ({self.organization.name})"


class NotificationSettings(models.Model):
    """Notification preferences for an organization.

    Allows organizations to customize which event types
    generate Slack notifications.

    Attributes:
        organization: The organization these settings belong to.
        notify_*: Boolean flags for each notification type.
    """

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

    def __str__(self) -> str:
        """Return string representation of notification settings.

        Returns:
            Organization name with settings label.
        """
        return f"Notification Settings for {self.organization.name}"


class Plan(models.Model):
    """Plan definitions with usage limits for organizations.

    Defines available subscription plans with their pricing,
    limits, and feature sets.

    Attributes:
        name: Internal plan identifier.
        display_name: Human-readable plan name.
        price_monthly: Monthly price in USD.
        max_users: Maximum users allowed.
        max_integrations: Maximum integrations allowed.
        features: List of included features.
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

    def __str__(self) -> str:
        """Return string representation of the plan.

        Returns:
            Plan display name.
        """
        return self.display_name


class WebAuthnCredential(models.Model):
    """Store WebAuthn credentials for passwordless authentication.

    Stores the public key and metadata for registered passkeys,
    enabling passwordless login via WebAuthn/FIDO2.

    Attributes:
        user: The user who owns this credential.
        credential_id: Base64-encoded credential ID.
        public_key: Base64-encoded public key.
        sign_count: Counter to detect credential cloning.
        name: User-friendly name for the credential.
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

    def __str__(self) -> str:
        """Return string representation of the credential.

        Returns:
            Username and credential name.
        """
        return f"{self.user.username} - {self.name}"


class WebAuthnChallenge(models.Model):
    """Temporary storage for WebAuthn challenges during authentication flow.

    Stores challenges for both registration and authentication flows,
    with automatic cleanup of expired challenges.

    Attributes:
        challenge: Base64-encoded challenge string.
        user: Associated user (null for registration challenges).
        challenge_type: Type of challenge (registration or authentication).
    """

    challenge = models.CharField(max_length=255, unique=True)  # Base64 encoded
    user = models.ForeignKey(
        "auth.User", on_delete=models.CASCADE, null=True, blank=True
    )  # Null for registration challenges
    created_at = models.DateTimeField(auto_now_add=True)

    # Challenge type
    CHALLENGE_TYPES: ClassVar[tuple[tuple[str, str], ...]] = (
        ("registration", "Registration"),
        ("authentication", "Authentication"),
        ("signup_registration", "Signup Registration"),
    )
    challenge_type = models.CharField(max_length=20, choices=CHALLENGE_TYPES)

    class Meta:
        app_label = "core"
        verbose_name = "WebAuthn Challenge"
        verbose_name_plural = "WebAuthn Challenges"

    def __str__(self) -> str:
        """Return string representation of the challenge.

        Returns:
            Challenge type and associated user (or Anonymous).
        """
        user_str = self.user.username if self.user else "Anonymous"
        return f"{self.challenge_type} challenge for {user_str}"
