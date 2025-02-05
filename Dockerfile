# Используем официальный образ Python
FROM python:3.13-slim

# Устанавливаем переменные окружения
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем зависимости
COPY pyproject.toml poetry.lock /app/

# Устанавливаем Poetry
RUN pip install --upgrade pip && \
    pip install poetry && \
    poetry config virtualenvs.create false

RUN apt-get update && apt-get install -y libpq-dev gcc && rm -rf /var/lib/apt/lists/*

# Устанавливаем зависимости проекта
RUN poetry install --no-root --no-interaction --no-ansi

# Копируем исходный код проекта
COPY . /app/

RUN apt update && apt install -y postgresql-client
# Собираем статические файлы (если используется)
RUN python manage.py collectstatic --noinput

# Порт, который будет использовать приложение
EXPOSE 8000

# Команда для запуска сервера
# CMD ["gunicorn", "--bind", "0.0.0.0:8000", "django_notipus.wsgi:application"]
CMD ["poetry", "run", "python", "manage.py", "runserver"]



# poetry run python manage.py runserver