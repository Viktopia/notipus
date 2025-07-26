import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from decimal import Decimal

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)


class RateLimitException(Exception):
    """Raised when rate limit is exceeded"""
    def __init__(self, message: str, limit: int, current_usage: int, reset_time: datetime):
        self.message = message
        self.limit = limit
        self.current_usage = current_usage
        self.reset_time = reset_time
        super().__init__(message)


class RateLimiter:
    """
    Rate limiter for webhook notifications based on subscription plans.
    Uses Redis/Django cache for efficient counting.
    """

    # Plan limits mapping
    PLAN_LIMITS = {
        "trial": 1000,
        "basic": 10000,
        "pro": 100000,
        "enterprise": 1000000,  # 1 million events/month
    }

    def __init__(self):
        self.cache_timeout = 60 * 60 * 24 * 31  # 31 days for monthly limits

    def get_cache_key(self, organization_uuid: str, month: str) -> str:
        """Generate cache key for organization monthly usage"""
        return f"webhook_usage:{organization_uuid}:{month}"

    def get_current_month_key(self) -> str:
        """Get current month key in YYYY-MM format"""
        return timezone.now().strftime("%Y-%m")

    def get_organization_limit(self, organization) -> int:
        """Get the webhook limit for an organization based on their plan"""
        plan = organization.subscription_plan
        return self.PLAN_LIMITS.get(plan, 1000)  # Default to trial limit

    def check_rate_limit(self, organization) -> Tuple[bool, Dict[str, any]]:
        """
        Check if organization is within rate limits.

        Returns:
            Tuple[bool, Dict]: (is_allowed, rate_limit_info)
        """
        try:
            organization_uuid = str(organization.uuid)
            current_month = self.get_current_month_key()
            cache_key = self.get_cache_key(organization_uuid, current_month)

            # Get current usage
            current_usage = cache.get(cache_key, 0)
            limit = self.get_organization_limit(organization)

            # Check if within limits
            is_allowed = current_usage < limit

            # Calculate reset time (first day of next month)
            now = timezone.now()
            if now.month == 12:
                reset_time = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            else:
                reset_time = now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)

            rate_limit_info = {
                "limit": limit,
                "current_usage": current_usage,
                "remaining": max(0, limit - current_usage),
                "reset_time": reset_time,
                "plan": organization.subscription_plan,
            }

            return is_allowed, rate_limit_info

        except Exception as e:
            logger.error(f"Error checking rate limit for organization {organization.uuid}: {str(e)}")
            # Fail open - allow request if rate limiting fails
            return True, {
                "limit": 0,
                "current_usage": 0,
                "remaining": 0,
                "reset_time": timezone.now(),
                "plan": "unknown",
                "error": str(e)
            }

    def increment_usage(self, organization) -> int:
        """
        Increment usage counter for organization and return new count.
        """
        try:
            organization_uuid = str(organization.uuid)
            current_month = self.get_current_month_key()
            cache_key = self.get_cache_key(organization_uuid, current_month)

            # Increment and get new value
            new_count = cache.get(cache_key, 0) + 1
            cache.set(cache_key, new_count, timeout=self.cache_timeout)

            logger.info(f"Incremented webhook usage for org {organization_uuid} to {new_count}")
            return new_count

        except Exception as e:
            logger.error(f"Error incrementing usage for organization {organization.uuid}: {str(e)}")
            return 0

    def enforce_rate_limit(self, organization) -> Dict[str, any]:
        """
        Check rate limit and raise exception if exceeded.
        If within limits, increment usage counter.

        Returns:
            Dict: Rate limit information
        """
        is_allowed, rate_limit_info = self.check_rate_limit(organization)

        if not is_allowed:
            raise RateLimitException(
                f"Rate limit exceeded for plan '{organization.subscription_plan}'. "
                f"Limit: {rate_limit_info['limit']}, Current usage: {rate_limit_info['current_usage']}",
                limit=rate_limit_info['limit'],
                current_usage=rate_limit_info['current_usage'],
                reset_time=rate_limit_info['reset_time']
            )

        # Increment usage if allowed
        new_usage = self.increment_usage(organization)
        rate_limit_info['current_usage'] = new_usage
        rate_limit_info['remaining'] = max(0, rate_limit_info['limit'] - new_usage)

        return rate_limit_info

    def get_rate_limit_headers(self, rate_limit_info: Dict[str, any]) -> Dict[str, str]:
        """
        Generate HTTP headers for rate limiting information.
        """
        headers = {
            "X-RateLimit-Limit": str(rate_limit_info.get('limit', 0)),
            "X-RateLimit-Remaining": str(rate_limit_info.get('remaining', 0)),
            "X-RateLimit-Used": str(rate_limit_info.get('current_usage', 0)),
            "X-RateLimit-Reset": str(int(rate_limit_info.get('reset_time', timezone.now()).timestamp())),
            "X-RateLimit-Plan": rate_limit_info.get('plan', 'unknown'),
        }

        return headers

    def get_usage_stats(self, organization, months: int = 6) -> Dict[str, int]:
        """
        Get usage statistics for an organization over the last N months.
        """
        stats = {}
        current_date = timezone.now()
        organization_uuid = str(organization.uuid)

        for i in range(months):
            # Calculate month
            if current_date.month - i <= 0:
                month = current_date.month - i + 12
                year = current_date.year - 1
            else:
                month = current_date.month - i
                year = current_date.year

            month_key = f"{year:04d}-{month:02d}"
            cache_key = self.get_cache_key(organization_uuid, month_key)
            usage = cache.get(cache_key, 0)
            stats[month_key] = usage

        return stats


# Global rate limiter instance
rate_limiter = RateLimiter()