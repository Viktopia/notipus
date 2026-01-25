"""Pytest fixtures for core app tests.

This module provides reusable fixtures for:
- Users with different roles (owner, admin, user)
- Workspaces with various configurations
- Plans with different user limits
- Workspace invitations
"""

from datetime import timedelta

import pytest
from core.models import Plan, Workspace, WorkspaceInvitation, WorkspaceMember
from django.contrib.auth.models import User


@pytest.fixture
def pro_plan(db) -> Plan:
    """Get or create a Pro plan with 5 max users."""
    plan, _ = Plan.objects.get_or_create(
        name="pro",
        defaults={
            "display_name": "Pro",
            "price_monthly": 49.00,
            "max_users": 5,
            "is_active": True,
        },
    )
    # Ensure max_users is set correctly for tests
    if plan.max_users != 5:
        plan.max_users = 5
        plan.save()
    return plan


@pytest.fixture
def starter_plan(db) -> Plan:
    """Get or create a Basic plan with 2 max users for testing invite limits.

    Note: Named 'starter_plan' for backwards compatibility with existing tests,
    but creates a Plan with name='basic' to match valid
    Workspace.subscription_plan choices.
    """
    plan, _ = Plan.objects.get_or_create(
        name="basic",
        defaults={
            "display_name": "Basic",
            "price_monthly": 29.00,
            "max_users": 2,
            "is_active": True,
        },
    )
    # Ensure max_users is set correctly for tests
    if plan.max_users != 2:
        plan.max_users = 2
        plan.save()
    return plan


@pytest.fixture
def free_plan(db) -> Plan:
    """Get or create a Free plan with 1 max user."""
    plan, _ = Plan.objects.get_or_create(
        name="free",
        defaults={
            "display_name": "Free",
            "price_monthly": 0.00,
            "max_users": 1,
            "is_active": True,
        },
    )
    # Ensure max_users is set correctly for tests
    if plan.max_users != 1:
        plan.max_users = 1
        plan.save()
    return plan


@pytest.fixture
def workspace(db, pro_plan) -> Workspace:
    """Create a test workspace with Pro plan on trial."""
    return Workspace.objects.create(
        name="Test Workspace",
        subscription_plan="pro",
        subscription_status="trial",
    )


@pytest.fixture
def starter_workspace(db, starter_plan) -> Workspace:
    """Create a test workspace with Basic plan (limited users) on trial.

    Note: The starter_plan fixture creates a Plan record for testing,
    but Workspace.subscription_plan uses the basic tier for validation.
    """
    return Workspace.objects.create(
        name="Starter Workspace",
        subscription_plan="basic",
        subscription_status="trial",
    )


@pytest.fixture
def owner_user(db) -> User:
    """Create an owner user."""
    return User.objects.create_user(
        username="testowner",
        email="owner@example.com",
        password="testpass123",
    )


@pytest.fixture
def admin_user(db) -> User:
    """Create an admin user."""
    return User.objects.create_user(
        username="testadmin",
        email="admin@example.com",
        password="testpass123",
    )


@pytest.fixture
def regular_user(db) -> User:
    """Create a regular user."""
    return User.objects.create_user(
        username="testuser",
        email="user@example.com",
        password="testpass123",
    )


@pytest.fixture
def second_owner_user(db) -> User:
    """Create a second owner user for testing owner-owner interactions."""
    return User.objects.create_user(
        username="testowner2",
        email="owner2@example.com",
        password="testpass123",
    )


@pytest.fixture
def owner_member(db, workspace, owner_user) -> WorkspaceMember:
    """Create an owner membership."""
    return WorkspaceMember.objects.create(
        user=owner_user,
        workspace=workspace,
        role="owner",
    )


@pytest.fixture
def admin_member(db, workspace, admin_user) -> WorkspaceMember:
    """Create an admin membership."""
    return WorkspaceMember.objects.create(
        user=admin_user,
        workspace=workspace,
        role="admin",
    )


@pytest.fixture
def user_member(db, workspace, regular_user) -> WorkspaceMember:
    """Create a regular user membership."""
    return WorkspaceMember.objects.create(
        user=regular_user,
        workspace=workspace,
        role="user",
    )


@pytest.fixture
def second_owner_member(db, workspace, second_owner_user) -> WorkspaceMember:
    """Create a second owner membership."""
    return WorkspaceMember.objects.create(
        user=second_owner_user,
        workspace=workspace,
        role="owner",
    )


@pytest.fixture
def workspace_with_members(
    db, workspace, owner_member, admin_member, user_member
) -> Workspace:
    """Create a workspace with owner, admin, and user members."""
    return workspace


@pytest.fixture
def pending_invitation(db, workspace, owner_user) -> WorkspaceInvitation:
    """Create a pending invitation."""
    from django.utils import timezone

    return WorkspaceInvitation.objects.create(
        workspace=workspace,
        email="invitee@example.com",
        role="admin",
        invited_by=owner_user,
        expires_at=timezone.now() + timedelta(days=7),
    )


@pytest.fixture
def expired_invitation(db, workspace, owner_user) -> WorkspaceInvitation:
    """Create an expired invitation."""
    from django.utils import timezone

    return WorkspaceInvitation.objects.create(
        workspace=workspace,
        email="expired@example.com",
        role="user",
        invited_by=owner_user,
        expires_at=timezone.now() - timedelta(days=1),
    )


@pytest.fixture
def invitee_user(db) -> User:
    """Create a user matching a pending invitation email."""
    return User.objects.create_user(
        username="invitee",
        email="invitee@example.com",
        password="testpass123",
    )


@pytest.fixture
def authenticated_owner_client(db, client, owner_user, owner_member):
    """Return a client logged in as workspace owner."""
    client.force_login(owner_user)
    return client


@pytest.fixture
def authenticated_admin_client(db, client, admin_user, admin_member):
    """Return a client logged in as workspace admin."""
    client.force_login(admin_user)
    return client


@pytest.fixture
def authenticated_user_client(db, client, regular_user, user_member):
    """Return a client logged in as regular workspace user."""
    client.force_login(regular_user)
    return client
