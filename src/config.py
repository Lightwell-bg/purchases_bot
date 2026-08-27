"""Конфигурация приложения.

Секреты и окружение читаются из `.env` (pydantic-settings),
бизнес-параметры расчётов — из ini-файла (по умолчанию `settings.ini`).
"""

from __future__ import annotations

import configparser
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class BusinessSettings:
    """Параметры закупки из ini-файла."""

    def __init__(
        self,
        customs_flat_fee_eur: Decimal,
        purchase_limit_eur: Decimal,
        max_items_per_participant: int,
        max_deadline_days: int,
    ) -> None:
        self.customs_flat_fee_eur = customs_flat_fee_eur
        self.purchase_limit_eur = purchase_limit_eur
        self.max_items_per_participant = max_items_per_participant
        self.max_deadline_days = max_deadline_days

    @classmethod
    def from_file(cls, path: Path) -> "BusinessSettings":
        parser = configparser.ConfigParser()
        if not path.exists():
            raise FileNotFoundError(
                f"Не найден файл бизнес-настроек: {path}. "
                "Скопируйте settings.ini из репозитория."
            )
        parser.read(path, encoding="utf-8")
        business = parser["business"]
        limits = parser["limits"] if parser.has_section("limits") else {}
        return cls(
            customs_flat_fee_eur=Decimal(business["customs_flat_fee_eur"].strip()),
            purchase_limit_eur=Decimal(business["purchase_limit_eur"].strip()),
            max_items_per_participant=int(limits.get("max_items_per_participant", 100)),
            max_deadline_days=int(limits.get("max_deadline_days", 365)),
        )


class Settings(BaseSettings):
    """Переменные окружения."""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    bot_token: str = Field(min_length=10)
    bot_username: str = ""
    main_group_id: int = 0
    # NoDecode: список приходит как "1,2,3", а не JSON — разбираем валидатором ниже.
    admin_telegram_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)

    database_url: str = "sqlite+aiosqlite:///./data/bot.db"
    run_migrations_on_start: bool = True

    rules_version: str = "1.0"

    business_settings_file: str = "settings.ini"
    timezone: str = "Europe/Sofia"

    deadline_check_interval_seconds: int = 300

    log_level: str = "INFO"
    log_file: str = "logs/bot.log"

    @field_validator("admin_telegram_ids", mode="before")
    @classmethod
    def _parse_admin_ids(cls, value: object) -> object:
        """Разрешаем формат `1,2,3` в .env."""
        if isinstance(value, str):
            return [int(part) for part in value.replace(";", ",").split(",") if part.strip()]
        return value

    @field_validator("main_group_id", "deadline_check_interval_seconds", mode="before")
    @classmethod
    def _empty_to_default(cls, value: object) -> object:
        """Пустая строка в .env — это «не задано», а не ошибка."""
        if isinstance(value, str) and not value.strip():
            return 0
        return value

    @field_validator("bot_username", mode="before")
    @classmethod
    def _strip_at(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lstrip("@")
        return value

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def business(self) -> BusinessSettings:
        path = Path(self.business_settings_file)
        if not path.is_absolute():
            path = BASE_DIR / path
        return _load_business(str(path))

    def is_admin(self, telegram_id: int) -> bool:
        return telegram_id in self.admin_telegram_ids

    def deep_link(self, payload: str) -> str:
        return f"https://t.me/{self.bot_username}?start={payload}"


@lru_cache(maxsize=4)
def _load_business(path: str) -> BusinessSettings:
    return BusinessSettings.from_file(Path(path))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
