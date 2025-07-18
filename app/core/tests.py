from django.test import TestCase
from django.core.exceptions import ValidationError

from .models import Organization, Company, NotificationSettings, validate_domain


class ValidateDomainTest(TestCase):
    """Test domain validation function"""

    def test_valid_domains(self):
        """Test valid domain formats"""
        valid_domains = [
            "example.com",
            "sub.example.com",
            "test-site.co.uk",
            "my-company.org",
            "shop.mystore.com",
        ]

        for domain in valid_domains:
            with self.subTest(domain=domain):
                result = validate_domain(domain)
                self.assertIsInstance(result, str)
                self.assertTrue(len(result) > 0)

    def test_domain_cleaning(self):
        """Test that protocols and www are removed"""
        test_cases = [
            ("https://example.com", "example.com"),
            ("http://www.example.com", "example.com"),
            ("www.example.com", "example.com"),
            ("EXAMPLE.COM", "example.com"),
        ]

        for input_domain, expected in test_cases:
            with self.subTest(input_domain=input_domain):
                result = validate_domain(input_domain)
                self.assertEqual(result, expected)

    def test_invalid_domains(self):
        """Test invalid domain formats"""
        invalid_domains = [
            "invalid",
            ".com",
            "example.",
            "ex ample.com",
            "example..com",
            "",
            "localhost",
            "192.168.1.1",
        ]

        for domain in invalid_domains:
            with self.subTest(domain=domain):
                with self.assertRaises(ValidationError):
                    validate_domain(domain)


class CompanyModelTest(TestCase):
    """Test Company model"""

    def test_create_company_valid_domain(self):
        """Test creating company with valid domain"""
        company = Company.objects.create(domain="example.com", name="Example Company")

        self.assertEqual(company.domain, "example.com")
        self.assertEqual(company.name, "Example Company")
        self.assertIsNotNone(company.created_at)
        self.assertIsNotNone(company.updated_at)

    def test_company_str_with_name(self):
        """Test string representation with name"""
        company = Company.objects.create(domain="example.com", name="Example Company")
        self.assertEqual(str(company), "Example Company (example.com)")

    def test_company_str_without_name(self):
        """Test string representation without name"""
        company = Company.objects.create(domain="example.com")
        self.assertEqual(str(company), "example.com")

    def test_company_domain_unique(self):
        """Test domain uniqueness constraint"""
        Company.objects.create(domain="example.com")

        with self.assertRaises(Exception):  # IntegrityError
            Company.objects.create(domain="example.com")

    def test_company_domain_validation_on_save(self):
        """Test domain validation on save"""
        company = Company(domain="invalid-domain")

        with self.assertRaises(ValidationError):
            company.save()

    def test_company_clean_method(self):
        """Test clean method normalizes domain"""
        company = Company(domain="HTTPS://WWW.EXAMPLE.COM")
        company.clean()
        self.assertEqual(company.domain, "example.com")

    def test_brand_info_default(self):
        """Test brand_info defaults to empty dict"""
        company = Company.objects.create(domain="example.com")
        self.assertEqual(company.brand_info, {})

    def test_optional_fields(self):
        """Test optional fields can be None/blank"""
        company = Company.objects.create(domain="example.com")
        self.assertIsNone(company.name)
        self.assertIsNone(company.logo_url)


class NotificationSettingsModelTest(TestCase):
    """Test NotificationSettings model"""

    def setUp(self):
        """Set up test data"""
        self.organization = Organization.objects.create(
            slack_team_id="T123456",
            slack_domain="test.slack.com",
            name="Test Organization",
        )

    def test_create_notification_settings(self):
        """Test creating notification settings"""
        # Get the settings that were auto-created by signal
        settings = self.organization.notification_settings

        # Test all default values are True
        self.assertTrue(settings.notify_payment_success)
        self.assertTrue(settings.notify_payment_failure)
        self.assertTrue(settings.notify_subscription_created)
        self.assertTrue(settings.notify_subscription_updated)
        self.assertTrue(settings.notify_subscription_canceled)
        self.assertTrue(settings.notify_trial_ending)
        self.assertTrue(settings.notify_trial_expired)
        self.assertTrue(settings.notify_customer_updated)
        self.assertTrue(settings.notify_signups)
        self.assertTrue(settings.notify_shopify_order_created)
        self.assertTrue(settings.notify_shopify_order_updated)
        self.assertTrue(settings.notify_shopify_order_paid)

    def test_notification_settings_str(self):
        """Test string representation"""
        settings = self.organization.notification_settings
        expected = f"Notification Settings for {self.organization.name}"
        self.assertEqual(str(settings), expected)

    def test_one_to_one_relationship(self):
        """Test one-to-one relationship with Organization"""
        settings = self.organization.notification_settings

        # Access from organization
        self.assertEqual(self.organization.notification_settings, settings)

        # Test unique constraint
        with self.assertRaises(Exception):  # IntegrityError
            NotificationSettings.objects.create(organization=self.organization)

    def test_update_settings(self):
        """Test updating notification settings"""
        settings = self.organization.notification_settings

        settings.notify_payment_success = False
        settings.notify_trial_ending = False
        settings.save()

        settings.refresh_from_db()
        self.assertFalse(settings.notify_payment_success)
        self.assertFalse(settings.notify_trial_ending)
        # Other settings should remain True
        self.assertTrue(settings.notify_payment_failure)


class NotificationSettingsSignalTest(TestCase):
    """Test notification settings signal"""

    def test_signal_creates_notification_settings(self):
        """Test that creating organization creates notification settings"""
        organization = Organization.objects.create(
            slack_team_id="T123456",
            slack_domain="test.slack.com",
            name="Test Organization",
        )

        # Check that notification settings were created
        self.assertTrue(
            NotificationSettings.objects.filter(organization=organization).exists()
        )

        settings = organization.notification_settings
        self.assertIsNotNone(settings)
        self.assertTrue(settings.notify_payment_success)  # Check default value

    def test_signal_not_triggered_on_update(self):
        """Test signal not triggered on organization update"""
        organization = Organization.objects.create(
            slack_team_id="T123456",
            slack_domain="test.slack.com",
            name="Test Organization",
        )

        # Get initial settings
        initial_settings = organization.notification_settings

        # Update organization
        organization.name = "Updated Name"
        organization.save()

        # Settings should be the same instance
        organization.refresh_from_db()
        self.assertEqual(organization.notification_settings.id, initial_settings.id)


class OrganizationTrialEndDateTest(TestCase):
    """Test Organization trial_end_date functionality"""

    def test_trial_end_date_callable_default(self):
        """Test that trial_end_date uses callable default"""
        # Create organization and check that trial_end_date is set
        org = Organization.objects.create(
            slack_team_id="T123456",
            slack_domain="test1.slack.com",
            name="Test Organization 1",
        )

        # Trial end date should be set and in the future
        self.assertIsNotNone(org.trial_end_date)

        # Check it's roughly 14 days from now (allowing some tolerance)
        from django.utils import timezone

        expected_end = timezone.now() + timezone.timedelta(days=14)
        time_diff = abs((org.trial_end_date - expected_end).total_seconds())
        self.assertLess(time_diff, 60)  # Within 1 minute
