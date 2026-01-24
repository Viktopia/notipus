"""Tests for Workspace model validation.

This module contains tests for the Workspace model including:
- Subscription plan and status validation
- Trial status constraints
"""

import pytest
from core.models import Workspace
from django.core.exceptions import ValidationError


@pytest.mark.django_db
class TestWorkspaceSubscriptionValidation:
    """Tests for Workspace subscription plan and status validation."""

    def test_free_plan_with_trial_status_raises_validation_error(self) -> None:
        """Test that free plan cannot have trial status.

        Free plan users should have 'active' status, not 'trial'.
        Trial status is only valid for paid plans.
        """
        workspace = Workspace(
            name="Test Workspace",
            subscription_plan="free",
            subscription_status="trial",
        )

        with pytest.raises(ValidationError) as exc_info:
            workspace.full_clean()

        assert "Free plan cannot have trial status" in str(exc_info.value)

    def test_free_plan_with_trial_status_save_raises_validation_error(self) -> None:
        """Test that saving free plan with trial status raises ValidationError.

        The save() method should enforce validation via full_clean().
        """
        workspace = Workspace(
            name="Test Workspace Save",
            subscription_plan="free",
            subscription_status="trial",
        )

        with pytest.raises(ValidationError) as exc_info:
            workspace.save()

        assert "Free plan cannot have trial status" in str(exc_info.value)

    def test_free_plan_with_active_status_succeeds(self) -> None:
        """Test that free plan with active status is valid."""
        workspace = Workspace(
            name="Test Workspace Free Active",
            subscription_plan="free",
            subscription_status="active",
        )

        # Should not raise
        workspace.full_clean()
        workspace.save()

        assert workspace.pk is not None
        assert workspace.subscription_plan == "free"
        assert workspace.subscription_status == "active"

    def test_basic_plan_with_trial_status_succeeds(self) -> None:
        """Test that basic plan can have trial status.

        Paid plans (basic, pro, enterprise) can have trial status.
        """
        workspace = Workspace(
            name="Test Workspace Basic Trial",
            subscription_plan="basic",
            subscription_status="trial",
        )

        # Should not raise
        workspace.full_clean()
        workspace.save()

        assert workspace.pk is not None
        assert workspace.subscription_plan == "basic"
        assert workspace.subscription_status == "trial"

    def test_pro_plan_with_trial_status_succeeds(self) -> None:
        """Test that pro plan can have trial status."""
        workspace = Workspace(
            name="Test Workspace Pro Trial",
            subscription_plan="pro",
            subscription_status="trial",
        )

        # Should not raise
        workspace.full_clean()
        workspace.save()

        assert workspace.pk is not None
        assert workspace.subscription_plan == "pro"
        assert workspace.subscription_status == "trial"

    def test_enterprise_plan_with_trial_status_succeeds(self) -> None:
        """Test that enterprise plan can have trial status."""
        workspace = Workspace(
            name="Test Workspace Enterprise Trial",
            subscription_plan="enterprise",
            subscription_status="trial",
        )

        # Should not raise
        workspace.full_clean()
        workspace.save()

        assert workspace.pk is not None
        assert workspace.subscription_plan == "enterprise"
        assert workspace.subscription_status == "trial"

    def test_paid_plan_with_active_status_succeeds(self) -> None:
        """Test that paid plans with active status are valid."""
        workspace = Workspace(
            name="Test Workspace Basic Active",
            subscription_plan="basic",
            subscription_status="active",
        )

        # Should not raise
        workspace.full_clean()
        workspace.save()

        assert workspace.pk is not None
        assert workspace.subscription_plan == "basic"
        assert workspace.subscription_status == "active"
