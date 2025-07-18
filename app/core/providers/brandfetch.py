import requests
from django.conf import settings
from .base import BaseEnrichmentProvider
import logging

logger = logging.getLogger(__name__)


class BrandfetchProvider(BaseEnrichmentProvider):
    def __init__(self, api_key=None, base_url="https://api.brandfetch.io/v2"):
        self.api_key = api_key or getattr(settings, "BRANDFETCH_API_KEY", None)
        self.base_url = base_url

    def enrich_domain(self, domain: str) -> dict:
        if not self.api_key:
            logger.error("Brandfetch API key is not configured")
            return {}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.get(
                f"{self.base_url}/companies/{domain}", headers=headers
            )
            response.raise_for_status()
            brand_data = response.json()

            logos_response = requests.get(
                f"{self.base_url}/companies/{domain}/logos", headers=headers
            )
            logos_response.raise_for_status()
            logos_data = logos_response.json()

            return {
                "name": brand_data.get("name"),
                "logo_url": self._get_primary_logo(logos_data),
                "brand_info": {
                    "description": brand_data.get("description"),
                    "industry": brand_data.get("industry"),
                    "year_founded": brand_data.get("yearFounded"),
                    "links": brand_data.get("links", []),
                    "colors": brand_data.get("colors", []),
                },
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching data from Brandfetch: {str(e)}")
            return {}

    def _get_primary_logo(self, logos_data):
        """Retrieves the URL of the main logo"""
        if not logos_data:
            return None

        for logo in logos_data:
            if logo.get("type") == "icon" and logo.get("formats"):
                for format in logo["formats"]:
                    if format.get("src"):
                        return format["src"]
        return None
