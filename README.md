# Notipus - Webhook to Slack Notifier

A webhook-driven notification service that sends enriched payment and subscription events from Shopify and Chargify to Slack. The service provides meaningful, actionable insights for customer success teams with a fun and engaging tone.

## Features

- 🎯 **Smart Event Processing**: Automatically categorizes and prioritizes events based on type and customer value
- 💡 **Rich Context**: Enriches notifications with customer history, metrics, and actionable insights
- 🎨 **Engaging Messages**: Uses whimsical language and emojis to make notifications fun and memorable
- 📊 **Business Metrics**: Includes relevant business metrics like lifetime value and payment history
- 🔄 **Event Analysis**: Analyzes events to provide actionable recommendations
- ⚡ **Multiple Payment Providers**: Supports both Shopify and Chargify webhooks

## Installation

### Using Docker (Recommended)

1. Clone the Repository
Clone the repository to your local machine and navigate into the project directory:
```
git clone git@github.com:viktopia/notipus.git
cd notipus
```

2. Build the Docker Image
Build the necessary Docker containers for the project:
```
docker-compose build
```

3. Set Environment Variables
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
Note: Webhook secrets for customer integrations are now managed per-tenant through the web interface.

4. Run the Containers
Start the Docker containers with the specified environment variables:
```
docker-compose up -d
```
The -d flag runs the containers in detached mode.

5. Verify the Setup
Ensure that the services are running correctly by checking the Docker container logs:
```
docker-compose logs -f
```
Access the application based on the configured settings (e.g., http://localhost:8000).

6. Stopping the Containers
To stop the running containers, use:
```
docker-compose down
```
Feel free to extend this setup guide with additional steps or troubleshooting tips specific to your project.

### Local Development

1. Clone the repository:
```bash
git clone git@github.com:Viktopia/notipus.git
cd notipus
```

2. Install [uv](https://docs.astral.sh/uv/) for dependency management:
```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or with Homebrew
brew install uv
```

3. Install dependencies:
```bash
uv sync
```

4. Set Environment Variables
```bash
export SECRET_DJANGO_KEY=your-secure-secret-key-here
export DEBUG=True
# Add other required environment variables as needed
```
Webhook secrets for customer integrations are managed per-tenant through the application interface.

## Development

1. Install all dependencies (including dev):
```bash
uv sync --all-groups
```

2. Run tests:
```bash
uv run pytest
```

3. Format code:
```bash
uv run ruff format .
```

4. Run linting:
```bash
uv run ruff check .
```
## Architecture
The service is built with a modular architecture that separates concerns and makes it easy to extend:

```bash
app/
├── webhooks/
│   ├── providers/      # Payment gateway integrations
│   │   ├── base.py     ♻️ AbstractProvider
│   │   ├── chargify.py ⚡ ChargifyWebhookProcessor
│   │   └── shopify.py  🛒 ShopifyWebhookProcessor
│   ├── models/
│   │   └── notification.py # 🗄️ Notification model
│   ├── event_processor.py  # ⚙️ Event handling
│   └── message_generator.py # 📨 Content builder
```

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Commit your changes: `git commit -m 'Add amazing feature'`
4. Push to the branch: `git push origin feature/amazing-feature`
5. Open a pull request

## Configuration

### Core Environment Variables

The application requires the following environment variables:

**Required for production:**
- `SECRET_DJANGO_KEY`: Django secret key for cryptographic operations
- `DB_PASSWORD`: Database password for PostgreSQL

**Notipus billing (subscription revenue):**
- `NOTIPUS_STRIPE_SECRET_KEY`: Stripe secret key for processing subscriptions
- `NOTIPUS_STRIPE_WEBHOOK_SECRET`: Webhook secret for Stripe billing events

**Optional overrides:**
- `DEBUG`: Set to "False" for production (defaults to "True")
- `ALLOWED_HOSTS`: Comma-separated list of allowed hostnames
- `DB_NAME`, `DB_USER`, `DB_HOST`: Database connection parameters

### Per-Tenant Configuration

Customer webhook integrations (Shopify, Chargify, Stripe) are configured per-tenant through the web interface. Each organization manages their own:
- Webhook secrets
- API credentials
- Slack integration settings
