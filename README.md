# Notipus - Webhook to Slack Notifier

A webhook-driven notification service that sends enriched payment and subscription events from Shopify and Chargify to Slack. The service provides meaningful, actionable insights for customer success teams with a fun and engaging tone.

## Features

- 🎯 **Smart Event Processing**: Automatically categorizes and prioritizes events based on type and customer value
- 💡 **Rich Context**: Enriches notifications with customer history, metrics, and actionable insights
- 🎨 **Engaging Messages**: Uses whimsical language and emojis to make notifications fun and memorable
- 📊 **Business Metrics**: Includes relevant business metrics like lifetime value and payment history
- 🔄 **Event Analysis**: Analyzes events to provide actionable recommendations
- ⚡ **Multiple Payment Providers**: Supports both Shopify and Chargify webhooks

## Tech Stack

- **Backend**: Django 5.x, Python 3.12+
- **Database**: PostgreSQL 17
- **Cache**: Redis 7
- **Package Manager**: [uv](https://docs.astral.sh/uv/) (fast Python package manager from Astral)
- **Linting/Formatting**: [ruff](https://docs.astral.sh/ruff/)
- **Testing**: pytest with pytest-django
- **Containerization**: Docker with docker-compose

## Installation

### Using Docker (Recommended)

1. **Clone the repository**

```bash
git clone git@github.com:viktopia/notipus.git
cd notipus
```

2. **Build the Docker images**

```bash
docker-compose build
```

3. **Set environment variables**

The application reads configuration from environment variables. Set these before running:

```bash
export SECRET_DJANGO_KEY=your-secure-secret-key-here
export DEBUG=True

# Notipus billing (for subscription revenue)
export NOTIPUS_STRIPE_SECRET_KEY=sk_test_your_stripe_key
export NOTIPUS_STRIPE_WEBHOOK_SECRET=whsec_your_webhook_secret

# Optional: Override other settings
export DB_PASSWORD=secure_db_password
```

> **Note**: Webhook secrets for customer integrations are managed per-tenant through the web interface.

4. **Run the containers**

```bash
docker-compose up -d
```

5. **Verify the setup**

```bash
docker-compose logs -f
```

Access the application at http://localhost:8000.

6. **Stop the containers**

```bash
docker-compose down
```

### Local Development

1. **Clone the repository**

```bash
git clone git@github.com:Viktopia/notipus.git
cd notipus
```

2. **Install uv** (Python package manager)

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or with Homebrew
brew install uv
```

3. **Install dependencies**

```bash
uv sync --all-groups
```

4. **Set environment variables**

```bash
export SECRET_DJANGO_KEY=your-secure-secret-key-here
export DEBUG=True
export DB_NAME=notipus_dev
export DB_USER=postgres
export DB_PASSWORD=postgres
export DB_HOST=localhost
```

5. **Start PostgreSQL and Redis** (using Docker)

```bash
docker-compose up -d db redis
```

6. **Run migrations**

```bash
uv run python app/manage.py migrate
```

7. **Start the development server**

```bash
uv run python app/manage.py runserver
```

## Development

### Install dependencies

```bash
# Install all dependencies (including dev tools)
uv sync --all-groups

# Update all dependencies to latest versions
uv lock --upgrade && uv sync --all-groups
```

### Run tests

```bash
# Run all tests
uv run pytest

# Run with coverage report
uv run pytest --cov=app --cov-report=term-missing

# Run a specific test file
uv run pytest tests/test_webhooks.py

# Run tests matching a pattern
uv run pytest -k "test_shopify"
```

### Code quality

```bash
# Format code
uv run ruff format .

# Run linter
uv run ruff check .

# Auto-fix linting issues
uv run ruff check --fix .

# Type checking
uv run mypy app/
```

### Pre-commit hooks

```bash
# Install pre-commit hooks
uv run pre-commit install

# Run hooks manually on all files
uv run pre-commit run --all-files
```

### Django management commands

```bash
# Create a superuser
uv run python app/manage.py createsuperuser

# Make migrations
uv run python app/manage.py makemigrations

# Run migrations
uv run python app/manage.py migrate

# Collect static files
uv run python app/manage.py collectstatic
```

## Architecture

The service is built with a modular, multi-tenant architecture that separates concerns and makes it easy to extend:

```
app/
├── core/              # Core application (users, organizations, billing)
│   ├── models.py          # Organization, Integration, Company, UserProfile, etc.
│   ├── services/
│   │   ├── stripe.py      # Stripe billing API client
│   │   ├── shopify.py     # Shopify Admin API client
│   │   ├── enrichment.py  # Domain enrichment service
│   │   ├── dashboard.py   # Dashboard data aggregation
│   │   └── webauthn.py    # Passwordless authentication
│   └── providers/
│       ├── base.py        # BaseEnrichmentProvider
│       └── brandfetch.py  # Domain/brand enrichment
├── webhooks/
│   ├── providers/     # Payment gateway integrations
│   │   ├── base.py        # PaymentProvider abstract class
│   │   ├── chargify.py    # Chargify/Maxio webhook processor
│   │   ├── shopify.py     # Shopify webhook processor
│   │   └── stripe.py      # Stripe webhook processor
│   ├── services/
│   │   ├── event_processor.py  # Event processing and notification formatting
│   │   ├── slack_client.py     # Slack incoming webhooks client
│   │   ├── billing.py          # Notipus subscription billing handler
│   │   ├── rate_limiter.py     # Rate limiting with circuit breaker
│   │   └── database_lookup.py  # Recent activity storage (Redis)
│   ├── models/
│   │   └── notification.py
│   └── webhook_router.py  # Multi-tenant webhook routing
└── django_notipus/    # Django project settings
```

### Multi-Tenant Architecture

Notipus is designed as a multi-tenant SaaS platform where each organization manages their own integrations:

- **Organizations**: Each tenant (organization) has their own webhook endpoints, integrations, and Slack configurations
- **Webhook Endpoints**: Organization-specific webhooks at `/webhooks/customer/{org_uuid}/{provider}/`
- **Integration Storage**: Credentials and settings stored per-organization in the `Integration` model
- **Isolation**: Each organization's data is isolated and rate-limited independently

### Authentication

Notipus supports multiple authentication methods:

1. **Slack OAuth (Sign in with Slack)**: Primary authentication method using OpenID Connect
2. **WebAuthn/Passkeys**: Passwordless authentication for enhanced security
3. **Django Sessions**: Traditional session-based auth for API access

### Domain Enrichment (Brandfetch)

The Brandfetch integration enriches company domains with brand information:

- Automatically fetches company logos, colors, and descriptions
- Caches results in the `Company` model to reduce API calls
- Used to enhance Slack notifications with company branding

### Rate Limiting & Circuit Breaker

The webhook system includes robust rate limiting:

- **Per-Organization Limits**: Configurable limits based on subscription plan
- **Redis-Backed**: Uses Redis for distributed rate limit tracking
- **Circuit Breaker**: Automatically disables failing integrations to prevent cascading failures
- **Graceful Degradation**: Falls back to in-memory counting if Redis is unavailable

### Caching (Redis)

Redis is used for multiple purposes:

- **Rate Limit Tracking**: Per-organization request counts with TTL
- **Recent Activity**: Last 7 days of webhook activity for dashboard display
- **Session Cache**: Django session storage (configurable)
- **Circuit Breaker State**: Tracks integration health status

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Install dependencies: `uv sync --all-groups`
4. Make your changes and ensure tests pass: `uv run pytest`
5. Format and lint: `uv run ruff format . && uv run ruff check .`
6. Commit your changes: `git commit -m 'Add amazing feature'`
7. Push to the branch: `git push origin feature/amazing-feature`
8. Open a pull request

## Configuration

### Core Environment Variables

**Required for production:**

- `SECRET_DJANGO_KEY`: Django secret key for cryptographic operations
- `DB_PASSWORD`: Database password for PostgreSQL

**Notipus billing (subscription revenue):**

- `STRIPE_SECRET_KEY`: Stripe secret key for processing subscriptions
- `STRIPE_PUBLISHABLE_KEY`: Stripe publishable key for frontend integration
- `STRIPE_API_VERSION`: Stripe API version (default: `2025-12-18.acacia`)
- `NOTIPUS_STRIPE_WEBHOOK_SECRET`: Webhook secret for Stripe billing events

**Stripe Checkout and Portal URLs:**

- `STRIPE_SUCCESS_URL`: Redirect URL after successful checkout (default: `http://localhost:8000/billing/checkout/success/`)
- `STRIPE_CANCEL_URL`: Redirect URL after cancelled checkout (default: `http://localhost:8000/billing/checkout/cancel/`)
- `STRIPE_PORTAL_RETURN_URL`: Return URL from Customer Portal (default: `http://localhost:8000/billing/`)

**Legacy plan ID mapping (optional, prefer Stripe as source of truth):**

- `STRIPE_BASIC_PLAN`: Stripe price ID for basic plan
- `STRIPE_PRO_PLAN`: Stripe price ID for pro plan
- `STRIPE_ENTERPRISE_PLAN`: Stripe price ID for enterprise plan

**Optional overrides:**

- `DEBUG`: Set to "False" for production (defaults to "True")
- `ALLOWED_HOSTS`: Comma-separated list of allowed hostnames
- `DB_NAME`, `DB_USER`, `DB_HOST`, `DB_PORT`: Database connection parameters
- `REDIS_URL`: Redis connection URL

### Per-Tenant Configuration

Customer webhook integrations (Shopify, Chargify, Stripe) are configured per-tenant through the web interface. Each organization manages their own:

- Webhook secrets
- API credentials
- Slack integration settings

### Webhook Endpoints

**Customer Webhooks** (per-organization):

- `POST /webhooks/customer/{org_uuid}/shopify/` - Shopify order and customer events
- `POST /webhooks/customer/{org_uuid}/chargify/` - Chargify/Maxio subscription events
- `POST /webhooks/customer/{org_uuid}/stripe/` - Stripe payment events

**Global Webhooks** (Notipus billing):

- `POST /webhooks/billing/stripe/` - Notipus subscription billing events

### Supported Events

**Shopify**:

- `orders/paid` - New order payments
- `customers/create`, `customers/update` - Customer lifecycle events

**Chargify/Maxio**:

- `payment_success`, `payment_failure` - Payment outcomes
- `subscription_created`, `subscription_updated` - Subscription lifecycle
- `renewal_success`, `renewal_failure` - Renewal events

**Stripe**:

- `customer.subscription.created/updated/deleted` - Subscription lifecycle
- `customer.subscription.trial_will_end` - Trial ending notification (3 days before)
- `invoice.payment_succeeded/failed` - Invoice payment outcomes
- `invoice.paid` - Invoice paid confirmation
- `invoice.payment_action_required` - Payment requires customer action (3DS)
- `checkout.session.completed` - Checkout completion

### Security Features

- **HMAC Signature Validation**: All webhooks require valid signatures
- **Timestamp Validation**: Prevents replay attacks (Chargify)
- **Production-Only Enforcement**: Webhook validation cannot be bypassed in production
- **Request Timeouts**: All external API calls have configured timeouts
