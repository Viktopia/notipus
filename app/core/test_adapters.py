"""Tests for custom social account adapters.

This module tests the CustomSocialAccountAdapter that handles
automatic username generation during social OAuth signup.
"""

from unittest.mock import MagicMock, patch

import pytest
from core.adapters import CustomSocialAccountAdapter
from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase


class TestCustomSocialAccountAdapter(TestCase):
    """Test cases for CustomSocialAccountAdapter."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.adapter = CustomSocialAccountAdapter()
        self.factory = RequestFactory()

    def test_clean_username_removes_special_characters(self) -> None:
        """Test that special characters are removed from usernames."""
        assert self.adapter._clean_username("john.doe") == "johndoe"
        assert self.adapter._clean_username("user+test") == "usertest"
        assert self.adapter._clean_username("user@domain") == "userdomain"

    def test_clean_username_preserves_valid_characters(self) -> None:
        """Test that valid characters are preserved in usernames."""
        assert self.adapter._clean_username("john_doe") == "john_doe"
        assert self.adapter._clean_username("user-name") == "user-name"
        assert self.adapter._clean_username("user123") == "user123"

    def test_clean_username_returns_user_for_empty_result(self) -> None:
        """Test that 'user' is returned when cleaning results in empty string."""
        assert self.adapter._clean_username("@@@") == "user"
        assert self.adapter._clean_username("...") == "user"

    def test_generate_unique_username_no_conflict(self) -> None:
        """Test username generation when no conflicts exist."""
        username = self.adapter._generate_unique_username("testuser")
        assert username == "testuser"

    def test_generate_unique_username_with_conflict(self) -> None:
        """Test username generation increments counter on conflict."""
        # Create a user with the base username
        User.objects.create_user(username="existinguser", email="existing@test.com")

        username = self.adapter._generate_unique_username("existinguser")
        assert username == "existinguser1"

    def test_generate_unique_username_with_multiple_conflicts(self) -> None:
        """Test username generation handles multiple conflicts."""
        # Create users with base username and first increment
        User.objects.create_user(username="taken", email="taken@test.com")
        User.objects.create_user(username="taken1", email="taken1@test.com")
        User.objects.create_user(username="taken2", email="taken2@test.com")

        username = self.adapter._generate_unique_username("taken")
        assert username == "taken3"

    def test_populate_user_generates_username_from_email(self) -> None:
        """Test that populate_user generates username from email."""
        request = self.factory.get("/")
        sociallogin = MagicMock()
        data = {
            "email": "newuser@example.com",
            "first_name": "New",
            "last_name": "User",
        }

        # Create a real User object without username
        mock_user = User(email="newuser@example.com", username="")

        with patch(
            "core.adapters.DefaultSocialAccountAdapter.populate_user",
            return_value=mock_user,
        ):
            adapter = CustomSocialAccountAdapter()
            result = adapter.populate_user(request, sociallogin, data)

        assert result.username == "newuser"

    def test_populate_user_preserves_existing_username(self) -> None:
        """Test that populate_user doesn't override existing username."""
        request = self.factory.get("/")
        sociallogin = MagicMock()
        data = {"email": "test@example.com"}

        # Create a real User object with username already set
        mock_user = User(email="test@example.com", username="already_set")

        with patch(
            "core.adapters.DefaultSocialAccountAdapter.populate_user",
            return_value=mock_user,
        ):
            adapter = CustomSocialAccountAdapter()
            result = adapter.populate_user(request, sociallogin, data)

        # Username should remain unchanged
        assert result.username == "already_set"


@pytest.mark.django_db
class TestCustomSocialAccountAdapterIntegration:
    """Integration tests for CustomSocialAccountAdapter."""

    def test_adapter_integrates_with_allauth(self) -> None:
        """Test that the adapter can be instantiated and used."""
        adapter = CustomSocialAccountAdapter()
        assert adapter is not None
        assert hasattr(adapter, "populate_user")
        assert hasattr(adapter, "_generate_unique_username")
        assert hasattr(adapter, "_clean_username")
