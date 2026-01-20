"""Brandfetch API provider for domain enrichment.

This module provides integration with the Brandfetch API v2 to retrieve
brand information including logos, colors, and company details.
"""

import logging
from typing import Any

import requests
from django.conf import settings

from .base import BaseEnrichmentProvider

logger = logging.getLogger(__name__)


class BrandfetchProvider(BaseEnrichmentProvider):
    """Provider for enriching domains with brand data from Brandfetch API."""

    def __init__(
        self, api_key: str | None = None, base_url: str = "https://api.brandfetch.io/v2"
    ) -> None:
        """Initialize the Brandfetch provider.

        Args:
            api_key: Optional API key. Falls back to settings.BRANDFETCH_API_KEY.
            base_url: Base URL for the Brandfetch API.
        """
        self.api_key = api_key or getattr(settings, "BRANDFETCH_API_KEY", None)
        self.base_url = base_url

    def enrich_domain(self, domain: str) -> dict[str, Any]:
        """Enrich domain with brand data from Brandfetch API v2.

        The /v2/brands/{domain} endpoint returns all brand data including logos
        in a single response. There is no separate /logos endpoint.

        API Documentation: https://docs.brandfetch.com/reference/brand-api

        Args:
            domain: The domain to enrich (e.g., "example.com").

        Returns:
            Dictionary containing brand name, logo URL, and brand info,
            or empty dict on failure.
        """
        if not self.api_key:
            logger.error("Brandfetch API key is not configured")
            return {}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            # Add timeout for reliability
            timeout = 10  # seconds

            response = requests.get(
                f"{self.base_url}/brands/{domain}", headers=headers, timeout=timeout
            )
            response.raise_for_status()
            brand_data = response.json()

            # Check quota usage from response headers
            self._log_quota_usage(response.headers)

            # Logos are included in the main brands response under the "logos" array
            # No separate /logos endpoint exists in the Brandfetch API v2
            logos_data = brand_data.get("logos", [])

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
            # Handle rate limiting specifically
            if (
                hasattr(e, "response")
                and e.response is not None
                and e.response.status_code == 429
            ):
                retry_after = e.response.headers.get("Retry-After", "60")
                logger.warning(
                    f"Brandfetch rate limit exceeded. Retry after {retry_after} seconds"
                )
            else:
                logger.error(f"Error fetching data from Brandfetch: {e!s}")
            return {}

    def _get_primary_logo(self, logos_data: list[dict[str, Any]]) -> str | None:
        """Retrieve the URL of the main logo.

        Args:
            logos_data: List of logo dictionaries from the API response.

        Returns:
            URL of the primary logo, or None if not found.
        """
        if not logos_data:
            return None

        for logo in logos_data:
            if logo.get("type") == "icon" and logo.get("formats"):
                for fmt in logo["formats"]:
                    if fmt.get("src"):
                        return fmt["src"]
        return None

    def _log_quota_usage(self, headers: Any) -> None:
        """Log API quota usage from response headers.

        Args:
            headers: Response headers from the Brandfetch API.
        """
        try:
            quota = headers.get("x-api-key-quota")
            usage = headers.get("x-api-key-approximate-usage")

            if quota and usage and str(quota).isdigit() and str(usage).isdigit():
                quota_int = int(quota)
                usage_int = int(usage)
                usage_pct = (usage_int / quota_int) * 100
                logger.info(f"Brandfetch API usage: {usage}/{quota} ({usage_pct:.1f}%)")

                if usage_pct > 80:
                    logger.warning(f"Brandfetch API usage high: {usage_pct:.1f}%")
            elif quota and str(quota).isdigit():
                logger.debug(f"Brandfetch API quota: {quota}")
            elif usage and str(usage).isdigit():
                logger.debug(f"Brandfetch API usage: {usage}")
        except (ValueError, TypeError, ZeroDivisionError) as e:
            logger.debug(f"Could not parse quota headers: {e}")
