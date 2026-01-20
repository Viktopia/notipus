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

The service is built with a modular architecture that separates concerns and makes it easy to extend:

```
app/
├── core/              # Core application (users, organizations, billing)
├── webhooks/
│   ├── providers/     # Payment gateway integrations
│   │   ├── base.py        # AbstractProvider
│   │   ├── chargify.py    # ChargifyWebhookProcessor
│   │   ├── shopify.py     # ShopifyWebhookProcessor
│   │   └── stripe.py      # StripeWebhookProcessor
│   ├── services/      # Business logic
│   │   ├── event_processor.py
│   │   └── slack_client.py
│   ├── models/
│   │   └── notification.py
│   └── message_generator.py
└── django_notipus/    # Django project settings
```

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

- `NOTIPUS_STRIPE_SECRET_KEY`: Stripe secret key for processing subscriptions
- `NOTIPUS_STRIPE_WEBHOOK_SECRET`: Webhook secret for Stripe billing events

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
