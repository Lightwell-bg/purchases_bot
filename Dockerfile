FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Europe/Sofia

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini settings.ini ./
COPY migrations ./migrations
COPY src ./src

RUN mkdir -p /app/data /app/logs

# Миграции прогоняются самим приложением при старте (RUN_MIGRATIONS_ON_START).
CMD ["python", "-m", "src.main"]
