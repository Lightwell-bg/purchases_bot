"""Общие фикстуры тестов.

Переменные окружения задаём до импорта конфига, чтобы тесты не зависели
от локального `.env` разработчика.
"""

from __future__ import annotations

import os

os.environ.setdefault("BOT_TOKEN", "123456:test-token-not-a-real-secret")
os.environ.setdefault("BOT_USERNAME", "test_bot")
os.environ.setdefault("MAIN_GROUP_ID", "-1001234567890")
os.environ.setdefault("ADMIN_TELEGRAM_IDS", "1,2")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./data/test.db")
os.environ.setdefault("RULES_VERSION", "1.0")
os.environ.setdefault("TIMEZONE", "Europe/Sofia")

import pytest  # noqa: E402

from src.config import get_settings  # noqa: E402


@pytest.fixture(scope="session")
def settings():
    return get_settings()


@pytest.fixture(scope="session")
def business(settings):
    return settings.business
