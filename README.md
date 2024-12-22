# Shopify & Chargify to Slack Notifier

A webhook-driven notification service that sends enriched payment and subscription events from Shopify and Chargify to Slack. The service provides meaningful, actionable insights for customer success teams with a fun and engaging tone.

## Features

- 🎯 **Smart Event Processing**: Automatically categorizes and prioritizes events based on type and customer value
- 💡 **Rich Context**: Enriches notifications with customer history, metrics, and actionable insights
- 🎨 **Engaging Messages**: Uses whimsical language and emojis to make notifications fun and memorable
- 📊 **Business Metrics**: Includes relevant business metrics like lifetime value and payment history
- 🔄 **Event Correlation**: Groups related events to tell a complete customer story
- ⚡ **Multiple Payment Providers**: Supports both Shopify and Chargify, with an extensible architecture for more providers

## Installation

### Using Docker (Recommended)

1. Clone the repository:
```bash
git clone git@github.com:Viktopia/shopify-to-slack.git
cd shopify-to-slack
```

2. Build the Docker image:
```bash
docker build -t shopify-to-slack .
```

3. Run the container with your environment variables:
```bash
docker run -d \
  -p 8080:8080 \
  -e SLACK_WEBHOOK_URL=your_slack_webhook_url \
  -e CHARGIFY_API_KEY=your_chargify_api_key \
  -e CHARGIFY_DOMAIN=your_chargify_domain \
  -e CHARGIFY_WEBHOOK_SECRET=your_chargify_webhook_secret \
  -e SHOPIFY_SHOP_URL=your_shop_url \
  -e SHOPIFY_ACCESS_TOKEN=your_access_token \
  -e SHOPIFY_WEBHOOK_SECRET=your_webhook_secret \
  shopify-to-slack
```

### Local Development

1. Clone the repository:
```bash
git clone git@github.com:Viktopia/shopify-to-slack.git
cd shopify-to-slack
```

2. Set up Poetry for dependency management:
```bash
poetry install
```

3. Set required environment variables:
```bash
export SLACK_WEBHOOK_URL=your_slack_webhook_url
export CHARGIFY_API_KEY=your_chargify_api_key
export CHARGIFY_DOMAIN=your_chargify_domain
export CHARGIFY_WEBHOOK_SECRET=your_chargify_webhook_secret
export SHOPIFY_SHOP_URL=your_shop_url
export SHOPIFY_ACCESS_TOKEN=your_access_token
export SHOPIFY_WEBHOOK_SECRET=your_webhook_secret
```

## Usage

1. Start the server:

Using Docker:
```bash
docker run -d -p 8080:8080 shopify-to-slack
```

Local development:
```bash
poetry run python -m app.main
```

2. Configure webhooks in Shopify and Chargify to point to your endpoints:
- Shopify: `https://your-domain/webhooks/shopify`
- Chargify: `https://your-domain/webhooks/chargify`

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

- `app/providers/`: Payment provider implementations (Shopify, Chargify)
- `app/enrichment.py`: Notification enrichment with context and insights
- `app/messages.py`: Message generation with whimsical templates
- `app/models.py`: Common data models and enums
- `app/main.py`: Flask application and webhook handlers

## Docker Deployment

The service is containerized using Docker for easy deployment. The Dockerfile:
- Uses Python 3.9 slim base image
- Installs Poetry for dependency management
- Copies only necessary files
- Sets up a non-root user for security
- Exposes port 8080
- Uses multi-stage build for smaller image size

Environment variables are passed to the container at runtime, making it easy to deploy in different environments without modifying the code.

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Commit your changes: `git commit -m 'Add amazing feature'`
4. Push to the branch: `git push origin feature/amazing-feature`
5. Open a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.
