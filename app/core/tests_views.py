import json
from unittest.mock import patch

from core.models import Organization, UserProfile
from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse


class NotificationSettingsViewsTest(TestCase):
    """Test notification settings views"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()

        # Create user and organization
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )

        self.organization = Organization.objects.create(
            slack_team_id="T123456",
            slack_domain="test.slack.com",
            name="Test Organization",
        )

        self.user_profile = UserProfile.objects.create(
            user=self.user,
            slack_user_id="U123456",
            slack_team_id="T123456",
            organization=self.organization,
        )

        # Notification settings are created automatically via signal
        self.notification_settings = self.organization.notification_settings

    def test_get_notification_settings_success(self):
        """Test successful retrieval of notification settings"""
        self.client.login(username="testuser", password="testpass123")

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
        User.objects.create_user(username="noprofile", password="testpass123")

        self.client.login(username="noprofile", password="testpass123")

        response = self.client.get(reverse("get_notification_settings"))

        self.assertEqual(response.status_code, 404)
        data = json.loads(response.content)
        self.assertEqual(data["error"], "User profile not found")

    def test_get_notification_settings_no_notification_settings(self):
        """Test getting settings when notification settings don't exist"""
        # Delete notification settings
        self.notification_settings.delete()

        self.client.login(username="testuser", password="testpass123")

        response = self.client.get(reverse("get_notification_settings"))

        self.assertEqual(response.status_code, 404)
        data = json.loads(response.content)
        self.assertEqual(data["error"], "Notification settings not found")

    def test_update_notification_settings_success(self):
        """Test successful update of notification settings"""
        self.client.login(username="testuser", password="testpass123")

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
        self.client.login(username="testuser", password="testpass123")

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
        self.client.login(username="testuser", password="testpass123")

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
        self.client.login(username="testuser", password="testpass123")

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
        self.client.login(username="testuser", password="testpass123")

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
        self.client.login(username="testuser", password="testpass123")

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
        self.client.login(username="testuser", password="testpass123")

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
        User.objects.create_user(username="noprofile", password="testpass123")

        self.client.login(username="noprofile", password="testpass123")

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

        self.client.login(username="testuser", password="testpass123")

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
        self.client.login(username="testuser", password="testpass123")

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
        self.client.login(username="testuser", password="testpass123")

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
        self.client.login(username="testuser", password="testpass123")

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
        self.client.login(username="testuser", password="testpass123")

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
