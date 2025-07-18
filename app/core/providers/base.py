import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseEnrichmentProvider(ABC):
    @abstractmethod
    def enrich_domain(self, domain: str) -> dict:
        """The main method for enriching domain data"""
        pass

    def get_provider_name(self) -> str:
        """Returns the name of the provider"""
        return self.__class__.__name__.lower()
