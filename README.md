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

3. Create the .env File
Create a .env file in the root directory to store environment variables. Below is a template for reference:
```
SLACK_WEBHOOK_URL=https://hooks.slack.com/test
CHARGIFY_WEBHOOK_SECRET=test_secret
SHOPIFY_WEBHOOK_SECRET=test_secret
SHOPIFY_SHOP_URL=test.myshopify.com
SHOPIFY_ACCESS_TOKEN=test_token
```
Note: Replace the placeholder values (test_secret, test_token, etc.) with the actual credentials and secrets for your environment.

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

2. Set up Poetry for dependency management:
```bash
poetry install
```

3. Create the .env File
Create a .env file in the root directory to store environment variables. Below is a template for reference:
```
SLACK_WEBHOOK_URL=https://hooks.slack.com/test
CHARGIFY_WEBHOOK_SECRET=test_secret
SHOPIFY_WEBHOOK_SECRET=test_secret
SHOPIFY_SHOP_URL=test.myshopify.com
SHOPIFY_ACCESS_TOKEN=test_token
```

## Development

1. Install development dependencies:
```bash
poetry install --with dev
```

2. Run tests:
```bash
poetry run pytest
```

3. Format code:
```bash
poetry run black .
poetry run isort .
```

4. Run linting:
```bash
poetry run ruff check .
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

The application requires the following environment variables:

- `SLACK_WEBHOOK_URL`: The Slack webhook URL used to send notifications.
- `CHARGIFY_WEBHOOK_SECRET`: (Optional) The webhook secret from your Chargify settings.
- `SHOPIFY_WEBHOOK_SECRET`: The webhook secret from your Shopify app settings.
- `SHOPIFY_SHOP_URL`: The URL of your Shopify store (e.g., yourstore.myshopify.com).
- `SHOPIFY_ACCESS_TOKEN`: The access token to authenticate API requests to your Shopify store.
