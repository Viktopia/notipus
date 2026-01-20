# syntax=docker/dockerfile:1
# Use the official Python image
FROM python:3.13-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Copy uv binary from official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set the working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y libpq-dev gcc redis-tools postgresql-client && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY pyproject.toml uv.lock /app/

# Install project dependencies (without dev dependencies)
RUN uv sync --frozen --no-dev --no-install-project

# Copy application code
COPY ./app/ .

# Collect static files (if used)
RUN uv run python manage.py collectstatic --noinput

# Port that the application will use
EXPOSE 8000

# Command to start the server
CMD ["uv", "run", "gunicorn", "--bind", "0.0.0.0:8000", "django_notipus.wsgi:application"]
