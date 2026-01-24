"""Views for serving company logos from the database."""

import logging

from core.models import Company
from django.http import Http404, HttpResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import cache_control

logger = logging.getLogger(__name__)


@method_decorator(cache_control(max_age=86400, public=True), name="dispatch")
class CompanyLogoView(View):
    """Serve company logos from database storage.

    This view serves logos stored as binary data in the Company model.
    Logos are publicly accessible (no authentication required) so that
    Slack can fetch them for message previews.

    URL: /logos/<domain>/
    Example: https://app.notipus.com/logos/acme.com/

    Includes caching headers for browser and CDN caching (24 hours).
    """

    def get(self, request, domain: str) -> HttpResponse:
        """Serve logo for the given domain.

        Args:
            request: HTTP request.
            domain: Company domain to serve logo for.

        Returns:
            HttpResponse with logo data or 404.
        """
        try:
            company = Company.objects.only(
                "logo_data", "logo_content_type", "domain"
            ).get(domain=domain)
        except Company.DoesNotExist as e:
            raise Http404("Company not found") from e

        if not company.logo_data:
            raise Http404("Logo not found")

        content_type = company.logo_content_type or "image/png"

        response = HttpResponse(company.logo_data, content_type=content_type)
        response["Content-Length"] = len(company.logo_data)

        return response
