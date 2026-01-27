"""Email domain utilities for filtering enrichable domains.

This module provides utilities for determining if an email domain
is worth enriching (i.e., belongs to a company vs free/disposable).
"""

import logging
import re
import unicodedata
from email.utils import parseaddr
from typing import Any
from urllib.parse import urlparse

from disposable_email_domains import blocklist

logger = logging.getLogger(__name__)

# Well-known free email providers - domains that should not be enriched
FREE_EMAIL_PROVIDERS: frozenset[str] = frozenset(
    {
        # Major providers
        "gmail.com",
        "googlemail.com",
        "yahoo.com",
        "yahoo.co.uk",
        "yahoo.fr",
        "yahoo.de",
        "yahoo.co.jp",
        "hotmail.com",
        "hotmail.co.uk",
        "hotmail.fr",
        "outlook.com",
        "outlook.co.uk",
        "live.com",
        "live.co.uk",
        "msn.com",
        "icloud.com",
        "me.com",
        "mac.com",
        # Privacy-focused
        "protonmail.com",
        "proton.me",
        "tutanota.com",
        "tutamail.com",
        # Other free providers
        "aol.com",
        "mail.com",
        "email.com",
        "zoho.com",
        "zohomail.com",
        "yandex.com",
        "yandex.ru",
        "gmx.com",
        "gmx.de",
        "gmx.net",
        "web.de",
        "fastmail.com",
        "fastmail.fm",
        "inbox.com",
        "mailbox.org",
        "hey.com",
        # Regional
        "qq.com",
        "163.com",
        "126.com",
        "sina.com",
        "naver.com",
        "daum.net",
        "hanmail.net",
        "libero.it",
        "virgilio.it",
        "laposte.net",
        "orange.fr",
        "free.fr",
        "wanadoo.fr",
        "t-online.de",
        "btinternet.com",
        "sky.com",
        "rogers.com",
        "shaw.ca",
        "telus.net",
        "bigpond.com",
        "optusnet.com.au",
    }
)

# Hosted email domains - cloud providers where the subdomain represents
# the tenant/company. For these domains, the subdomain should be extracted
# to derive the company domain (e.g., contoso.onmicrosoft.com -> contoso.com)
HOSTED_EMAIL_DOMAINS: frozenset[str] = frozenset(
    {
        "onmicrosoft.com",  # Azure AD / Microsoft 365
        "mail.onmicrosoft.com",  # Microsoft 365 mail subdomain
    }
)

# Maximum email length per RFC 5321
MAX_EMAIL_LENGTH = 254

# Simple email regex for basic validation
EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


def sanitize_email_input(value: Any) -> str | None:
    """Sanitize and validate email input.

    First line of defense against malicious input.

    Args:
        value: Raw input value.

    Returns:
        Sanitized email string or None if invalid.
    """
    # Must be a string
    if not isinstance(value, str):
        return None

    # Strip whitespace
    email = value.strip()

    # Check length
    if not email or len(email) > MAX_EMAIL_LENGTH:
        return None

    # Reject null bytes and control characters
    if "\x00" in email or any(ord(c) < 32 for c in email):
        return None

    # Normalize unicode (NFC) to prevent homograph attacks
    email = unicodedata.normalize("NFC", email)

    return email.lower()


def is_valid_email(email: str) -> bool:
    """Validate email format using stdlib.

    Args:
        email: Email address to validate.

    Returns:
        True if email format is valid.
    """
    if not email:
        return False

    # Use stdlib parseaddr for parsing
    _name, addr = parseaddr(email)
    if not addr or "@" not in addr:
        return False

    # Basic format check
    if not EMAIL_PATTERN.match(addr):
        return False

    # Extract and validate domain
    domain = addr.split("@")[1]

    # Reject IP address domains
    if domain.startswith("[") or domain[0].isdigit():
        return False

    # Reject localhost
    if domain in ("localhost", "localhost.localdomain"):
        return False

    # Must have at least one dot (TLD)
    if "." not in domain:
        return False

    # Validate domain structure via urlparse
    try:
        parsed = urlparse(f"http://{domain}")
        if not parsed.netloc or parsed.netloc != domain:
            return False
    except Exception:
        return False

    return True


def extract_domain(email: str, *, derive_company_domain: bool = False) -> str | None:
    """Extract and normalize domain from email address.

    Args:
        email: Email address.
        derive_company_domain: If True, derive company domain from hosted
            email providers (e.g., contoso.onmicrosoft.com -> contoso.com).
            This is useful for enrichment where we want the actual company
            website, not the hosted email provider domain.

    Returns:
        Lowercase domain or None if invalid.
    """
    # Sanitize first
    sanitized = sanitize_email_input(email)
    if not sanitized:
        return None

    # Validate format
    if not is_valid_email(sanitized):
        return None

    # Extract domain
    try:
        _name, addr = parseaddr(sanitized)
        if not addr or "@" not in addr:
            return None

        domain = addr.split("@")[1].lower().strip()

        # Convert IDN to ASCII (punycode)
        try:
            domain = domain.encode("idna").decode("ascii")
        except (UnicodeError, UnicodeDecodeError):
            pass  # Keep original if conversion fails

        # Optionally derive company domain for hosted email providers
        if derive_company_domain:
            return extract_company_domain(domain)

        return domain
    except Exception:
        return None


def is_free_email_provider(domain: str) -> bool:
    """Check if domain is a known free email provider.

    Args:
        domain: Domain to check.

    Returns:
        True if domain is a free email provider.
    """
    if not domain:
        return False
    return domain.lower() in FREE_EMAIL_PROVIDERS


def is_hosted_email_domain(domain: str) -> bool:
    """Check if domain is a hosted email provider with tenant subdomains.

    Hosted email domains are cloud providers (like Microsoft Azure AD) where
    the subdomain represents the tenant/company name, not the actual company
    website. For example, 'contoso.onmicrosoft.com' is a hosted domain where
    'contoso' is the tenant name.

    Args:
        domain: Domain to check (e.g., 'contoso.onmicrosoft.com').

    Returns:
        True if domain is a hosted email provider.
    """
    if not domain:
        return False

    domain_lower = domain.lower()

    # Check if domain ends with any hosted email domain suffix
    for hosted_domain in HOSTED_EMAIL_DOMAINS:
        if domain_lower.endswith(f".{hosted_domain}"):
            return True

    return False


def extract_company_domain(domain: str) -> str | None:
    """Extract the likely company domain from a hosted email domain.

    For hosted email domains (like Azure AD's onmicrosoft.com), the subdomain
    typically represents the tenant/company name. This function extracts that
    subdomain and derives a likely company domain by appending '.com'.

    For regular domains, returns the domain unchanged.

    Examples:
        - 'contoso.onmicrosoft.com' -> 'contoso.com'
        - 'acme.mail.onmicrosoft.com' -> 'acme.com'
        - 'company.com' -> 'company.com' (unchanged)

    Args:
        domain: Domain to process.

    Returns:
        Derived company domain, or None if extraction fails.
    """
    if not domain:
        return None

    domain_lower = domain.lower()

    # If not a hosted email domain, return as-is
    if not is_hosted_email_domain(domain_lower):
        return domain_lower

    # Find which hosted domain suffix matches
    for hosted_domain in HOSTED_EMAIL_DOMAINS:
        suffix = f".{hosted_domain}"
        if domain_lower.endswith(suffix):
            # Extract the subdomain (tenant name)
            # e.g., 'contoso.onmicrosoft.com' -> 'contoso'
            # e.g., 'acme.mail.onmicrosoft.com' -> 'acme'
            subdomain_part = domain_lower[: -len(suffix)]

            # Handle multiple subdomains - take the first part (leftmost)
            # e.g., 'sales.contoso.onmicrosoft.com' -> 'sales'
            # This might not always be correct, but it's the best heuristic
            tenant_name = subdomain_part.split(".")[0]

            # Validate tenant name is not empty and looks like a valid domain part
            if tenant_name and len(tenant_name) >= 2:
                derived_domain = f"{tenant_name}.com"
                logger.debug(
                    f"Derived company domain '{derived_domain}' "
                    f"from hosted domain '{domain}'"
                )
                return derived_domain

            # If we can't extract a valid tenant name, return None
            logger.warning(
                f"Could not extract tenant name from hosted domain: {domain}"
            )
            return None

    # This should be unreachable since is_hosted_email_domain() already verified
    # the domain matches one of HOSTED_EMAIL_DOMAINS, but return None as fallback
    return None  # pragma: no cover


def is_disposable_email(domain: str) -> bool:
    """Check if domain is a disposable/temporary email provider.

    Uses the disposable-email-domains package blocklist.

    Args:
        domain: Domain to check.

    Returns:
        True if domain is disposable.
    """
    if not domain:
        return False
    return domain.lower() in blocklist


def is_enrichable_domain(email: str) -> bool:
    """Determine if an email domain is worth enriching.

    Performs full validation and filtering:
    1. Sanitizes input
    2. Validates email format
    3. Extracts domain
    4. Checks not a free provider
    5. Checks not a disposable domain

    Args:
        email: Email address to check.

    Returns:
        True if domain should be enriched.
    """
    # Extract and validate domain
    domain = extract_domain(email)
    if not domain:
        logger.debug(f"Invalid email format, skipping enrichment: {email}")
        return False

    # Check if free provider
    if is_free_email_provider(domain):
        logger.debug(f"Free email provider, skipping enrichment: {domain}")
        return False

    # Check if disposable
    if is_disposable_email(domain):
        logger.debug(f"Disposable email domain, skipping enrichment: {domain}")
        return False

    return True
