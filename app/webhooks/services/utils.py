"""Shared utility functions for webhook services.

This module contains utility functions used across multiple webhook services
to avoid code duplication.
"""

from typing import Any

from core.utils.email_domain import is_free_email_provider


def get_display_name(customer_data: dict[str, Any]) -> str:
    """Get display name from customer data with smart fallbacks.

    Priority order:
    1. company_name or company field
    2. Customer's full name (first + last)
    3. Email domain (capitalized) for business emails
    4. Email username for free email providers
    5. "Customer" as last resort

    Args:
        customer_data: Customer data dictionary.

    Returns:
        Display name string.
    """
    # Try company name first
    company_name = customer_data.get("company_name") or customer_data.get("company")
    if company_name and company_name != "Individual":
        return company_name

    # Try customer's full name
    first_name = customer_data.get("first_name", "")
    last_name = customer_data.get("last_name", "")
    if first_name or last_name:
        return f"{first_name} {last_name}".strip()

    # Try email domain or username
    email = customer_data.get("email", "")
    if email and "@" in email:
        username, domain = email.split("@", 1)
        # For business emails, use capitalized domain name
        if not is_free_email_provider(domain):
            # Extract company name from domain (e.g., "acme.com" -> "Acme")
            domain_parts = domain.split(".")
            if domain_parts:
                return domain_parts[0].title()
        # For free email providers, use the username
        return username

    return "Customer"
