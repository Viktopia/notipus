"""Custom adapters for django-allauth social authentication.

This module provides custom adapters to enhance the social authentication
flow, particularly for Slack OAuth integration.
"""

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    """Custom adapter for social account authentication.

    This adapter automatically generates usernames from email addresses
    when users sign up via social providers like Slack, enabling a
    seamless signup flow without requiring manual username input.
    """

    def is_auto_signup_allowed(self, request, sociallogin):
        """Determine if auto-signup is allowed for this social login.

        Always returns True to skip the intermediate signup form,
        since we auto-generate usernames from email addresses.

        Args:
            request: The HTTP request object.
            sociallogin: The social login object.

        Returns:
            True to allow auto-signup without showing the form.
        """
        return True

    def populate_user(self, request, sociallogin, data):
        """Populate user instance with data from social provider.

        Args:
            request: The HTTP request object.
            sociallogin: The social login object containing provider data.
            data: Dictionary of user data from the social provider.

        Returns:
            User instance populated with social provider data.
        """
        user = super().populate_user(request, sociallogin, data)

        # Generate username from email if not already set
        if not user.username and user.email:
            base_username = user.email.split("@")[0]
            # Clean the username to remove invalid characters
            base_username = self._clean_username(base_username)
            user.username = self._generate_unique_username(base_username)

        return user

    def _clean_username(self, username: str) -> str:
        """Clean username to contain only valid characters.

        Args:
            username: The raw username string.

        Returns:
            Cleaned username with only alphanumeric characters and underscores.
        """
        import re

        # Keep only alphanumeric characters, underscores, and hyphens
        cleaned = re.sub(r"[^\w\-]", "", username)
        # Ensure it's not empty
        return cleaned or "user"

    def _generate_unique_username(self, base: str) -> str:
        """Generate a unique username based on a base string.

        Args:
            base: The base username to start from.

        Returns:
            A unique username that doesn't exist in the database.
        """
        from django.contrib.auth import get_user_model

        User = get_user_model()
        username = base
        counter = 1

        while User.objects.filter(username=username).exists():
            username = f"{base}{counter}"
            counter += 1

        return username
