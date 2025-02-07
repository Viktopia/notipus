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
git clone git@github.com:ThNikGhost/notipus.git
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
