# syntax=docker/dockerfile:1
# Use the official Python image
FROM python:3.13-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Copy uv binary from official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy bun binary from official image
COPY --from=oven/bun:latest /usr/local/bin/bun /usr/local/bin/

# Set the working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y libpq-dev gcc redis-tools postgresql-client && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY pyproject.toml uv.lock /app/

# Install project dependencies (without dev dependencies)
RUN UV_HTTP_TIMEOUT=120 uv sync --frozen --no-dev

# Copy frontend dependency files and install
COPY package.json bun.lock /app/
RUN bun install --frozen-lockfile

# Copy frontend source files
COPY src/ /app/src/
COPY postcss.config.js /app/

# Copy application code
COPY ./app/ .

# Build frontend assets
RUN mkdir -p static/dist static/webfonts && \
    cp -r /app/node_modules/@fortawesome/fontawesome-free/webfonts/* static/webfonts/ && \
    bun x tailwindcss -i /app/src/css/main.css -o static/dist/main.css --minify

# Collect static files
RUN uv run --no-dev python manage.py collectstatic --noinput

# Port that the application will use
EXPOSE 8000

# Command to start the server
CMD ["uv", "run", "--no-dev", "gunicorn", "--bind", "0.0.0.0:8000", "django_notipus.wsgi:application"]
