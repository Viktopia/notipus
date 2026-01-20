"""Tests for template rendering.

These tests ensure that templates render correctly without errors,
especially custom error templates (404, 500) and key application pages.
"""

from core.models import Organization, Plan, UserProfile
from core.views import custom_404, custom_500
from django.contrib.auth.models import User
from django.template.loader import get_template, render_to_string
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse


class TemplateLoadingTests(TestCase):
    """Test that templates can be loaded without errors."""

    def test_base_template_loads(self) -> None:
        """Test that the base template can be loaded."""
        template = get_template("core/base.html.j2")
        assert template is not None

    def test_404_template_loads(self) -> None:
        """Test that the 404 template can be loaded."""
        template = get_template("404.html.j2")
        assert template is not None

    def test_500_template_loads(self) -> None:
        """Test that the 500 template can be loaded."""
        template = get_template("500.html.j2")
        assert template is not None

    def test_landing_template_loads(self) -> None:
        """Test that the landing page template can be loaded."""
        template = get_template("core/landing.html.j2")
        assert template is not None

    def test_dashboard_template_loads(self) -> None:
        """Test that the dashboard template can be loaded."""
        template = get_template("core/dashboard.html.j2")
        assert template is not None

    def test_login_template_loads(self) -> None:
        """Test that the login template can be loaded."""
        template = get_template("account/login.html.j2")
        assert template is not None

    def test_signup_template_loads(self) -> None:
        """Test that the signup template can be loaded."""
        template = get_template("account/signup.html.j2")
        assert template is not None


class ErrorTemplateRenderingTests(TestCase):
    """Test that error templates render correctly."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.factory = RequestFactory()

    def test_404_template_renders(self) -> None:
        """Test that the 404 template renders without errors."""
        html = render_to_string("404.html.j2", {})
        assert "404" in html
        assert "Page Not Found" in html
        assert "Go Home" in html

    def test_500_template_renders(self) -> None:
        """Test that the 500 template renders without errors."""
        html = render_to_string("500.html.j2", {})
        assert "500" in html
        assert "Server Error" in html
        assert "Go Home" in html

    def test_404_view_returns_correct_status(self) -> None:
        """Test that the custom 404 view returns 404 status code."""
        request = self.factory.get("/nonexistent/")
        response = custom_404(request, Exception("Not found"))
        assert response.status_code == 404
        assert b"Page Not Found" in response.content

    def test_500_view_returns_correct_status(self) -> None:
        """Test that the custom 500 view returns 500 status code."""
        request = self.factory.get("/")
        response = custom_500(request)
        assert response.status_code == 500
        assert b"Server Error" in response.content


class TemplateContextTests(TestCase):
    """Test templates render with various context states."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.client = Client()

        # Create test user
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
        )

        # Create organization and profile
        self.organization = Organization.objects.create(
            name="Test Organization",
            shop_domain="test.myshopify.com",
        )

        self.user_profile = UserProfile.objects.create(
            user=self.user,
            slack_user_id="U123456",
            organization=self.organization,
        )

    def test_landing_page_unauthenticated(self) -> None:
        """Test landing page renders for unauthenticated users."""
        response = self.client.get(reverse("core:landing"))
        assert response.status_code == 200
        assert b"Notipus" in response.content

    def test_landing_page_authenticated_redirects(self) -> None:
        """Test landing page redirects authenticated users to dashboard."""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("core:landing"))
        # Authenticated users are redirected to dashboard
        assert response.status_code == 302
        assert response.url == "/dashboard/"

    def test_dashboard_requires_authentication(self) -> None:
        """Test dashboard redirects unauthenticated users."""
        response = self.client.get(reverse("core:dashboard"))
        assert response.status_code == 302  # Redirect to login

    def test_dashboard_renders_authenticated(self) -> None:
        """Test dashboard renders for authenticated users."""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("core:dashboard"))
        assert response.status_code == 200
        assert b"Dashboard" in response.content

    def test_integrations_page_renders(self) -> None:
        """Test integrations page renders for authenticated users."""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("core:integrations"))
        assert response.status_code == 200


@override_settings(DEBUG=False)
class Error404IntegrationTests(TestCase):
    """Integration tests for 404 error handling."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.client = Client()

    def test_nonexistent_page_returns_404(self) -> None:
        """Test that a non-existent page returns 404 with custom template."""
        response = self.client.get("/this-page-definitely-does-not-exist/")
        assert response.status_code == 404
        # Should render our custom 404 template
        assert b"Page Not Found" in response.content

    def test_nonexistent_api_endpoint_returns_404(self) -> None:
        """Test that a non-existent API endpoint returns 404."""
        response = self.client.get("/api/this-endpoint-does-not-exist/")
        assert response.status_code == 404


class BillingTemplateTests(TestCase):
    """Test billing-related templates render correctly."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.client = Client()

        # Create test user
        self.user = User.objects.create_user(
            username="billinguser",
            email="billing@example.com",
            password="testpass123",
        )

        # Create organization and profile
        self.organization = Organization.objects.create(
            name="Billing Test Org",
            shop_domain="billing.myshopify.com",
            subscription_plan="basic",
            subscription_status="active",
        )

        self.user_profile = UserProfile.objects.create(
            user=self.user,
            slack_user_id="U789012",
            organization=self.organization,
        )

        # Get or create a plan (plan may already exist from migrations)
        self.plan, _ = Plan.objects.get_or_create(
            name="basic",
            defaults={
                "display_name": "Basic Plan",
                "description": "Basic plan for small teams",
                "price_monthly": 29.00,
                "max_users": 5,
                "max_integrations": 3,
                "max_monthly_notifications": 5000,
                "stripe_price_id_monthly": "price_test123",
                "is_active": True,
            },
        )

    def test_billing_dashboard_renders(self) -> None:
        """Test billing dashboard renders for authenticated users."""
        self.client.login(username="billinguser", password="testpass123")
        response = self.client.get(reverse("core:billing_dashboard"))
        assert response.status_code == 200

    def test_select_plan_renders(self) -> None:
        """Test select plan page renders."""
        self.client.login(username="billinguser", password="testpass123")
        response = self.client.get(reverse("core:select_plan"))
        assert response.status_code == 200

    def test_billing_history_renders(self) -> None:
        """Test billing history page renders."""
        self.client.login(username="billinguser", password="testpass123")
        response = self.client.get(reverse("core:billing_history"))
        assert response.status_code == 200


class OrganizationTemplateTests(TestCase):
    """Test organization-related templates render correctly."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.client = Client()

        # Create test user without organization
        self.user_no_org = User.objects.create_user(
            username="noorguser",
            email="noorg@example.com",
            password="testpass123",
        )

        # Create user with organization
        self.user_with_org = User.objects.create_user(
            username="orguser",
            email="org@example.com",
            password="testpass123",
        )

        self.organization = Organization.objects.create(
            name="Test Org",
            shop_domain="org.myshopify.com",
        )

        self.user_profile = UserProfile.objects.create(
            user=self.user_with_org,
            slack_user_id="U111222",
            organization=self.organization,
        )

    def test_create_organization_renders(self) -> None:
        """Test create organization page renders."""
        self.client.login(username="noorguser", password="testpass123")
        response = self.client.get(reverse("core:create_organization"))
        assert response.status_code == 200

    def test_organization_settings_renders(self) -> None:
        """Test organization settings page renders."""
        self.client.login(username="orguser", password="testpass123")
        response = self.client.get(reverse("core:organization_settings"))
        assert response.status_code == 200


class StaticFilesTemplateTests(TestCase):
    """Test that templates correctly reference static files."""

    def test_base_template_includes_css(self) -> None:
        """Test that base template includes CSS reference."""
        html = render_to_string("core/base.html.j2", {})
        assert "main.css" in html

    def test_base_template_includes_logo(self) -> None:
        """Test that base template includes logo reference."""
        html = render_to_string("core/base.html.j2", {})
        assert "notipus-logo.png" in html


class AuthenticationTemplateTests(TestCase):
    """Test authentication-related templates."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.client = Client()

    def test_login_page_renders(self) -> None:
        """Test login page renders correctly."""
        response = self.client.get("/accounts/login/")
        assert response.status_code == 200
        assert b"Login" in response.content or b"Sign In" in response.content

    def test_signup_page_renders(self) -> None:
        """Test signup page renders correctly."""
        response = self.client.get("/accounts/signup/")
        assert response.status_code == 200
        assert b"Sign Up" in response.content or b"Register" in response.content
