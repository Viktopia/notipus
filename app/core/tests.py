from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from .models import Company, NotificationSettings, Organization, validate_domain


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


class CompanyTest(TestCase):
    """Test Company model"""

    def test_company_creation(self):
        """Test creating a company with valid domain"""
        company = Company.objects.create(
            domain="example.com", name="Example Company"
        )
        self.assertEqual(company.domain, "example.com")
        self.assertEqual(company.name, "Example Company")

    def test_company_str_representation(self):
        """Test string representation of company"""
        company = Company.objects.create(
            domain="example.com", name="Example Company"
        )
        self.assertEqual(str(company), "Example Company (example.com)")

        # Test without name
        company_no_name = Company.objects.create(domain="test.com")
        self.assertEqual(str(company_no_name), "test.com")

    def test_company_domain_validation(self):
        """Test domain validation on company creation"""
        with self.assertRaises(ValidationError):
            Company.objects.create(domain="invalid-domain")

    def test_company_unique_constraint(self):
        """Test unique constraint on domain"""
        Company.objects.create(domain="example.com")

        with self.assertRaises(IntegrityError):  # Fixed: specific exception
            Company.objects.create(domain="example.com")

    def test_company_domain_cleaning(self):
        """Test domain cleaning on save"""
        company = Company.objects.create(
            domain="https://www.EXAMPLE.COM", name="Example"
        )
        self.assertEqual(company.domain, "example.com")


class CoreTestCase(TestCase):
    """Test core models and functionality"""

    def setUp(self):
        """Set up test data"""
        self.organization = Organization.objects.create(
            name="Test Org", shop_domain="test.myshopify.com"
        )

    def test_organization_creation(self):
        """Test organization creation"""
        self.assertEqual(self.organization.name, "Test Org")
        self.assertEqual(self.organization.shop_domain, "test.myshopify.com")

    def test_organization_str_representation(self):
        """Test organization string representation"""
        expected = "Test Org (test.myshopify.com)"
        self.assertEqual(str(self.organization), expected)


class NotificationSettingsTest(TestCase):
    """Test NotificationSettings model"""

    def setUp(self):
        """Set up test data"""
        self.organization = Organization.objects.create(
            name="Test Org", shop_domain="test.myshopify.com"
        )

    def test_notification_settings_creation(self):
        """Test creating notification settings"""
        settings = NotificationSettings.objects.create(
            organization=self.organization
        )
        self.assertEqual(settings.organization, self.organization)
        self.assertTrue(settings.notify_payment_success)  # Default value

    def test_notification_settings_str_representation(self):
        """Test string representation"""
        settings = NotificationSettings.objects.create(
            organization=self.organization
        )
        expected = f"Notification settings for {self.organization.name}"
        self.assertEqual(str(settings), expected)

    def test_notification_settings_defaults(self):
        """Test default values"""
        settings = NotificationSettings.objects.create(
            organization=self.organization
        )
        # Test some key defaults
        self.assertTrue(settings.notify_payment_success)
        self.assertTrue(settings.notify_payment_failure)
        self.assertTrue(settings.notify_subscription_created)

    def test_notification_settings_one_per_organization(self):
        """Test one settings instance per organization"""
        NotificationSettings.objects.create(organization=self.organization)

        # Test unique constraint
        with self.assertRaises(IntegrityError):  # Fixed: specific exception
            NotificationSettings.objects.create(organization=self.organization)
