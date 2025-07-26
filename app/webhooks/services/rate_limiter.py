import logging
import time
from datetime import datetime
from typing import Dict, Optional, Tuple

from django.core.cache import cache
from django.core.cache.backends.base import InvalidCacheBackendError
from django.utils import timezone

logger = logging.getLogger(__name__)


class RedisCircuitBreaker:
    """
    Circuit breaker pattern for Redis operations to handle cache failures gracefully.
    """

    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN

    def is_circuit_open(self) -> bool:
        """Check if circuit is open (Redis is considered down)"""
        if self.state == "OPEN":
            if (
                self.last_failure_time
                and time.time() - self.last_failure_time > self.recovery_timeout
            ):
                self.state = "HALF_OPEN"
                logger.info("Redis circuit breaker entering HALF_OPEN state")
                return False
            return True
        return False

    def record_success(self):
        """Record successful Redis operation"""
        if self.state == "HALF_OPEN":
            self.state = "CLOSED"
            self.failure_count = 0
            self.last_failure_time = None
            logger.info("Redis circuit breaker returned to CLOSED state")

    def record_failure(self):
        """Record failed Redis operation"""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.warning(
                f"Redis circuit breaker opened after {self.failure_count} failures"
            )

    def call_with_circuit_breaker(self, func, *args, **kwargs):
        """Execute function with circuit breaker protection"""
        if self.is_circuit_open():
            raise RedisUnavailableError("Redis circuit breaker is OPEN")

        try:
            result = func(*args, **kwargs)
            self.record_success()
            return result
        except Exception as e:
            self.record_failure()
            raise RedisUnavailableError(f"Redis operation failed: {str(e)}") from e


class RedisUnavailableError(Exception):
    """Raised when Redis is unavailable"""

    pass


class RateLimitException(Exception):
    """Raised when rate limit is exceeded"""

    def __init__(
        self, message: str, limit: int, current_usage: int, reset_time: datetime
    ):
        self.message = message
        self.limit = limit
        self.current_usage = current_usage
        self.reset_time = reset_time
        super().__init__(message)


class RateLimiter:
    """
    Rate limiter for webhook notifications based on subscription plans.
    Uses Redis/Django cache for efficient counting with fallback mechanisms.
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
        self.circuit_breaker = RedisCircuitBreaker()
        self._in_memory_fallback = {}  # In-memory fallback for Redis failures
        self._fallback_timeout = 300  # 5 minutes for in-memory cache

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

    def _safe_cache_get(self, key: str, default: int = 0) -> int:
        """Get value from cache with fallback to in-memory storage"""
        try:
            return self.circuit_breaker.call_with_circuit_breaker(
                cache.get, key, default
            )
        except (RedisUnavailableError, InvalidCacheBackendError, Exception) as e:
            logger.warning(f"Cache GET failed for key {key}, using fallback: {str(e)}")
            return self._get_from_fallback(key, default)

    def _safe_cache_set(
        self, key: str, value: int, timeout: Optional[int] = None
    ) -> bool:
        """Set value in cache with fallback to in-memory storage"""
        try:
            self.circuit_breaker.call_with_circuit_breaker(
                cache.set, key, value, timeout or self.cache_timeout
            )
            # Also update fallback in case Redis goes down later
            self._set_to_fallback(key, value)
            return True
        except (RedisUnavailableError, InvalidCacheBackendError, Exception) as e:
            logger.warning(f"Cache SET failed for key {key}, using fallback: {str(e)}")
            self._set_to_fallback(key, value)
            return False

    def _get_from_fallback(self, key: str, default: int = 0) -> int:
        """Get value from in-memory fallback with expiration"""
        if key in self._in_memory_fallback:
            value, timestamp = self._in_memory_fallback[key]
            if time.time() - timestamp < self._fallback_timeout:
                return value
            else:
                # Expired, remove from fallback
                del self._in_memory_fallback[key]
        return default

    def _set_to_fallback(self, key: str, value: int):
        """Set value in in-memory fallback with timestamp"""
        self._in_memory_fallback[key] = (value, time.time())

        # Clean up expired entries to prevent memory leaks
        current_time = time.time()
        expired_keys = [
            k
            for k, (_, timestamp) in self._in_memory_fallback.items()
            if current_time - timestamp >= self._fallback_timeout
        ]
        for expired_key in expired_keys:
            del self._in_memory_fallback[expired_key]

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

            # Get current usage using safe cache operations
            current_usage = self._safe_cache_get(cache_key, 0)
            limit = self.get_organization_limit(organization)

            # Check if within limits
            is_allowed = current_usage < limit

            # Calculate reset time (first day of next month)
            now = timezone.now()
            if now.month == 12:
                reset_time = now.replace(
                    year=now.year + 1,
                    month=1,
                    day=1,
                    hour=0,
                    minute=0,
                    second=0,
                    microsecond=0,
                )
            else:
                reset_time = now.replace(
                    month=now.month + 1,
                    day=1,
                    hour=0,
                    minute=0,
                    second=0,
                    microsecond=0,
                )

            rate_limit_info = {
                "limit": limit,
                "current_usage": current_usage,
                "remaining": max(0, limit - current_usage),
                "reset_time": reset_time,
                "plan": organization.subscription_plan,
                "fallback_mode": self.circuit_breaker.state != "CLOSED",
            }

            return is_allowed, rate_limit_info

        except Exception as e:
            logger.error(
                f"Error checking rate limit for organization "
                f"{organization.uuid}: {str(e)}"
            )
            # Fail open - allow request if rate limiting fails completely
            return True, {
                "limit": self.get_organization_limit(organization),
                "current_usage": 0,
                "remaining": self.get_organization_limit(organization),
                "reset_time": timezone.now(),
                "plan": organization.subscription_plan,
                "fallback_mode": True,
                "error": str(e),
            }

    def increment_usage(self, organization) -> int:
        """
        Increment usage counter for organization and return new count.
        """
        try:
            organization_uuid = str(organization.uuid)
            current_month = self.get_current_month_key()
            cache_key = self.get_cache_key(organization_uuid, current_month)

            # Get current value and increment using safe cache operations
            current_count = self._safe_cache_get(cache_key, 0)
            new_count = current_count + 1
            self._safe_cache_set(cache_key, new_count)

            logger.info(
                f"Incremented webhook usage for org {organization_uuid} to {new_count} "
                f"(fallback_mode: {self.circuit_breaker.state != 'CLOSED'})"
            )
            return new_count

        except Exception as e:
            logger.error(
                f"Error incrementing usage for organization "
                f"{organization.uuid}: {str(e)}"
            )
            # Return 1 to indicate at least this request was processed
            return 1

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
                f"Limit: {rate_limit_info['limit']}, "
                f"Current usage: {rate_limit_info['current_usage']}",
                limit=rate_limit_info["limit"],
                current_usage=rate_limit_info["current_usage"],
                reset_time=rate_limit_info["reset_time"],
            )

        # Increment usage if allowed
        new_usage = self.increment_usage(organization)
        rate_limit_info["current_usage"] = new_usage
        rate_limit_info["remaining"] = max(0, rate_limit_info["limit"] - new_usage)

        return rate_limit_info

    def get_rate_limit_headers(self, rate_limit_info: Dict[str, any]) -> Dict[str, str]:
        """
        Generate HTTP headers for rate limiting information.
        """
        headers = {
            "X-RateLimit-Limit": str(rate_limit_info.get("limit", 0)),
            "X-RateLimit-Remaining": str(rate_limit_info.get("remaining", 0)),
            "X-RateLimit-Used": str(rate_limit_info.get("current_usage", 0)),
            "X-RateLimit-Reset": str(
                int(rate_limit_info.get("reset_time", timezone.now()).timestamp())
            ),
            "X-RateLimit-Plan": rate_limit_info.get("plan", "unknown"),
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
            usage = self._safe_cache_get(cache_key, 0)
            stats[month_key] = usage

        return stats


# Global rate limiter instance
rate_limiter = RateLimiter()
