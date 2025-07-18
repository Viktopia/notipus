from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase


class ValidateDomainTest(TestCase):
    """Test domain validation function"""

    def test_valid_domains(self):
        """Test valid domain formats"""
        from .models import validate_domain  # noqa: E402

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
                self.assertTrue(len(result) > 0)

    def test_domain_cleaning(self):
        """Test that protocols and www are removed"""
        from .models import validate_domain  # noqa: E402

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
        from .models import validate_domain  # noqa: E402

        invalid_domains = [
            "invalid",
            "http://",
            "ftp://example.com",
            "",
            "example..com",
            ".example.com",
            "example.com.",
        ]

        for domain in invalid_domains:
            with self.subTest(domain=domain):
                with self.assertRaises(ValidationError):
                    validate_domain(domain)


class CompanyTest(TestCase):
    """Test Company model"""

    def test_company_creation(self):
        """Test creating a company with valid domain"""
        from .models import Company  # noqa: E402

        company = Company.objects.create(
            domain="example.com", name="Example Company"
        )
        self.assertEqual(company.domain, "example.com")
        self.assertEqual(company.name, "Example Company")

    def test_company_str_representation(self):
        """Test string representation of company"""
        from .models import Company  # noqa: E402

        company = Company.objects.create(
            domain="example.com", name="Example Company"
        )
        expected = "Example Company (example.com)"
        self.assertEqual(str(company), expected)

        # Test company without name
        company_no_name = Company.objects.create(domain="test.com")
        self.assertEqual(str(company_no_name), "test.com")

    def test_company_domain_validation(self):
        """Test domain validation on company creation"""
        from .models import Company  # noqa: E402

        with self.assertRaises(ValidationError):
            Company.objects.create(domain="invalid-domain")

    def test_company_unique_constraint(self):
        """Test unique constraint on domain"""
        from .models import Company  # noqa: E402

        Company.objects.create(domain="example.com")

        with self.assertRaises(IntegrityError):
            Company.objects.create(domain="example.com")

    def test_company_domain_cleaning(self):
        """Test domain cleaning on save"""
        from .models import Company  # noqa: E402

        company = Company.objects.create(
            domain="https://www.EXAMPLE.COM", name="Example"
        )
        self.assertEqual(company.domain, "example.com")


class OrganizationTest(TestCase):
    """Test Organization model"""

    def setUp(self):
        """Set up test data"""
        from .models import Organization  # noqa: E402

        self.organization = Organization.objects.create(
            name="Test Org", shop_domain="test.myshopify.com"
        )

    def test_organization_str_representation(self):
        """Test organization string representation"""
        expected = "Test Org (test.myshopify.com)"
        self.assertEqual(str(self.organization), expected)


class NotificationSettingsTest(TestCase):
    """Test NotificationSettings model"""

    def setUp(self):
        """Set up test data"""
        from .models import Organization  # noqa: E402

        self.organization = Organization.objects.create(
            name="Test Org", shop_domain="test.myshopify.com"
        )

    def test_notification_settings_creation(self):
        """Test creating notification settings"""
        from .models import NotificationSettings  # noqa: E402

        settings = NotificationSettings.objects.create(
            organization=self.organization
        )
        self.assertEqual(settings.organization, self.organization)
        self.assertTrue(settings.notify_payment_success)  # Default value

    def test_notification_settings_str_representation(self):
        """Test string representation"""
        from .models import NotificationSettings  # noqa: E402

        settings = NotificationSettings.objects.create(
            organization=self.organization
        )
        expected = f"Notification settings for {self.organization.name}"
        self.assertEqual(str(settings), expected)

    def test_notification_settings_defaults(self):
        """Test default values"""
        from .models import NotificationSettings  # noqa: E402

        settings = NotificationSettings.objects.create(
            organization=self.organization
        )
        # Test some key defaults
        self.assertTrue(settings.notify_payment_success)
        self.assertTrue(settings.notify_payment_failure)
        self.assertTrue(settings.notify_subscription_created)

    def test_notification_settings_one_per_organization(self):
        """Test one settings instance per organization"""
        from .models import NotificationSettings  # noqa: E402

        NotificationSettings.objects.create(organization=self.organization)

        # Test unique constraint
        with self.assertRaises(IntegrityError):  # Fixed: specific exception
            NotificationSettings.objects.create(organization=self.organization)
