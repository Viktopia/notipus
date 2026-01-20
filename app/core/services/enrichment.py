"""Domain enrichment service for company brand information.

This module provides services for enriching company domain data
with brand information from external providers.
"""

import logging
from typing import Any

from core.models import Company
from core.providers.brandfetch import BrandfetchProvider

logger = logging.getLogger(__name__)


class DomainEnrichmentService:
    """Service for enriching company domain data.

    Uses external providers to fetch brand information and
    caches results in the Company model.

    Attributes:
        providers: List of initialized enrichment providers.
    """

    def __init__(self) -> None:
        """Initialize the enrichment service with available providers."""
        self.providers: list[Any] = []
        self._initialize_providers()

    def _initialize_providers(self) -> None:
        """Initialize enrichment providers based on available API keys."""
        try:
            brandfetch_provider = BrandfetchProvider()
            if brandfetch_provider.api_key:
                self.providers.append(brandfetch_provider)
                logger.info("Initialized Brandfetch provider for domain enrichment")
            else:
                logger.warning("Brandfetch API key not available, skipping provider")
        except Exception as e:
            logger.error(f"Failed to initialize Brandfetch provider: {e!s}")

        if not self.providers:
            logger.warning("No domain enrichment providers available")

    def enrich_domain(self, domain: str) -> Company | None:
        """Enrich a domain with company information.

        Args:
            domain: Domain name to enrich.

        Returns:
            Company instance with enrichment data, or None on failure.
        """
        if not domain:
            logger.warning("Empty domain provided for enrichment")
            return None

        try:
            # Get or create company record
            company, created = Company.objects.get_or_create(
                domain=domain, defaults={"name": "", "logo_url": "", "brand_info": {}}
            )

            if not self.providers:
                logger.warning("No providers available for domain enrichment")
                return company

            # Skip enrichment if we already have meaningful data
            if not created and (company.name or company.logo_url or company.brand_info):
                logger.debug(f"Company {domain} already has enrichment data")
                return company

            # Try to enrich with each provider
            enrichment_data: dict[str, Any] = {}
            successful_provider: Any = None
            for provider in self.providers:
                try:
                    data = provider.enrich_domain(domain)
                    if data:
                        enrichment_data.update(data)
                        successful_provider = provider
                        logger.info(
                            f"Successfully enriched {domain} with "
                            f"{provider.__class__.__name__}"
                        )
                        break  # Use first successful provider
                except Exception as e:
                    logger.error(
                        f"Provider {provider.__class__.__name__} failed for "
                        f"{domain}: {e!s}"
                    )
                    continue

            # Update company with enrichment data
            if enrichment_data:
                provider_name = (
                    successful_provider.get_provider_name()
                    if successful_provider
                    else None
                )
                self._update_company(company, enrichment_data, provider_name)
                logger.info(f"Updated company record for {domain}")
            else:
                logger.warning(f"No enrichment data found for {domain}")

            return company

        except Exception as e:
            logger.error(f"Error enriching domain {domain}: {e!s}", exc_info=True)
            return None

    def _update_company(
        self,
        company: Company,
        data: dict[str, Any],
        provider_name: str | None = None,
    ) -> None:
        """Update company record with enrichment data.

        Args:
            company: Company model instance to update.
            data: Enrichment data dictionary.
            provider_name: Name of the provider that supplied the data.
        """
        if not data:
            return

        # Update basic fields and track changes
        updated_fields = self._update_basic_fields(company, data)

        # Store enrichment data in brand_info
        self._store_brand_info(company, data, provider_name)
        updated_fields.append("brand_info")

        # Save with specific fields for performance
        self._save_company(company, updated_fields)

    def _update_basic_fields(self, company: Company, data: dict[str, Any]) -> list[str]:
        """Update basic company fields and return list of updated fields.

        Args:
            company: Company model instance.
            data: Enrichment data dictionary.

        Returns:
            List of field names that were updated.
        """
        updated_fields: list[str] = []

        if "name" in data and data["name"]:
            company.name = data["name"]
            updated_fields.append("name")

        if "logo_url" in data and data["logo_url"]:
            company.logo_url = data["logo_url"]
            updated_fields.append("logo_url")

        return updated_fields

    def _store_brand_info(
        self, company: Company, data: dict[str, Any], provider_name: str | None
    ) -> None:
        """Store enrichment data in brand_info field.

        Args:
            company: Company model instance.
            data: Enrichment data dictionary.
            provider_name: Name of the provider that supplied the data.
        """
        if provider_name:
            self._store_provider_specific_data(company, data, provider_name)
        else:
            # Store all enrichment data directly (backward compatibility)
            company.brand_info = data

    def _store_provider_specific_data(
        self, company: Company, data: dict[str, Any], provider_name: str
    ) -> None:
        """Store data under provider-specific key in brand_info.

        Args:
            company: Company model instance.
            data: Enrichment data dictionary.
            provider_name: Provider name for namespacing.
        """
        if not company.brand_info:
            company.brand_info = {}

        if "brand_info" in data:
            company.brand_info[provider_name] = data["brand_info"]
        else:
            # Store all non-basic fields under provider name
            basic_fields = ["name", "logo_url"]
            provider_data = {k: v for k, v in data.items() if k not in basic_fields}
            if provider_data:
                company.brand_info[provider_name] = provider_data

    def _save_company(self, company: Company, updated_fields: list[str]) -> None:
        """Save company with optimized field updates.

        Args:
            company: Company model instance.
            updated_fields: List of fields that were updated.
        """
        if updated_fields:
            company.save(update_fields=updated_fields)
        else:
            company.save()

        logger.debug(f"Updated company {company.domain} with enrichment data")
