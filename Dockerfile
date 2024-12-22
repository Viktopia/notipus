# syntax=docker/dockerfile:1

FROM python:3.9-slim

LABEL fly_launch_runtime="flask"

# Install Poetry
ENV POETRY_HOME="/opt/poetry" \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false

RUN pip install poetry

WORKDIR /code

# Copy only dependencies first to leverage Docker cache
COPY pyproject.toml poetry.lock ./
RUN poetry install --no-dev --no-root

# Copy the rest of the application
COPY . .

EXPOSE 8080

CMD ["poetry", "run", "flask", "run", "--host=0.0.0.0", "--port=8080"]
