import logging

from django.conf import settings

from ..providers.brandfetch import BrandfetchProvider

logger = logging.getLogger(__name__)


class DomainEnrichmentService:
    def __init__(self):
        self.providers = self._initialize_providers()

    def _initialize_providers(self):
        """Initializing active providers"""
        providers = []

        # Add Brandfetch provider if API key is configured
        if hasattr(settings, "BRANDFETCH_API_KEY") and settings.BRANDFETCH_API_KEY:
            providers.append(BrandfetchProvider())

        return providers

    def enrich_domain(self, domain: str):
        """Enriches domain data using all available providers"""
        from core.models import Company

        company, created = Company.objects.get_or_create(domain=domain)

        if not created and (company.name or company.logo_url):
            return company

        for provider in self.providers:
            try:
                enriched_data = provider.enrich_domain(domain)
                if enriched_data:
                    self._update_company(
                        company, enriched_data, provider.get_provider_name()
                    )
            except Exception as e:
                logger.error(
                    f"Error enriching domain with "
                    f"{provider.get_provider_name()}: {str(e)}"
                )

        return company

    def _update_company(self, company, data, provider_name):
        update_fields = []

        if data.get("name") and not company.name:
            company.name = data["name"]
            update_fields.append("name")

        if data.get("logo_url") and not company.logo_url:
            company.logo_url = data["logo_url"]
            update_fields.append("logo_url")

        if data.get("brand_info"):
            if not company.brand_info:
                company.brand_info = {}
            company.brand_info[provider_name] = data["brand_info"]
            update_fields.append("brand_info")

        if update_fields:
            company.save(update_fields=update_fields)
