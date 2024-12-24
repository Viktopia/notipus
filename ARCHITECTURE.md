# Shopify to Slack Architecture

## Overview
This application serves as a webhook integration service that processes webhooks from various providers (Shopify, Chargify) and forwards notifications to Slack. The system is designed to be extensible, type-safe, and maintainable.

## Development Environment

### 1. Dependency Management
- **Poetry** for Python package management
  - Ensures reproducible builds
  - Manages virtual environments
  - Handles dependency resolution
  - Version constraints in `pyproject.toml`
  - Lock file (`poetry.lock`) for deterministic installs

#### Important Rules
- **NEVER** edit `poetry.lock` manually
- **ALWAYS** use Poetry commands to add/remove dependencies
- **ALWAYS** commit both `pyproject.toml` and `poetry.lock`
- Use `poetry add package@version` for exact versions
- Use `poetry update package` to update specific packages
- Run `poetry install` after pulling changes with lock file updates

#### Version Constraints
- Use `^` for regular dependencies (e.g., `^1.2.3`)
- Use `==` for critical dependencies that need exact versions
- Avoid `*` or `latest` version constraints

### 2. Code Quality Tools
- **Ruff** for linting and code formatting
  - Configured in `pyproject.toml`
  - Enforces PEP 8 style guide
  - Checks import ordering
  - Identifies code complexity issues
  - Fast and comprehensive Python linter

- **MyPy** for static type checking
  - Strict type checking enabled
  - Type stubs for third-party packages
  - Custom type definitions in `py.typed`

- **Pytest** for testing
  - Fixtures in `conftest.py`
  - Coverage reporting
  - Parameterized tests
  - Mock objects for external services

### 3. Git Hooks
- Pre-commit hooks for:
  - Code formatting
  - Type checking
  - Linting
  - Test running
  - Commit message formatting

### 4. VS Code Configuration
- Recommended extensions
- Workspace settings
- Debug configurations
- Task definitions

## Core Components

### 1. Notification Model
The `Notification` class is the central model for formatting messages to be sent to Slack.

#### Design Decisions
- **Color-Status Relationship**
  - Color is the primary field, settable through constructor
  - Status is derived from color initially
  - Status changes update both status and color
  - Invalid status values default to "info"
  - Predefined color-status mappings in `STATUS_COLORS`

```python
STATUS_COLORS = {
    "success": "#28a745",
    "failed": "#dc3545",
    "warning": "#ffc107",
    "info": "#17a2b8"
}
```

#### Data Flow
1. Constructor sets initial color
2. Post-init derives initial status from color
3. Status changes trigger both status and color updates
4. Color changes trigger status updates

### 2. Webhook Providers
Base webhook provider interface with specific implementations for each service.

#### Provider Interface
- `validate_webhook(request)`: Validates webhook authenticity
- `parse_webhook(request)`: Parses webhook data into notification format
- `get_notification(data)`: Converts parsed data to Notification object

#### Implementation Requirements
- Must handle test webhooks appropriately
- Must validate webhook signatures/HMAC
- Must handle provider-specific event types
- Must raise appropriate errors for invalid data

### 3. Error Handling
Standardized error handling throughout the application.

#### Error Types
- `InvalidWebhookError`: For webhook validation failures
- `InvalidDataError`: For data parsing/format issues
- `UnsupportedEventError`: For unsupported webhook events

#### Error Responses
All errors should return JSON responses with:
- HTTP status code
- Error message
- Error type (if applicable)

### 4. Testing Requirements
Each component must have comprehensive tests covering:
- Happy path scenarios
- Error cases
- Edge cases
- Invalid input handling

## Project Structure
```
shopify-to-slack/
├── app/
│   ├── models/
│   │   ├── __init__.py
│   │   └── notification.py
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── shopify.py
│   │   └── chargify.py
│   ├── __init__.py
│   ├── event_processor.py
│   ├── routes.py
│   └── slack_client.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_webhooks.py
│   ├── test_event_processing.py
│   └── test_message_formatting.py
├── .env.example
├── .gitignore
├── ARCHITECTURE.md
├── README.md
├── poetry.lock
└── pyproject.toml
```

## Best Practices

### 1. Type Safety
- Use type hints consistently
- Use dataclasses for structured data
- Define clear interfaces
- Validate data at boundaries

### 2. Error Handling
- Use custom exceptions for different error cases
- Provide meaningful error messages
- Handle all edge cases explicitly
- Return standardized error responses

### 3. Code Organization
- Keep provider-specific logic in provider classes
- Use dependency injection where appropriate
- Keep business logic separate from HTTP handling
- Use clear naming conventions

### 4. Code Style
- Follow PEP 8 guidelines
- Use consistent import ordering
- Maximum line length of 100 characters
- Docstrings for all public functions and classes
- Type hints for all function arguments and returns

## Extension Guidelines

### Adding New Providers
1. Create new provider class implementing base interface
2. Define provider-specific event types
3. Implement webhook validation
4. Implement data parsing
5. Add comprehensive tests

### Modifying Notification Format
1. Update Notification class
2. Maintain backward compatibility
3. Update all affected tests
4. Document changes in changelog

## Configuration
- Store sensitive data in environment variables
- Use configuration files for non-sensitive settings
- Document all configuration options
- Provide example configurations

## Development Workflow
1. Create feature branch from main
2. Write tests first (TDD approach)
3. Implement feature
4. Run linting and type checking
5. Run test suite
6. Create pull request
7. Code review
8. Merge to main

## Deployment
- Use environment variables for configuration
- Handle CORS appropriately
- Set up proper logging
- Monitor webhook processing
- CI/CD pipeline with:
  - Automated tests
  - Linting checks
  - Type checking
  - Security scanning
  - Deployment automation

## Security Considerations
- Validate all webhooks
- Sanitize all input data
- Use HTTPS only
- Rate limit webhook endpoints
- Log security-relevant events
- Regular dependency updates
- Security scanning in CI/CD

## Documentation
- Keep ARCHITECTURE.md up to date
- Maintain comprehensive README
- Document all environment variables
- Include example configurations
- API documentation
- Deployment guides
