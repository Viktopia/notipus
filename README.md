## Installation

### Using Docker (Recommended)

1. Clone the repository:
```bash
git clone git@github.com:ThNikGhost/notipus2.git
cd notipus2
```

2. Build the Docker image:
```bash
docker-compose build
```

3. Create .env file. Template:
```
SLACK_WEBHOOK_URL=https://hooks.slack.com/test
CHARGIFY_WEBHOOK_SECRET=test_secret
SHOPIFY_WEBHOOK_SECRET=test_secret
SHOPIFY_SHOP_URL=test.myshopify.com
SHOPIFY_ACCESS_TOKEN=test_token
```

3. Run the container with your environment variables:
```bash
docker-compose up -d
```
