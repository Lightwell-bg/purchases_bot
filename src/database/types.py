"""Кастомные типы SQLAlchemy.

SQLite не умеет хранить Decimal и timezone-aware datetime нативно,
поэтому оборачиваем их в TypeDecorator, чтобы не терять точность денег
и не путаться с часовыми поясами.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, String, TypeDecorator


class Money(TypeDecorator):
    """Decimal, хранимый строкой — без промежуточного float."""

    impl = String(32)
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> str | None:
        if value is None:
            return None
        return str(Decimal(value))

    def process_result_value(self, value: Any, dialect: Any) -> Decimal | None:
        if value is None:
            return None
        return Decimal(value)


class TZDateTime(TypeDecorator):
    """Datetime, всегда aware. В базе лежит naive UTC."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value: Any, dialect: Any) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc)
