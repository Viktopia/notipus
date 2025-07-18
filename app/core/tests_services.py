from django.test import TestCase
from unittest.mock import Mock, patch
from core.services.enrichment import DomainEnrichmentService
from core.models import Company, Organization
from webhooks.services.billing import BillingService


class DomainEnrichmentServiceTest(TestCase):
    """Test DomainEnrichmentService"""

    def setUp(self):
        """Set up test data"""
        self.service = DomainEnrichmentService()

    @patch("django.conf.settings")
    @patch("core.services.enrichment.BrandfetchProvider")
    def test_initialize_providers_with_api_key(self, mock_brandfetch, mock_settings):
        """Test provider initialization when API key is available"""
        mock_settings.BRANDFETCH_API_KEY = "test_key"

        # Mock hasattr to return True
        with patch("builtins.hasattr", return_value=True):
            service = DomainEnrichmentService()

            self.assertEqual(len(service.providers), 1)
            mock_brandfetch.assert_called_once()

    @patch("django.conf.settings")
    def test_initialize_providers_without_api_key(self, mock_settings):
        """Test provider initialization when no API key available"""
        # Mock hasattr to return False for BRANDFETCH_API_KEY
        with patch("builtins.hasattr", return_value=False):
            service = DomainEnrichmentService()

            self.assertEqual(len(service.providers), 0)

    @patch("django.conf.settings")
    def test_initialize_providers_empty_api_key(self, mock_settings):
        """Test provider initialization when API key is empty"""
        mock_settings.BRANDFETCH_API_KEY = ""

        # Mock hasattr to return True but key is empty
        with patch("builtins.hasattr", return_value=True):
            service = DomainEnrichmentService()

            self.assertEqual(len(service.providers), 0)

    def test_enrich_domain_creates_new_company(self):
        """Test enriching domain creates new company"""
        domain = "example.com"

        # Mock providers
        mock_provider = Mock()
        mock_provider.enrich_domain.return_value = {
            "name": "Example Company",
            "logo_url": "https://example.com/logo.png",
            "brand_info": {"industry": "Technology"},
        }
        mock_provider.get_provider_name.return_value = "testprovider"

        self.service.providers = [mock_provider]

        result = self.service.enrich_domain(domain)

        # Check company was created
        self.assertTrue(Company.objects.filter(domain=domain).exists())
        company = Company.objects.get(domain=domain)
        self.assertEqual(company.name, "Example Company")
        self.assertEqual(company.logo_url, "https://example.com/logo.png")
        self.assertEqual(company.brand_info["testprovider"]["industry"], "Technology")

        self.assertEqual(result, company)

    def test_enrich_domain_existing_company_with_data(self):
        """Test enriching existing company that already has data"""
        domain = "example.com"

        # Create existing company with data
        existing_company = Company.objects.create(
            domain=domain,
            name="Existing Company",
            logo_url="https://existing.com/logo.png",
        )

        # Mock providers
        mock_provider = Mock()
        mock_provider.enrich_domain.return_value = {
            "name": "New Company Name",
            "logo_url": "https://new.com/logo.png",
        }

        self.service.providers = [mock_provider]

        result = self.service.enrich_domain(domain)

        # Should return existing company without calling provider
        self.assertEqual(result, existing_company)
        mock_provider.enrich_domain.assert_not_called()

        # Data should remain unchanged
        existing_company.refresh_from_db()
        self.assertEqual(existing_company.name, "Existing Company")
        self.assertEqual(existing_company.logo_url, "https://existing.com/logo.png")

    def test_enrich_domain_existing_company_without_data(self):
        """Test enriching existing company that has no name or logo"""
        domain = "example.com"

        # Create existing company without name or logo
        existing_company = Company.objects.create(domain=domain)

        # Mock providers
        mock_provider = Mock()
        mock_provider.enrich_domain.return_value = {
            "name": "New Company Name",
            "logo_url": "https://new.com/logo.png",
            "brand_info": {"industry": "Technology"},
        }
        mock_provider.get_provider_name.return_value = "testprovider"

        self.service.providers = [mock_provider]

        result = self.service.enrich_domain(domain)

        # Should call provider and update company
        mock_provider.enrich_domain.assert_called_once_with(domain)

        existing_company.refresh_from_db()
        self.assertEqual(existing_company.name, "New Company Name")
        self.assertEqual(existing_company.logo_url, "https://new.com/logo.png")
        self.assertEqual(result, existing_company)

    def test_enrich_domain_provider_exception(self):
        """Test handling provider exceptions"""
        domain = "example.com"

        # Mock provider that raises exception
        mock_provider = Mock()
        mock_provider.enrich_domain.side_effect = Exception("API Error")
        mock_provider.get_provider_name.return_value = "testprovider"

        self.service.providers = [mock_provider]

        with patch("core.services.enrichment.logger") as mock_logger:
            result = self.service.enrich_domain(domain)

            # Should create company but not update it
            company = Company.objects.get(domain=domain)
            self.assertIsNone(company.name)
            self.assertIsNone(company.logo_url)
            self.assertEqual(result, company)

            # Should log error
            mock_logger.error.assert_called_once()
            self.assertIn(
                "Error enriching domain with testprovider",
                mock_logger.error.call_args[0][0],
            )

    def test_enrich_domain_no_providers(self):
        """Test enriching domain with no providers available"""
        domain = "example.com"

        # No providers
        self.service.providers = []

        result = self.service.enrich_domain(domain)

        # Should create company but not enrich it
        company = Company.objects.get(domain=domain)
        self.assertIsNone(company.name)
        self.assertIsNone(company.logo_url)
        self.assertEqual(result, company)

    def test_update_company_all_fields(self):
        """Test updating company with all available data"""
        company = Company.objects.create(domain="example.com")

        data = {
            "name": "Example Company",
            "logo_url": "https://example.com/logo.png",
            "brand_info": {"industry": "Technology"},
        }

        with patch.object(company, "save") as mock_save:
            self.service._update_company(company, data, "testprovider")

            self.assertEqual(company.name, "Example Company")
            self.assertEqual(company.logo_url, "https://example.com/logo.png")
            self.assertEqual(
                company.brand_info["testprovider"]["industry"], "Technology"
            )

            mock_save.assert_called_once_with(
                update_fields=["name", "logo_url", "brand_info"]
            )

    def test_update_company_partial_data(self):
        """Test updating company with partial data"""
        company = Company.objects.create(domain="example.com", name="Existing Name")

        data = {
            "logo_url": "https://example.com/logo.png",
            "brand_info": {"industry": "Technology"},
        }

        with patch.object(company, "save") as mock_save:
            self.service._update_company(company, data, "testprovider")

            # Name should not change (already exists)
            self.assertEqual(company.name, "Existing Name")
            self.assertEqual(company.logo_url, "https://example.com/logo.png")

            mock_save.assert_called_once_with(update_fields=["logo_url", "brand_info"])

    def test_update_company_no_data(self):
        """Test updating company with no relevant data"""
        company = Company.objects.create(domain="example.com")

        data = {}

        with patch.object(company, "save") as mock_save:
            self.service._update_company(company, data, "testprovider")

            # No fields should be updated
            mock_save.assert_not_called()

    def test_update_company_existing_brand_info(self):
        """Test updating company that already has brand info"""
        company = Company.objects.create(
            domain="example.com", brand_info={"existing": "data"}
        )

        data = {"brand_info": {"industry": "Technology"}}

        with patch.object(company, "save") as mock_save:
            self.service._update_company(company, data, "testprovider")

            # Should merge brand info
            expected_brand_info = {
                "existing": "data",
                "testprovider": {"industry": "Technology"},
            }
            self.assertEqual(company.brand_info, expected_brand_info)


class BillingServiceTest(TestCase):
    """Test BillingService"""

    def setUp(self):
        """Set up test data"""
        self.organization = Organization.objects.create(
            slack_team_id="T123456",
            slack_domain="test.slack.com",
            name="Test Organization",
            stripe_customer_id="cus_test123",
        )

    @patch("webhooks.services.billing.logger")
    def test_handle_subscription_created_success(self, mock_logger):
        """Test successful subscription creation handling"""
        subscription_data = {
            "customer": "cus_test123",
            "items": {"data": [{"plan": {"id": "plan_basic"}}]},
            "current_period_start": 1234567890,
        }

        BillingService.handle_subscription_created(subscription_data)

        self.organization.refresh_from_db()
        self.assertEqual(self.organization.subscription_plan, "plan_basic")
        self.assertEqual(self.organization.subscription_status, "active")
        self.assertEqual(self.organization.billing_cycle_anchor, 1234567890)

        mock_logger.info.assert_called_once_with(
            "Updated subscription for customer cus_test123 to plan plan_basic"
        )

    @patch("webhooks.services.billing.logger")
    def test_handle_subscription_created_missing_customer(self, mock_logger):
        """Test subscription creation with missing customer ID"""
        subscription_data = {"items": {"data": [{"plan": {"id": "plan_basic"}}]}}

        BillingService.handle_subscription_created(subscription_data)

        self.organization.refresh_from_db()
        # Should not update organization
        self.assertEqual(self.organization.subscription_plan, "trial")

        mock_logger.error.assert_called_once_with(
            "Missing customer ID in subscription data"
        )

    @patch("webhooks.services.billing.logger")
    def test_handle_subscription_created_missing_plan(self, mock_logger):
        """Test subscription creation with missing plan ID"""
        subscription_data = {
            "customer": "cus_test123",
            "items": {"data": [{}]},  # Missing plan
        }

        BillingService.handle_subscription_created(subscription_data)

        self.organization.refresh_from_db()
        # Should not update organization
        self.assertEqual(self.organization.subscription_plan, "trial")

        mock_logger.error.assert_called_once_with(
            "Missing plan ID in subscription data for customer cus_test123"
        )

    @patch("webhooks.services.billing.logger")
    def test_handle_subscription_created_customer_not_found(self, mock_logger):
        """Test subscription creation for non-existent customer"""
        subscription_data = {
            "customer": "cus_nonexistent",
            "items": {"data": [{"plan": {"id": "plan_basic"}}]},
            "current_period_start": 1234567890,
        }

        BillingService.handle_subscription_created(subscription_data)

        mock_logger.warning.assert_called_once_with(
            "No organization found for customer cus_nonexistent"
        )

    @patch("webhooks.services.billing.logger")
    def test_handle_payment_success(self, mock_logger):
        """Test successful payment handling"""
        invoice_data = {"customer": "cus_test123", "period_end": 1234567890}

        BillingService.handle_payment_success(invoice_data)

        self.organization.refresh_from_db()
        self.assertEqual(self.organization.subscription_status, "active")
        self.assertEqual(self.organization.billing_cycle_anchor, 1234567890)

        mock_logger.info.assert_called_once_with(
            "Updated payment status to active for customer cus_test123"
        )

    @patch("webhooks.services.billing.logger")
    def test_handle_payment_success_missing_customer(self, mock_logger):
        """Test payment success with missing customer ID"""
        invoice_data = {"period_end": 1234567890}

        BillingService.handle_payment_success(invoice_data)

        mock_logger.error.assert_called_once_with("Missing customer ID in invoice data")

    @patch("webhooks.services.billing.logger")
    def test_handle_payment_failed(self, mock_logger):
        """Test failed payment handling"""
        invoice_data = {"customer": "cus_test123"}

        BillingService.handle_payment_failed(invoice_data)

        self.organization.refresh_from_db()
        self.assertEqual(self.organization.subscription_status, "past_due")

        mock_logger.warning.assert_called_once_with(
            "Updated payment status to past_due for customer cus_test123"
        )

    @patch("webhooks.services.billing.logger")
    def test_handle_payment_failed_missing_customer(self, mock_logger):
        """Test payment failure with missing customer ID"""
        invoice_data = {}

        BillingService.handle_payment_failed(invoice_data)

        mock_logger.error.assert_called_once_with("Missing customer ID in invoice data")

    @patch("webhooks.services.billing.Organization.objects")
    @patch("webhooks.services.billing.logger")
    def test_handle_subscription_created_exception(self, mock_logger, mock_objects):
        """Test exception handling in subscription creation"""
        mock_objects.filter.side_effect = Exception("Database error")

        subscription_data = {
            "customer": "cus_test123",
            "items": {"data": [{"plan": {"id": "plan_basic"}}]},
        }

        BillingService.handle_subscription_created(subscription_data)

        mock_logger.error.assert_called_once_with(
            "Error handling subscription created: Database error"
        )

    @patch("webhooks.services.billing.Organization.objects")
    @patch("webhooks.services.billing.logger")
    def test_handle_payment_success_exception(self, mock_logger, mock_objects):
        """Test exception handling in payment success"""
        mock_objects.filter.side_effect = Exception("Database error")

        invoice_data = {"customer": "cus_test123"}

        BillingService.handle_payment_success(invoice_data)

        mock_logger.error.assert_called_once_with(
            "Error handling payment success: Database error"
        )

    @patch("webhooks.services.billing.Organization.objects")
    @patch("webhooks.services.billing.logger")
    def test_handle_payment_failed_exception(self, mock_logger, mock_objects):
        """Test exception handling in payment failure"""
        mock_objects.filter.side_effect = Exception("Database error")

        invoice_data = {"customer": "cus_test123"}

        BillingService.handle_payment_failed(invoice_data)

        mock_logger.error.assert_called_once_with(
            "Error handling payment failure: Database error"
        )
