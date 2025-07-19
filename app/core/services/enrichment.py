import logging
from typing import Any, Dict, List, Optional

from core.models import Company
from core.providers.brandfetch import BrandfetchProvider

logger = logging.getLogger(__name__)


class DomainEnrichmentService:
    """Service for enriching company domain data"""

    def __init__(self) -> None:
        """Initialize the enrichment service with available providers"""
        self.providers: List[Any] = []
        self._initialize_providers()

    def _initialize_providers(self) -> None:
        """Initialize enrichment providers based on available API keys"""
        try:
            brandfetch_provider = BrandfetchProvider()
            if brandfetch_provider.api_key:
                self.providers.append(brandfetch_provider)
                logger.info("Initialized Brandfetch provider for domain enrichment")
            else:
                logger.warning("Brandfetch API key not available, skipping provider")
        except Exception as e:
            logger.error(f"Failed to initialize Brandfetch provider: {str(e)}")

        if not self.providers:
            logger.warning("No domain enrichment providers available")

    def enrich_domain(self, domain: str) -> Optional[Company]:
        """Enrich a domain with company information"""
        if not domain:
            logger.warning("Empty domain provided for enrichment")
            return None

        if not self.providers:
            logger.warning("No providers available for domain enrichment")
            return None

        try:
            # Get or create company record
            company, created = Company.objects.get_or_create(
                domain=domain, defaults={"name": "", "logo_url": "", "brand_info": {}}
            )

            # Skip enrichment if we already have data and it's recent
            if not created and company.brand_info and company.updated_at:
                logger.debug(f"Company {domain} already has enrichment data")
                return company

            # Try to enrich with each provider
            enrichment_data = {}
            for provider in self.providers:
                try:
                    data = provider.enrich_domain(domain)
                    if data:
                        enrichment_data.update(data)
                        logger.info(
                            f"Successfully enriched {domain} with {provider.__class__.__name__}"
                        )
                        break  # Use first successful provider
                except Exception as e:
                    logger.error(
                        f"Provider {provider.__class__.__name__} failed for {domain}: {str(e)}"
                    )
                    continue

            # Update company with enrichment data
            if enrichment_data:
                self._update_company(company, enrichment_data)
                logger.info(f"Updated company record for {domain}")
            else:
                logger.warning(f"No enrichment data found for {domain}")

            return company

        except Exception as e:
            logger.error(f"Error enriching domain {domain}: {str(e)}", exc_info=True)
            return None

    def _update_company(self, company: Company, data: Dict[str, Any]) -> None:
        """Update company record with enrichment data"""
        if not data:
            return

        # Update basic fields
        if "name" in data and data["name"]:
            company.name = data["name"]

        if "logo_url" in data and data["logo_url"]:
            company.logo_url = data["logo_url"]

        # Store all enrichment data in brand_info
        company.brand_info = data

        company.save()
        logger.debug(f"Updated company {company.domain} with enrichment data")
