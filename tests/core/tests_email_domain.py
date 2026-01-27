"""Tests for email domain filtering utilities.

Tests cover:
- Email sanitization and validation
- Domain extraction
- Free email provider detection
- Disposable email detection
- Hosted email domain detection
- Company domain extraction from hosted domains
- Combined enrichability check
"""

from core.utils.email_domain import (
    extract_company_domain,
    extract_domain,
    is_disposable_email,
    is_enrichable_domain,
    is_free_email_provider,
    is_hosted_email_domain,
    is_valid_email,
    sanitize_email_input,
)


class TestSanitizeEmailInput:
    """Tests for sanitize_email_input function."""

    def test_valid_email(self) -> None:
        """Test sanitization of valid email."""
        result = sanitize_email_input("User@Example.COM")
        assert result == "user@example.com"

    def test_strips_whitespace(self) -> None:
        """Test whitespace stripping."""
        result = sanitize_email_input("  user@example.com  ")
        assert result == "user@example.com"

    def test_rejects_non_string(self) -> None:
        """Test rejection of non-string input."""
        assert sanitize_email_input(None) is None
        assert sanitize_email_input(123) is None
        assert sanitize_email_input([]) is None
        assert sanitize_email_input({}) is None

    def test_rejects_empty_string(self) -> None:
        """Test rejection of empty string."""
        assert sanitize_email_input("") is None
        assert sanitize_email_input("   ") is None

    def test_rejects_oversized_input(self) -> None:
        """Test rejection of input exceeding max length."""
        oversized = "a" * 300 + "@example.com"
        assert sanitize_email_input(oversized) is None

    def test_rejects_null_bytes(self) -> None:
        """Test rejection of null byte injection."""
        assert sanitize_email_input("user\x00@example.com") is None

    def test_rejects_control_characters(self) -> None:
        """Test rejection of control characters."""
        assert sanitize_email_input("user\n@example.com") is None
        assert sanitize_email_input("user\t@example.com") is None
        assert sanitize_email_input("user\r@example.com") is None


class TestIsValidEmail:
    """Tests for is_valid_email function."""

    def test_valid_emails(self) -> None:
        """Test validation of valid email formats."""
        valid_emails = [
            "user@example.com",
            "name.surname@company.co.uk",
            "user+tag@example.com",
            "user123@test.org",
            "first.last@domain.io",
        ]
        for email in valid_emails:
            assert is_valid_email(email) is True, f"{email} should be valid"

    def test_invalid_format(self) -> None:
        """Test rejection of invalid formats."""
        invalid_emails = [
            "not-an-email",
            "missing@tld",
            "@nodomain.com",
            "nodomain@",
            "",
            "spaces in@email.com",
        ]
        for email in invalid_emails:
            assert is_valid_email(email) is False, f"{email} should be invalid"

    def test_rejects_ip_domains(self) -> None:
        """Test rejection of IP address domains."""
        assert is_valid_email("user@192.168.1.1") is False
        assert is_valid_email("user@10.0.0.1") is False

    def test_rejects_localhost(self) -> None:
        """Test rejection of localhost domains."""
        assert is_valid_email("user@localhost") is False
        assert is_valid_email("user@localhost.localdomain") is False


class TestExtractDomain:
    """Tests for extract_domain function."""

    def test_extracts_domain(self) -> None:
        """Test basic domain extraction."""
        assert extract_domain("user@example.com") == "example.com"
        assert extract_domain("name@company.co.uk") == "company.co.uk"

    def test_lowercases_domain(self) -> None:
        """Test domain is lowercased."""
        assert extract_domain("User@EXAMPLE.COM") == "example.com"

    def test_returns_none_for_invalid(self) -> None:
        """Test None return for invalid emails."""
        assert extract_domain("not-an-email") is None
        assert extract_domain("") is None
        assert extract_domain(None) is None  # type: ignore[arg-type]


class TestIsFreeEmailProvider:
    """Tests for is_free_email_provider function."""

    def test_detects_free_providers(self) -> None:
        """Test detection of known free providers."""
        free_providers = [
            "gmail.com",
            "yahoo.com",
            "hotmail.com",
            "outlook.com",
            "icloud.com",
            "protonmail.com",
            "aol.com",
            "mail.com",
            "zoho.com",
            "yandex.com",
        ]
        for domain in free_providers:
            assert is_free_email_provider(domain) is True, f"{domain} should be free"

    def test_rejects_company_domains(self) -> None:
        """Test rejection of company domains."""
        company_domains = [
            "acme.com",
            "company.io",
            "startup.co",
            "enterprise.org",
        ]
        for domain in company_domains:
            assert not is_free_email_provider(domain), f"{domain} should not be free"

    def test_case_insensitive(self) -> None:
        """Test case insensitivity."""
        assert is_free_email_provider("GMAIL.COM") is True
        assert is_free_email_provider("Gmail.Com") is True


class TestIsDisposableEmail:
    """Tests for is_disposable_email function."""

    def test_detects_disposable_domains(self) -> None:
        """Test detection of known disposable domains."""
        disposable_domains = [
            "mailinator.com",
            "guerrillamail.com",
            "10minutemail.com",
        ]
        for domain in disposable_domains:
            assert is_disposable_email(domain) is True, f"{domain} should be disposable"

    def test_rejects_real_domains(self) -> None:
        """Test rejection of real domains."""
        real_domains = [
            "gmail.com",
            "acme.com",
            "company.io",
        ]
        for domain in real_domains:
            assert not is_disposable_email(domain), f"{domain} not disposable"


class TestIsEnrichableDomain:
    """Tests for is_enrichable_domain function."""

    def test_enrichable_company_email(self) -> None:
        """Test that company emails are enrichable."""
        enrichable_emails = [
            "john@acme.com",
            "jane@startup.io",
            "contact@enterprise.org",
        ]
        for email in enrichable_emails:
            assert is_enrichable_domain(email) is True, f"{email} should be enrichable"

    def test_not_enrichable_free_provider(self) -> None:
        """Test that free provider emails are not enrichable."""
        free_emails = [
            "user@gmail.com",
            "user@yahoo.com",
            "user@hotmail.com",
            "user@outlook.com",
        ]
        for email in free_emails:
            assert not is_enrichable_domain(email), f"{email} not enrichable"

    def test_not_enrichable_disposable(self) -> None:
        """Test that disposable emails are not enrichable."""
        disposable_emails = [
            "user@mailinator.com",
            "user@guerrillamail.com",
            "user@10minutemail.com",
        ]
        for email in disposable_emails:
            assert not is_enrichable_domain(email), f"{email} not enrichable"

    def test_not_enrichable_invalid(self) -> None:
        """Test that invalid emails are not enrichable."""
        invalid_emails = [
            "not-an-email",
            "",
            "user@",
            "@domain.com",
        ]
        for email in invalid_emails:
            assert not is_enrichable_domain(email), f"{email} not enrichable"


class TestIsHostedEmailDomain:
    """Tests for is_hosted_email_domain function."""

    def test_detects_onmicrosoft_domains(self) -> None:
        """Test detection of Azure AD onmicrosoft.com domains."""
        hosted_domains = [
            "widgetco.onmicrosoft.com",
            "acmecorp.onmicrosoft.com",
            "testorg.mail.onmicrosoft.com",
            "democorp.mail.onmicrosoft.com",
        ]
        for domain in hosted_domains:
            assert is_hosted_email_domain(domain) is True, f"{domain} should be hosted"

    def test_rejects_regular_domains(self) -> None:
        """Test rejection of regular company domains."""
        regular_domains = [
            "acme.com",
            "company.io",
            "enterprise.org",
            "microsoft.com",
            "onmicrosoft.com",  # Base domain without subdomain is not hosted
        ]
        for domain in regular_domains:
            assert not is_hosted_email_domain(domain), f"{domain} should not be hosted"

    def test_rejects_free_providers(self) -> None:
        """Test rejection of free email providers."""
        free_providers = [
            "gmail.com",
            "outlook.com",
            "yahoo.com",
        ]
        for domain in free_providers:
            assert not is_hosted_email_domain(domain), f"{domain} should not be hosted"

    def test_case_insensitive(self) -> None:
        """Test case insensitivity."""
        assert is_hosted_email_domain("WIDGETCO.ONMICROSOFT.COM") is True
        assert is_hosted_email_domain("Acmecorp.OnMicrosoft.Com") is True

    def test_empty_and_none(self) -> None:
        """Test handling of empty and None values."""
        assert is_hosted_email_domain("") is False
        assert is_hosted_email_domain(None) is False  # type: ignore[arg-type]


class TestExtractCompanyDomain:
    """Tests for extract_company_domain function."""

    def test_extracts_from_onmicrosoft(self) -> None:
        """Test extraction from onmicrosoft.com domains."""
        assert extract_company_domain("widgetco.onmicrosoft.com") == "widgetco.com"
        assert extract_company_domain("acmecorp.onmicrosoft.com") == "acmecorp.com"
        assert extract_company_domain("testorg.onmicrosoft.com") == "testorg.com"

    def test_extracts_from_mail_onmicrosoft(self) -> None:
        """Test extraction from mail.onmicrosoft.com domains."""
        result = extract_company_domain("widgetco.mail.onmicrosoft.com")
        assert result == "widgetco.com"
        result = extract_company_domain("acmecorp.mail.onmicrosoft.com")
        assert result == "acmecorp.com"

    def test_handles_multiple_subdomains(self) -> None:
        """Test handling of multiple subdomains (uses first/leftmost).

        Note: When there are multiple subdomains like 'sales.widgetco.onmicrosoft.com',
        we use the leftmost subdomain ('sales') as the tenant name. This is a heuristic
        that may not always yield the "correct" company domain, but it's a reasonable
        default when we can't determine the organizational structure.
        """
        result = extract_company_domain("sales.widgetco.onmicrosoft.com")
        assert result == "sales.com"
        assert extract_company_domain("dept.testorg.onmicrosoft.com") == "dept.com"

    def test_returns_regular_domains_unchanged(self) -> None:
        """Test that regular domains are returned unchanged."""
        assert extract_company_domain("acme.com") == "acme.com"
        assert extract_company_domain("company.io") == "company.io"
        assert extract_company_domain("enterprise.co.uk") == "enterprise.co.uk"

    def test_case_insensitive(self) -> None:
        """Test case insensitivity (returns lowercase)."""
        assert extract_company_domain("WIDGETCO.ONMICROSOFT.COM") == "widgetco.com"
        assert extract_company_domain("ACMECORP.COM") == "acmecorp.com"

    def test_empty_and_none(self) -> None:
        """Test handling of empty and None values."""
        assert extract_company_domain("") is None
        assert extract_company_domain(None) is None  # type: ignore[arg-type]

    def test_invalid_short_tenant_names(self) -> None:
        """Test that very short tenant names (less than 2 chars) return None."""
        # Single character tenant names should fail validation
        assert extract_company_domain("a.onmicrosoft.com") is None


class TestExtractDomainWithDeriveCompanyDomain:
    """Tests for extract_domain with derive_company_domain parameter."""

    def test_default_behavior_unchanged(self) -> None:
        """Test that default behavior (derive_company_domain=False) is unchanged."""
        result = extract_domain("user@widgetco.onmicrosoft.com")
        assert result == "widgetco.onmicrosoft.com"
        assert extract_domain("user@acmecorp.com") == "acmecorp.com"

    def test_derives_company_domain_from_onmicrosoft(self) -> None:
        """Test derivation of company domain from onmicrosoft.com emails."""
        result = extract_domain(
            "user@widgetco.onmicrosoft.com", derive_company_domain=True
        )
        assert result == "widgetco.com"
        result = extract_domain(
            "admin@acmecorp.onmicrosoft.com", derive_company_domain=True
        )
        assert result == "acmecorp.com"

    def test_derives_company_domain_from_mail_onmicrosoft(self) -> None:
        """Test derivation from mail.onmicrosoft.com emails."""
        result = extract_domain(
            "user@widgetco.mail.onmicrosoft.com", derive_company_domain=True
        )
        assert result == "widgetco.com"

    def test_regular_domains_unchanged_with_derive(self) -> None:
        """Test that regular domains are unchanged when derive_company_domain=True."""
        result = extract_domain("user@acmecorp.com", derive_company_domain=True)
        assert result == "acmecorp.com"
        result = extract_domain("user@testorg.io", derive_company_domain=True)
        assert result == "testorg.io"

    def test_invalid_emails_return_none(self) -> None:
        """Test that invalid emails return None regardless of derive parameter."""
        assert extract_domain("not-an-email", derive_company_domain=True) is None
        assert extract_domain("", derive_company_domain=True) is None

    def test_hosted_domain_enrichable(self) -> None:
        """Test that hosted email domains are considered enrichable."""
        # Hosted domains should be enrichable since they're business emails
        assert is_enrichable_domain("user@widgetco.onmicrosoft.com") is True
        assert is_enrichable_domain("admin@acmecorp.mail.onmicrosoft.com") is True
