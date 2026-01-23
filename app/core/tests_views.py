import json
from unittest.mock import MagicMock, Mock, patch

from core.models import Integration, UserProfile, Workspace
from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse


class NotificationSettingsViewsTest(TestCase):
    """Test notification settings views"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()

        # Create user and workspace
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )

        self.workspace = Workspace.objects.create(
            name="Test Workspace",
            shop_domain="test.myshopify.com",
        )

        self.user_profile = UserProfile.objects.create(
            user=self.user,
            slack_user_id="U123456",
            workspace=self.workspace,
        )

        # Notification settings are created automatically via signal
        self.notification_settings = self.workspace.notification_settings

    def test_get_notification_settings_success(self):
        """Test successful retrieval of notification settings"""
        self.client.force_login(self.user)

        response = self.client.get(reverse("get_notification_settings"))

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        # Check all fields are present and have correct default values
        expected_fields = [
            "notify_payment_success",
            "notify_payment_failure",
            "notify_subscription_created",
            "notify_subscription_updated",
            "notify_subscription_canceled",
            "notify_trial_ending",
            "notify_trial_expired",
            "notify_customer_updated",
            "notify_signups",
            "notify_shopify_order_created",
            "notify_shopify_order_updated",
            "notify_shopify_order_paid",
        ]

        for field in expected_fields:
            self.assertIn(field, data)
            self.assertTrue(data[field])  # All default to True

    def test_get_notification_settings_unauthenticated(self):
        """Test getting settings without authentication"""
        response = self.client.get(reverse("get_notification_settings"))

        # Should redirect to login
        self.assertEqual(response.status_code, 302)

    def test_get_notification_settings_no_user_profile(self):
        """Test getting settings for user without profile"""
        # Create user without profile
        noprofile_user = User.objects.create_user(
            username="noprofile", password="testpass123"
        )

        self.client.force_login(noprofile_user)

        response = self.client.get(reverse("get_notification_settings"))

        self.assertEqual(response.status_code, 404)
        data = json.loads(response.content)
        self.assertEqual(data["error"], "User profile not found")

    def test_get_notification_settings_no_notification_settings(self):
        """Test getting settings when notification settings don't exist"""
        # Delete notification settings
        self.notification_settings.delete()

        self.client.force_login(self.user)

        response = self.client.get(reverse("get_notification_settings"))

        self.assertEqual(response.status_code, 404)
        data = json.loads(response.content)
        self.assertEqual(data["error"], "Notification settings not found")

    def test_update_notification_settings_success(self):
        """Test successful update of notification settings"""
        self.client.force_login(self.user)

        update_data = {
            "notify_payment_success": False,
            "notify_trial_ending": False,
            "notify_shopify_order_created": True,
        }

        response = self.client.post(
            reverse("update_notification_settings"),
            data=json.dumps(update_data),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["status"], "success")
        self.assertIn("updated_fields", data)

        # Check database was updated
        self.notification_settings.refresh_from_db()
        self.assertFalse(self.notification_settings.notify_payment_success)
        self.assertFalse(self.notification_settings.notify_trial_ending)
        self.assertTrue(self.notification_settings.notify_shopify_order_created)
        # Other fields should remain True
        self.assertTrue(self.notification_settings.notify_payment_failure)

    def test_update_notification_settings_partial_update(self):
        """Test partial update of notification settings"""
        self.client.force_login(self.user)

        update_data = {
            "notify_payment_success": False,
        }

        response = self.client.post(
            reverse("update_notification_settings"),
            data=json.dumps(update_data),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["updated_fields"], ["notify_payment_success"])

        # Check only specified field was updated
        self.notification_settings.refresh_from_db()
        self.assertFalse(self.notification_settings.notify_payment_success)
        self.assertTrue(self.notification_settings.notify_payment_failure)

    def test_update_notification_settings_empty_data(self):
        """Test update with empty data"""
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("update_notification_settings"),
            data=json.dumps({}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["updated_fields"], [])

    def test_update_notification_settings_invalid_field(self):
        """Test update with invalid field name"""
        self.client.force_login(self.user)

        update_data = {
            "invalid_field": False,
        }

        response = self.client.post(
            reverse("update_notification_settings"),
            data=json.dumps(update_data),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content)
        self.assertIn("is not allowed to be updated", data["error"])

    def test_update_notification_settings_invalid_value_type(self):
        """Test update with invalid value type"""
        self.client.force_login(self.user)

        update_data = {
            "notify_payment_success": "not_boolean",
        }

        response = self.client.post(
            reverse("update_notification_settings"),
            data=json.dumps(update_data),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content)
        self.assertIn("must be a boolean value", data["error"])

    def test_update_notification_settings_invalid_json(self):
        """Test update with invalid JSON"""
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("update_notification_settings"),
            data="invalid json",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content)
        self.assertEqual(data["error"], "Invalid JSON data")

    def test_update_notification_settings_wrong_method(self):
        """Test update with wrong HTTP method"""
        self.client.force_login(self.user)

        response = self.client.get(reverse("update_notification_settings"))

        self.assertEqual(response.status_code, 405)
        data = json.loads(response.content)
        self.assertEqual(data["error"], "Method not allowed")

    def test_update_notification_settings_unauthenticated(self):
        """Test update without authentication"""
        update_data = {
            "notify_payment_success": False,
        }

        response = self.client.post(
            reverse("update_notification_settings"),
            data=json.dumps(update_data),
            content_type="application/json",
        )

        # Should redirect to login
        self.assertEqual(response.status_code, 302)

    def test_update_notification_settings_no_user_profile(self):
        """Test update for user without profile"""
        # Create user without profile
        noprofile_user = User.objects.create_user(
            username="noprofile", password="testpass123"
        )

        self.client.force_login(noprofile_user)

        update_data = {
            "notify_payment_success": False,
        }

        response = self.client.post(
            reverse("update_notification_settings"),
            data=json.dumps(update_data),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)
        data = json.loads(response.content)
        self.assertEqual(data["error"], "User profile not found")

    def test_update_notification_settings_no_notification_settings(self):
        """Test update when notification settings don't exist"""
        # Delete notification settings
        self.notification_settings.delete()

        self.client.force_login(self.user)

        update_data = {
            "notify_payment_success": False,
        }

        response = self.client.post(
            reverse("update_notification_settings"),
            data=json.dumps(update_data),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)
        data = json.loads(response.content)
        self.assertEqual(data["error"], "Notification settings not found")

    @patch("core.views.logger")
    def test_get_notification_settings_internal_error(self, mock_logger):
        """Test handling of internal errors in get view"""
        self.client.force_login(self.user)

        # Mock to raise an exception
        with patch.object(
            self.user, "userprofile", side_effect=Exception("Database error")
        ):
            response = self.client.get(reverse("get_notification_settings"))

            self.assertEqual(response.status_code, 500)
            data = json.loads(response.content)
            self.assertEqual(data["error"], "Internal server error")

            mock_logger.error.assert_called_once()

    @patch("core.views.logger")
    def test_update_notification_settings_internal_error(self, mock_logger):
        """Test handling of internal errors in update view"""
        self.client.force_login(self.user)

        update_data = {
            "notify_payment_success": False,
        }

        # Mock to raise an exception
        with patch.object(
            self.user, "userprofile", side_effect=Exception("Database error")
        ):
            response = self.client.post(
                reverse("update_notification_settings"),
                data=json.dumps(update_data),
                content_type="application/json",
            )

            self.assertEqual(response.status_code, 500)
            data = json.loads(response.content)
            self.assertEqual(data["error"], "Internal server error")

            mock_logger.error.assert_called_once()

    def test_update_notification_settings_all_fields(self):
        """Test updating all notification settings fields"""
        self.client.force_login(self.user)

        # Update all fields to False
        update_data = {
            "notify_payment_success": False,
            "notify_payment_failure": False,
            "notify_subscription_created": False,
            "notify_subscription_updated": False,
            "notify_subscription_canceled": False,
            "notify_trial_ending": False,
            "notify_trial_expired": False,
            "notify_customer_updated": False,
            "notify_signups": False,
            "notify_shopify_order_created": False,
            "notify_shopify_order_updated": False,
            "notify_shopify_order_paid": False,
        }

        response = self.client.post(
            reverse("update_notification_settings"),
            data=json.dumps(update_data),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(len(data["updated_fields"]), 12)

        # Check all fields were updated
        self.notification_settings.refresh_from_db()
        for field_name in update_data.keys():
            self.assertFalse(getattr(self.notification_settings, field_name))

    def test_update_notification_settings_mixed_values(self):
        """Test updating with mixed boolean values"""
        self.client.force_login(self.user)

        update_data = {
            "notify_payment_success": False,
            "notify_payment_failure": True,
            "notify_trial_ending": False,
            "notify_signups": True,
        }

        response = self.client.post(
            reverse("update_notification_settings"),
            data=json.dumps(update_data),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)

        # Check specific field values
        self.notification_settings.refresh_from_db()
        self.assertFalse(self.notification_settings.notify_payment_success)
        self.assertTrue(self.notification_settings.notify_payment_failure)
        self.assertFalse(self.notification_settings.notify_trial_ending)
        self.assertTrue(self.notification_settings.notify_signups)


class StripeConnectOAuthViewsTest(TestCase):
    """Tests for Stripe Connect OAuth integration views."""

    def setUp(self) -> None:
        """Set up test data."""
        self.client = Client()

        # Create user and workspace
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )

        self.workspace = Workspace.objects.create(
            name="Test Workspace",
            shop_domain="test.myshopify.com",
        )

        self.user_profile = UserProfile.objects.create(
            user=self.user,
            slack_user_id="U123456",
            workspace=self.workspace,
        )

    def test_integrate_stripe_redirects_to_stripe_connect(self) -> None:
        """Test that integrate_stripe redirects to stripe_connect."""
        self.client.force_login(self.user)

        response = self.client.get(reverse("core:integrate_stripe"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("core:stripe_connect"))

    def test_integrate_stripe_requires_authentication(self) -> None:
        """Test that integrate_stripe requires authentication."""
        response = self.client.get(reverse("core:integrate_stripe"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    @patch("core.views.integrations.stripe.settings")
    def test_stripe_connect_redirects_to_oauth(self, mock_settings: Mock) -> None:
        """Test that stripe_connect redirects to Stripe OAuth URL."""
        mock_settings.STRIPE_CONNECT_CLIENT_ID = "ca_test123"
        mock_settings.STRIPE_CONNECT_REDIRECT_URI = "http://localhost/callback/"

        response = self.client.get(reverse("core:stripe_connect"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("connect.stripe.com/oauth/authorize", response.url)
        self.assertIn("ca_test123", response.url)
        self.assertIn("scope=read_write", response.url)

    @patch("core.views.integrations.stripe.settings")
    def test_stripe_connect_without_client_id(self, mock_settings: Mock) -> None:
        """Test stripe_connect when client_id is not configured."""
        mock_settings.STRIPE_CONNECT_CLIENT_ID = ""

        response = self.client.get(reverse("core:stripe_connect"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("core:integrations"))

    def test_stripe_connect_callback_without_code(self) -> None:
        """Test callback without authorization code."""
        self.client.force_login(self.user)

        response = self.client.get(reverse("core:stripe_connect_callback"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("core:integrations"))

    def test_stripe_connect_callback_with_error(self) -> None:
        """Test callback with OAuth error."""
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("core:stripe_connect_callback"),
            {"error": "access_denied", "error_description": "User denied access"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("core:integrations"))

    @patch("core.views.integrations.stripe.stripe.WebhookEndpoint.create")
    @patch("core.views.integrations.stripe.requests.post")
    @patch("core.views.integrations.stripe.settings")
    def test_stripe_connect_callback_success(
        self,
        mock_settings: Mock,
        mock_post: Mock,
        mock_webhook_create: Mock,
    ) -> None:
        """Test successful OAuth callback creates integration."""
        self.client.force_login(self.user)

        # Configure settings
        mock_settings.STRIPE_SECRET_KEY = "sk_test_123"
        mock_settings.BASE_URL = "http://localhost:8000"

        # Mock token exchange response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "access_token": "sk_test_connected_123",
            "stripe_user_id": "acct_test123",
            "refresh_token": "rt_test123",
        }
        mock_post.return_value = mock_response

        # Mock webhook endpoint creation
        mock_webhook = MagicMock()
        mock_webhook.id = "we_test123"
        mock_webhook.secret = "whsec_test123"
        mock_webhook_create.return_value = mock_webhook

        response = self.client.get(
            reverse("core:stripe_connect_callback"),
            {"code": "ac_test123"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("core:integrations"))

        # Verify integration was created
        integration = Integration.objects.get(
            workspace=self.workspace,
            integration_type="stripe_customer",
        )
        self.assertTrue(integration.is_active)
        self.assertEqual(integration.webhook_secret, "whsec_test123")
        self.assertEqual(
            integration.oauth_credentials["access_token"], "sk_test_connected_123"
        )
        self.assertEqual(
            integration.integration_settings["webhook_endpoint_id"], "we_test123"
        )

    @patch("core.views.integrations.stripe.requests.post")
    @patch("core.views.integrations.stripe.settings")
    def test_stripe_connect_callback_token_exchange_error(
        self,
        mock_settings: Mock,
        mock_post: Mock,
    ) -> None:
        """Test callback when token exchange fails."""
        self.client.force_login(self.user)

        mock_settings.STRIPE_SECRET_KEY = "sk_test_123"

        # Mock error response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "error": "invalid_grant",
            "error_description": "Authorization code expired",
        }
        mock_post.return_value = mock_response

        response = self.client.get(
            reverse("core:stripe_connect_callback"),
            {"code": "expired_code"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("core:integrations"))

        # Verify no integration was created
        self.assertFalse(
            Integration.objects.filter(
                workspace=self.workspace,
                integration_type="stripe_customer",
            ).exists()
        )

    def test_disconnect_stripe_requires_post(self) -> None:
        """Test that disconnect_stripe requires POST method."""
        self.client.force_login(self.user)

        response = self.client.get(reverse("core:disconnect_stripe"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("core:integrations"))

    def test_disconnect_stripe_no_integration(self) -> None:
        """Test disconnect when no integration exists."""
        self.client.force_login(self.user)

        response = self.client.post(reverse("core:disconnect_stripe"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("core:integrations"))

    @patch("core.views.integrations.stripe.stripe.WebhookEndpoint.delete")
    def test_disconnect_stripe_success(self, mock_webhook_delete: Mock) -> None:
        """Test successful Stripe disconnection."""
        self.client.force_login(self.user)

        # Create active integration
        integration = Integration.objects.create(
            workspace=self.workspace,
            integration_type="stripe_customer",
            oauth_credentials={
                "access_token": "sk_test_123",
                "stripe_user_id": "acct_test123",
            },
            webhook_secret="whsec_test123",
            integration_settings={
                "webhook_endpoint_id": "we_test123",
            },
            is_active=True,
        )

        response = self.client.post(reverse("core:disconnect_stripe"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("core:integrations"))

        # Verify integration was deactivated
        integration.refresh_from_db()
        self.assertFalse(integration.is_active)

        # Verify webhook endpoint deletion was attempted
        mock_webhook_delete.assert_called_once_with(
            "we_test123",
            api_key="sk_test_123",
        )

    @patch("core.views.integrations.stripe.stripe.WebhookEndpoint.delete")
    def test_disconnect_stripe_webhook_delete_fails(
        self, mock_webhook_delete: Mock
    ) -> None:
        """Test disconnection proceeds even if webhook deletion fails."""
        import stripe

        self.client.force_login(self.user)

        # Create active integration
        integration = Integration.objects.create(
            workspace=self.workspace,
            integration_type="stripe_customer",
            oauth_credentials={
                "access_token": "sk_test_123",
                "stripe_user_id": "acct_test123",
            },
            webhook_secret="whsec_test123",
            integration_settings={
                "webhook_endpoint_id": "we_test123",
            },
            is_active=True,
        )

        # Mock webhook deletion to fail
        mock_webhook_delete.side_effect = stripe.error.InvalidRequestError(
            "Webhook endpoint not found", param=None
        )

        response = self.client.post(reverse("core:disconnect_stripe"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("core:integrations"))

        # Integration should still be deactivated
        integration.refresh_from_db()
        self.assertFalse(integration.is_active)
