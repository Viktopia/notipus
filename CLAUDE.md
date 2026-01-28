# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Notipus is a multi-tenant SaaS webhook notification service that sends enriched payment and subscription events from Shopify, Stripe, and Chargify to Slack. Built with Django 5.x and Python 3.12+.

## Common Commands

### Package Management (uv)
```bash
uv sync --all-groups          # Install all dependencies
uv lock --upgrade && uv sync --all-groups  # Update dependencies
```

### Testing
```bash
uv run pytest                              # Run all tests
uv run pytest tests/test_webhooks.py       # Run specific test file
uv run pytest -k "test_shopify"            # Run tests matching pattern
uv run pytest --cov=app --cov-report=term-missing  # With coverage
```

### Code Quality
```bash
uv run ruff format .           # Format code
uv run ruff check .            # Run linter
uv run ruff check --fix .      # Auto-fix linting issues
uv run mypy app/               # Type checking
```

### Django Migrations (use test settings to avoid needing PostgreSQL)
```bash
# From project root:
PYTHONPATH=app DJANGO_SETTINGS_MODULE=django_notipus.test_settings uv run python app/manage.py makemigrations core --name your_migration_name

# Show migration status:
PYTHONPATH=app DJANGO_SETTINGS_MODULE=django_notipus.test_settings uv run python app/manage.py showmigrations
```

### Django Server
```bash
uv run python app/manage.py runserver      # Start dev server
uv run python app/manage.py migrate        # Apply migrations
```

### Frontend Assets (Tailwind CSS)
```bash
bun run build        # Build CSS and copy fonts
bun run dev          # Watch mode for CSS
```

## Architecture

### Directory Structure
- `app/` - Django application root (PYTHONPATH includes this)
  - `core/` - Core app: users, workspaces, billing, integrations
  - `webhooks/` - Webhook routing and event processing
  - `plugins/` - Plugin architecture for sources, destinations, enrichment
  - `django_notipus/` - Django project settings

### Plugin System (ADR-001)
Three plugin types with auto-discovery from `app/plugins/`:
- **Sources** (`plugins/sources/`): Webhook receivers - Stripe, Shopify, Chargify
- **Destinations** (`plugins/destinations/`): Notification delivery - Slack
- **Enrichment** (`plugins/enrichment/`): Data enhancement - Brandfetch

### Multi-Tenant Webhooks
- Customer webhooks: `POST /webhook/customer/{org_uuid}/{provider}/`
- Billing webhooks: `POST /webhook/billing/stripe/`

### Key Models (in `core/models.py`)
- `Workspace` - Tenant container
- `Integration` - Per-workspace provider connections
- `Company` - Enriched company data with cached logos
- `WorkspaceMember` - User-workspace relationships
- `Plan`, `Subscription` - Billing

### Services Layer
- `app/core/services/` - Business logic (Stripe, Shopify, enrichment)
- `app/webhooks/services/` - Event processing, notifications, rate limiting

## Code Style

- Use `ruff` for linting and formatting (always run after changes)
- Use modern Python 3.12+ features: type hints, f-strings, dataclasses
- Django templates use `.html.j2` extension
- Tests use pytest exclusively (not unittest)
- Never edit migration files after creation; use test settings to create migrations without PostgreSQL
