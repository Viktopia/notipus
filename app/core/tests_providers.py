from unittest.mock import Mock, patch

import requests
from core.providers.base import BaseEnrichmentProvider
from core.providers.brandfetch import BrandfetchProvider
from django.test import TestCase
from requests.exceptions import HTTPError, Timeout


class BaseEnrichmentProviderTest(TestCase):
    """Test base enrichment provider abstract class"""

    def test_get_provider_name(self):
        """Test provider name generation"""

        class TestProvider(BaseEnrichmentProvider):
            def enrich_domain(self, domain: str) -> dict:
                return {}

        provider = TestProvider()
        self.assertEqual(provider.get_provider_name(), "testprovider")

    def test_abstract_method_enforcement(self):
        """Test that abstract method must be implemented"""
        with self.assertRaises(TypeError):
            BaseEnrichmentProvider()  # Can't instantiate abstract class


class BrandfetchProviderTest(TestCase):
    """Test Brandfetch provider"""

    def setUp(self):
        """Set up test data"""
        self.api_key = "test_api_key"
        self.base_url = "https://api.brandfetch.io/v2"
        self.provider = BrandfetchProvider(api_key=self.api_key, base_url=self.base_url)

    def test_init_with_api_key(self):
        """Test provider initialization with API key"""
        provider = BrandfetchProvider(api_key="test_key")
        self.assertEqual(provider.api_key, "test_key")
        self.assertEqual(provider.base_url, "https://api.brandfetch.io/v2")

    def test_init_without_api_key(self):
        """Test provider initialization without API key"""
        with patch("core.providers.brandfetch.getattr") as mock_getattr:
            mock_getattr.return_value = "settings_key"
            provider = BrandfetchProvider()
            self.assertEqual(provider.api_key, "settings_key")

    def test_init_no_api_key_available(self):
        """Test provider initialization when no API key available"""
        with patch("django.conf.settings", spec=[]):
            # Mock getattr to return None
            with patch("core.providers.brandfetch.getattr", return_value=None):
                provider = BrandfetchProvider()
                self.assertIsNone(provider.api_key)

    def test_enrich_domain_no_api_key(self):
        """Test enrichment fails gracefully without API key"""
        provider = BrandfetchProvider(api_key=None)

        with patch("core.providers.brandfetch.logger") as mock_logger:
            result = provider.enrich_domain("example.com")

            self.assertEqual(result, {})
            mock_logger.error.assert_called_once_with(
                "Brandfetch API key is not configured"
            )

    @patch("core.providers.brandfetch.requests.get")
    def test_enrich_domain_success(self, mock_get):
        """Test successful domain enrichment"""
        # Mock successful API responses
        mock_brand_response = Mock()
        mock_brand_response.json.return_value = {
            "name": "Example Company",
            "description": "A great company",
            "industry": "Technology",
            "yearFounded": 2020,
            "links": [{"url": "https://example.com"}],
            "colors": [{"hex": "#FF0000"}],
        }
        mock_brand_response.headers = {
            "x-api-key-quota": "1000",
            "x-api-key-approximate-usage": "250",
        }
        mock_brand_response.raise_for_status.return_value = None

        mock_logos_response = Mock()
        mock_logos_response.json.return_value = [
            {"type": "icon", "formats": [{"src": "https://example.com/logo.png"}]}
        ]
        mock_logos_response.raise_for_status.return_value = None

        mock_get.side_effect = [mock_brand_response, mock_logos_response]

        result = self.provider.enrich_domain("example.com")

        expected = {
            "name": "Example Company",
            "logo_url": "https://example.com/logo.png",
            "brand_info": {
                "description": "A great company",
                "industry": "Technology",
                "year_founded": 2020,
                "links": [{"url": "https://example.com"}],
                "colors": [{"hex": "#FF0000"}],
            },
        }

        self.assertEqual(result, expected)
        self.assertEqual(mock_get.call_count, 2)

        # Check API calls were made with correct parameters
        expected_headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        mock_get.assert_any_call(
            f"{self.base_url}/brands/example.com",
            headers=expected_headers,
            timeout=10,
        )
        mock_get.assert_any_call(
            f"{self.base_url}/brands/example.com/logos",
            headers=expected_headers,
            timeout=10,
        )

    @patch("core.providers.brandfetch.requests.get")
    def test_enrich_domain_missing_data(self, mock_get):
        """Test enrichment with missing data fields"""
        # Mock API responses with missing fields
        mock_brand_response = Mock()
        mock_brand_response.json.return_value = {}  # Empty response
        mock_brand_response.raise_for_status.return_value = None

        mock_logos_response = Mock()
        mock_logos_response.json.return_value = []  # No logos
        mock_logos_response.raise_for_status.return_value = None

        mock_get.side_effect = [mock_brand_response, mock_logos_response]

        result = self.provider.enrich_domain("example.com")

        expected = {
            "name": None,
            "logo_url": None,
            "brand_info": {
                "description": None,
                "industry": None,
                "year_founded": None,
                "links": [],
                "colors": [],
            },
        }

        self.assertEqual(result, expected)

    @patch("core.providers.brandfetch.requests.get")
    def test_enrich_domain_http_error(self, mock_get):
        """Test enrichment with HTTP error"""
        mock_get.side_effect = HTTPError("404 Not Found")

        with patch("core.providers.brandfetch.logger") as mock_logger:
            result = self.provider.enrich_domain("nonexistent.com")

            self.assertEqual(result, {})
            mock_logger.error.assert_called_once()
            self.assertIn(
                "Error fetching data from Brandfetch", mock_logger.error.call_args[0][0]
            )

    @patch("core.providers.brandfetch.requests.get")
    def test_enrich_domain_timeout(self, mock_get):
        """Test enrichment with timeout"""
        mock_get.side_effect = Timeout("Request timed out")

        with patch("core.providers.brandfetch.logger") as mock_logger:
            result = self.provider.enrich_domain("example.com")

            self.assertEqual(result, {})
            mock_logger.error.assert_called_once()

    @patch("core.providers.brandfetch.requests.get")
    def test_enrich_domain_connection_error(self, mock_get):
        """Test enrichment with connection error"""
        mock_get.side_effect = requests.ConnectionError("Connection failed")

        with patch("core.providers.brandfetch.logger") as mock_logger:
            result = self.provider.enrich_domain("example.com")

            self.assertEqual(result, {})
            mock_logger.error.assert_called_once()

    def test_get_primary_logo_success(self):
        """Test successful logo extraction"""
        logos_data = [
            {"type": "icon", "formats": [{"src": "https://example.com/logo.png"}]},
            {"type": "banner", "formats": [{"src": "https://example.com/banner.png"}]},
        ]

        result = self.provider._get_primary_logo(logos_data)
        self.assertEqual(result, "https://example.com/logo.png")

    def test_get_primary_logo_no_icon(self):
        """Test logo extraction without icon type"""
        logos_data = [
            {"type": "banner", "formats": [{"src": "https://example.com/banner.png"}]}
        ]

        result = self.provider._get_primary_logo(logos_data)
        self.assertIsNone(result)

    def test_get_primary_logo_no_formats(self):
        """Test logo extraction without formats"""
        logos_data = [
            {
                "type": "icon"
                # Missing formats
            }
        ]

        result = self.provider._get_primary_logo(logos_data)
        self.assertIsNone(result)

    def test_get_primary_logo_empty_data(self):
        """Test logo extraction with empty data"""
        result = self.provider._get_primary_logo([])
        self.assertIsNone(result)

        result = self.provider._get_primary_logo(None)
        self.assertIsNone(result)

    def test_get_primary_logo_no_src(self):
        """Test logo extraction without src field"""
        logos_data = [
            {
                "type": "icon",
                "formats": [
                    {}  # Missing src
                ],
            }
        ]

        result = self.provider._get_primary_logo(logos_data)
        self.assertIsNone(result)

    def test_get_provider_name(self):
        """Test provider name"""
        self.assertEqual(self.provider.get_provider_name(), "brandfetchprovider")

    @patch("core.providers.brandfetch.requests.get")
    def test_enrich_domain_rate_limit(self, mock_get):
        """Test rate limit handling"""
        from requests.exceptions import HTTPError

        # Mock rate limit response
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.headers = {"Retry-After": "120"}

        # Create HTTPError with the mock response
        http_error = HTTPError()
        http_error.response = mock_response
        mock_get.side_effect = http_error

        with patch("core.providers.brandfetch.logger") as mock_logger:
            result = self.provider.enrich_domain("example.com")

            self.assertEqual(result, {})
            mock_logger.warning.assert_called_once_with(
                "Brandfetch rate limit exceeded. Retry after 120 seconds"
            )
