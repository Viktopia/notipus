from unittest.mock import Mock, patch

from core.models import Company, Integration, Organization, UserProfile
from core.services.enrichment import DomainEnrichmentService
from core.services.stripe import StripeAPI
from django.test import TestCase
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
            # Model default is empty string, not None
            self.assertEqual(company.name, "")
            self.assertEqual(company.logo_url, "")
            self.assertEqual(result, company)

            # Should log error
            mock_logger.error.assert_called_once()
            self.assertIn(
                "Provider Mock failed for example.com: API Error",
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
        # Model default is empty string, not None
        self.assertEqual(company.name, "")
        self.assertEqual(company.logo_url, "")
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

        with patch.object(company, "save"):
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
            name="Test Organization",
            shop_domain="test.myshopify.com",
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

    @patch("webhooks.services.billing.logger")
    def test_handle_subscription_updated_success(self, mock_logger):
        """Test successful subscription update handling"""
        subscription_data = {
            "customer": "cus_test123",
            "status": "active",
            "items": {"data": [{"plan": {"id": "plan_pro"}}]},
            "current_period_end": 1234567890,
        }

        BillingService.handle_subscription_updated(subscription_data)

        self.organization.refresh_from_db()
        self.assertEqual(self.organization.subscription_plan, "plan_pro")
        self.assertEqual(self.organization.subscription_status, "active")
        self.assertEqual(self.organization.billing_cycle_anchor, 1234567890)

        mock_logger.info.assert_called_once()
        self.assertIn("active", mock_logger.info.call_args[0][0])

    @patch("webhooks.services.billing.logger")
    def test_handle_subscription_updated_status_changes(self, mock_logger):
        """Test subscription update with various status changes"""
        status_test_cases = [
            ("trialing", "trial"),
            ("past_due", "past_due"),
            ("canceled", "cancelled"),
            ("unpaid", "past_due"),
        ]

        for stripe_status, expected_internal_status in status_test_cases:
            with self.subTest(stripe_status=stripe_status):
                # Reset organization
                self.organization.subscription_status = "active"
                self.organization.save()

                subscription_data = {
                    "customer": "cus_test123",
                    "status": stripe_status,
                }

                BillingService.handle_subscription_updated(subscription_data)

                self.organization.refresh_from_db()
                self.assertEqual(
                    self.organization.subscription_status, expected_internal_status
                )

    @patch("webhooks.services.billing.logger")
    def test_handle_subscription_updated_missing_customer(self, mock_logger):
        """Test subscription update with missing customer ID"""
        subscription_data = {"status": "active"}

        BillingService.handle_subscription_updated(subscription_data)

        mock_logger.error.assert_called_once_with(
            "Missing customer ID in subscription data"
        )

    @patch("webhooks.services.billing.logger")
    def test_handle_subscription_deleted_success(self, mock_logger):
        """Test successful subscription deletion handling"""
        subscription_data = {"customer": "cus_test123"}

        BillingService.handle_subscription_deleted(subscription_data)

        self.organization.refresh_from_db()
        self.assertEqual(self.organization.subscription_status, "cancelled")

        mock_logger.info.assert_called_once_with(
            "Marked subscription as cancelled for customer cus_test123"
        )

    @patch("webhooks.services.billing.logger")
    def test_handle_subscription_deleted_missing_customer(self, mock_logger):
        """Test subscription deletion with missing customer ID"""
        subscription_data = {}

        BillingService.handle_subscription_deleted(subscription_data)

        mock_logger.error.assert_called_once_with(
            "Missing customer ID in subscription data"
        )

    @patch("webhooks.services.billing.logger")
    def test_handle_subscription_deleted_customer_not_found(self, mock_logger):
        """Test subscription deletion for non-existent customer"""
        subscription_data = {"customer": "cus_nonexistent"}

        BillingService.handle_subscription_deleted(subscription_data)

        mock_logger.warning.assert_called_once_with(
            "No organization found for customer cus_nonexistent"
        )

    def test_extract_plan_id_nested_format(self):
        """Test plan ID extraction from nested items.data format"""
        subscription = {"items": {"data": [{"plan": {"id": "plan_nested"}}]}}

        result = BillingService._extract_plan_id(subscription)

        self.assertEqual(result, "plan_nested")

    def test_extract_plan_id_direct_format(self):
        """Test plan ID extraction from direct plan format"""
        subscription = {"plan": {"id": "plan_direct"}}

        result = BillingService._extract_plan_id(subscription)

        self.assertEqual(result, "plan_direct")

    def test_extract_plan_id_missing(self):
        """Test plan ID extraction when plan is missing"""
        subscription = {"items": {"data": [{}]}}

        result = BillingService._extract_plan_id(subscription)

        self.assertIsNone(result)


class StripeAPITest(TestCase):
    """Test StripeAPI service"""

    @patch("core.services.stripe.stripe.Customer.create")
    def test_create_stripe_customer_success(self, mock_create):
        """Test successful customer creation"""
        # Mock successful customer creation
        mock_customer = Mock()
        mock_customer.to_dict.return_value = {
            "id": "cus_test123",
            "email": "test@example.com",
            "name": "Test Customer",
        }
        mock_create.return_value = mock_customer

        customer_data = {
            "email": "test@example.com",
            "name": "Test Customer",
            "metadata": {"source": "test"},
        }

        result = StripeAPI.create_stripe_customer(customer_data)

        expected = {
            "id": "cus_test123",
            "email": "test@example.com",
            "name": "Test Customer",
        }

        self.assertEqual(result, expected)
        mock_create.assert_called_once_with(**customer_data)

    @patch("core.services.stripe.stripe.Customer.create")
    def test_create_stripe_customer_stripe_error(self, mock_create):
        """Test customer creation with Stripe error"""
        # Mock Stripe error using the actual stripe library structure
        mock_create.side_effect = Exception("Test Stripe error")

        customer_data = {"email": "test@example.com", "name": "Test Customer"}

        result = StripeAPI.create_stripe_customer(customer_data)

        self.assertIsNone(result)

    @patch("core.services.stripe.stripe.Customer.create")
    def test_create_stripe_customer_empty_data(self, mock_create):
        """Test customer creation with empty data"""
        # Mock successful creation with empty data
        mock_customer = Mock()
        mock_customer.to_dict.return_value = {"id": "cus_empty"}
        mock_create.return_value = mock_customer

        result = StripeAPI.create_stripe_customer({})

        self.assertEqual(result, {"id": "cus_empty"})
        mock_create.assert_called_once_with()


class DashboardServiceTest(TestCase):
    """Test DashboardService"""

    def setUp(self):
        """Set up test data"""
        from django.contrib.auth.models import User

        self.organization = Organization.objects.create(
            name="Test Organization",
            shop_domain="test.myshopify.com",
            stripe_customer_id="cus_test123",
        )
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
        )
        self.user_profile = UserProfile.objects.create(
            user=self.user,
            organization=self.organization,
        )

    @patch("core.services.dashboard.rate_limiter")
    @patch("core.services.dashboard.DatabaseLookupService")
    def test_get_dashboard_data_success(self, mock_db_service, mock_rate_limiter):
        """Test successful dashboard data retrieval"""
        from core.services.dashboard import DashboardService

        # Mock rate limiter
        mock_rate_limiter.check_rate_limit.return_value = (
            True,
            {"current_usage": 50, "limit": 1000, "remaining": 950},
        )
        mock_rate_limiter.get_usage_stats.return_value = {}

        # Mock database service
        mock_db_instance = Mock()
        mock_db_instance.get_recent_webhook_activity.return_value = []
        mock_db_service.return_value = mock_db_instance

        service = DashboardService()
        result = service.get_dashboard_data(self.user)

        self.assertIsNotNone(result)
        self.assertEqual(result["organization"], self.organization)
        self.assertEqual(result["user_profile"], self.user_profile)
        self.assertIn("integrations", result)
        self.assertIn("recent_activity", result)
        self.assertIn("usage_data", result)
        self.assertIn("trial_info", result)

    @patch("core.services.dashboard.rate_limiter")
    @patch("core.services.dashboard.DatabaseLookupService")
    def test_get_dashboard_data_no_profile(self, mock_db_service, mock_rate_limiter):
        """Test dashboard data retrieval when user has no profile"""
        from core.services.dashboard import DashboardService
        from django.contrib.auth.models import User

        user_without_profile = User.objects.create_user(
            username="noprofile",
            email="noprofile@example.com",
            password="testpass123",
        )

        service = DashboardService()
        result = service.get_dashboard_data(user_without_profile)

        self.assertIsNone(result)

    def test_get_integration_data(self):
        """Test integration data retrieval"""
        from core.services.dashboard import DashboardService

        # Create some integrations
        Integration.objects.create(
            organization=self.organization,
            integration_type="slack_notifications",
            is_active=True,
        )
        Integration.objects.create(
            organization=self.organization,
            integration_type="shopify",
            is_active=True,
        )

        service = DashboardService()
        result = service._get_integration_data(self.organization)

        self.assertTrue(result["has_slack"])
        self.assertTrue(result["has_shopify"])
        self.assertFalse(result["has_chargify"])
        self.assertFalse(result["has_stripe"])

    def test_get_trial_info_active_trial(self):
        """Test trial info for active trial"""
        from core.services.dashboard import DashboardService
        from django.utils import timezone

        # Set organization as trial
        self.organization.subscription_status = "trial"
        self.organization.trial_end_date = timezone.now() + timezone.timedelta(days=10)
        self.organization.save()

        service = DashboardService()
        result = service._get_trial_info(self.organization)

        self.assertTrue(result["is_trial"])
        # Days remaining can be 9 or 10 depending on exact timing
        self.assertIn(result["trial_days_remaining"], [9, 10])

    def test_get_trial_info_not_trial(self):
        """Test trial info for non-trial subscription"""
        from core.services.dashboard import DashboardService

        self.organization.subscription_status = "active"
        self.organization.save()

        service = DashboardService()
        result = service._get_trial_info(self.organization)

        self.assertFalse(result["is_trial"])
        self.assertEqual(result["trial_days_remaining"], 0)

    @patch("core.services.dashboard.rate_limiter")
    def test_get_usage_data_success(self, mock_rate_limiter):
        """Test usage data retrieval"""
        from core.services.dashboard import DashboardService

        mock_rate_limiter.check_rate_limit.return_value = (
            True,
            {"current_usage": 500, "limit": 1000, "remaining": 500},
        )
        mock_rate_limiter.get_usage_stats.return_value = {"monthly": []}

        service = DashboardService()
        result = service._get_usage_data(self.organization)

        self.assertTrue(result["is_allowed"])
        self.assertEqual(result["usage_percentage"], 50.0)

    @patch("core.services.dashboard.rate_limiter")
    def test_get_usage_data_error_handling(self, mock_rate_limiter):
        """Test usage data error handling"""
        from core.services.dashboard import DashboardService

        mock_rate_limiter.check_rate_limit.side_effect = Exception("Redis error")

        service = DashboardService()
        result = service._get_usage_data(self.organization)

        # Should return default values on error
        self.assertTrue(result["is_allowed"])
        self.assertEqual(result["usage_percentage"], 0)

    @patch("core.services.dashboard.DatabaseLookupService")
    def test_transform_activity_data(self, mock_db_service):
        """Test activity data transformation"""
        from core.services.dashboard import DashboardService

        service = DashboardService()

        raw_activity = [
            {
                "type": "payment_success",
                "provider": "stripe",
                "status": "completed",
                "amount": "99.99",
                "currency": "USD",
                "timestamp": 1234567890,
                "external_id": "pi_123",
                "customer_id": "cus_123",
            },
        ]

        result = service._transform_activity_data(raw_activity)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["type"], "payment_success")
        self.assertEqual(result[0]["provider"], "stripe")
        self.assertEqual(result[0]["amount"], "99.99")
