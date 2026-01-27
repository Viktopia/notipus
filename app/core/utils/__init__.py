"""Core utility modules."""

from .email_domain import (
    extract_company_domain,
    extract_domain,
    is_disposable_email,
    is_enrichable_domain,
    is_free_email_provider,
    is_hosted_email_domain,
)

__all__ = [
    "extract_company_domain",
    "extract_domain",
    "is_disposable_email",
    "is_enrichable_domain",
    "is_free_email_provider",
    "is_hosted_email_domain",
]
