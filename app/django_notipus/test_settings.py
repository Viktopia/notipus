from .settings import *  # noqa: F403

# Override database to use SQLite for tests
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Test-specific environment overrides
SECRET_KEY = "test-secret-key-for-testing-only"
DEBUG = True

# Override settings for tests
DISABLE_BILLING = True
CHARGIFY_WEBHOOK_SECRET = "test-chargify-secret"
SHOPIFY_WEBHOOK_SECRET = "test-shopify-secret"
STRIPE_WEBHOOK_SECRET = "test-stripe-secret"


# Enable migrations for testing - we need to test migrations on in-memory SQL
# MIGRATION_MODULES removed to enable migrations

# Use console email backend for tests
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Disable caching for tests
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache",
    }
}

# Speed up password hashing for tests
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Disable logging during tests
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "null": {
            "class": "logging.NullHandler",
        },
    },
    "root": {
        "handlers": ["null"],
    },
}
