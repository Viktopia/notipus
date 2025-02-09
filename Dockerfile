# syntax=docker/dockerfile:1
# Use the official Python image
FROM python:3.13-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set the working directory
WORKDIR /app

# Copy dependencies
COPY pyproject.toml poetry.lock /app/

# Install Poetry
RUN pip install --upgrade pip && \
    pip install poetry && \
    poetry config virtualenvs.create false

RUN apt-get update && apt-get install -y libpq-dev gcc && rm -rf /var/lib/apt/lists/*

# Install project dependencies
RUN poetry install --no-root --no-interaction --no-ansi

# Copy project source code
COPY ./app/ .

RUN apt update && apt install -y postgresql-client
# Collect static files (if used)
RUN python manage.py collectstatic --noinput

# Port that the application will use
EXPOSE 8000

# Command to start the server
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "django_notipus.wsgi:application"]
# CMD ["poetry", "run", "python", "manage.py", "runserver"]
