"""Разбор пользовательского ввода.

Каждая функция либо возвращает нормализованное значение,
либо кидает ValueError с текстом, который можно показать пользователю.
"""

from __future__ import annotations

import re
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from zoneinfo import ZoneInfo

MAX_PRICE = Decimal("100000")
URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)

# (формат, есть ли в нём время)
DATE_FORMATS = (
    ("%d.%m.%Y %H:%M", True),
    ("%d.%m.%Y", False),
    ("%Y-%m-%d %H:%M", True),
    ("%Y-%m-%d", False),
)

# `30.08` или `30.08 18:00` — год не указан.
SHORT_DATE_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})(\s+\d{1,2}:\d{2})?$")


def parse_price(raw: str) -> Decimal:
    """`2,80` / `2.80` / `€2.80` -> Decimal('2.80')."""
    cleaned = raw.strip().replace(",", ".")
    if cleaned.startswith("-"):
        raise ValueError("Цена должна быть больше нуля.")
    cleaned = re.sub(r"[^\d.]", "", cleaned)
    if not cleaned:
        raise ValueError("Не вижу числа. Пример: 2,80")
    try:
        value = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError("Не понимаю цену. Пример: 2,80") from exc
    if value <= 0:
        raise ValueError("Цена должна быть больше нуля.")
    if value > MAX_PRICE:
        raise ValueError("Слишком большая цена для совместной покупки.")
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def parse_quantity(raw: str, minimum: int = 1, maximum: int = 100) -> int:
    """Целое количество штук в разумных пределах."""
    cleaned = raw.strip().replace(" ", "")
    if not cleaned.isdigit():
        raise ValueError("Введите целое число, например: 2")
    value = int(cleaned)
    if value < minimum:
        raise ValueError(f"Минимальное количество: {minimum}")
    if value > maximum:
        raise ValueError(f"Максимальное количество: {maximum}")
    return value


def parse_url(raw: str) -> str:
    """Ссылка на товар. Пустое значение отсеивается на уровне хендлера."""
    value = raw.strip()
    if " " in value:
        value = value.split()[0]
    if not URL_RE.match(value):
        raise ValueError("Нужна ссылка, начинающаяся с http:// или https://")
    if len(value) > 1000:
        raise ValueError("Ссылка слишком длинная.")
    return value


def parse_deadline(
    raw: str,
    tz: ZoneInfo,
    now: datetime,
    max_days: int = 365,
) -> datetime:
    """Разбирает дату сбора в местном времени и возвращает UTC-aware datetime.

    Поддерживает `30.08.2026`, `30.08.2026 18:00`, `30.08`, `30.08 18:00`.
    Без времени сбор идёт до конца дня.
    """
    value = raw.strip()
    local_now = now.astimezone(tz)

    # Год явно подставляем сами: strptime без года объявлен устаревшим.
    short = SHORT_DATE_RE.match(value)
    if short:
        day, month, clock = short.groups()
        value = f"{day}.{month}.{local_now.year}{clock or ''}"

    parsed: datetime | None = None
    has_time = False
    for fmt, fmt_has_time in DATE_FORMATS:
        try:
            parsed = datetime.strptime(value, fmt)
        except ValueError:
            continue
        has_time = fmt_has_time
        break

    if parsed is None:
        raise ValueError("Не понимаю дату. Формат: 30.08.2026 или 30.08.2026 18:00")

    if not has_time:
        parsed = datetime.combine(parsed.date(), time(23, 59))

    local = parsed.replace(tzinfo=tz)

    # Дата без года, оказавшаяся в прошлом, скорее всего относится к следующему.
    if short and local <= local_now:
        local = local.replace(year=local.year + 1)

    if local <= local_now:
        raise ValueError("Дата должна быть в будущем.")
    if local > local_now + timedelta(days=max_days):
        raise ValueError(f"Слишком далёкая дата. Максимум {max_days} дней.")

    return local.astimezone(timezone.utc)


def clean_text(raw: str, max_length: int, field_name: str = "Значение") -> str:
    """Нормализует однострочные текстовые поля."""
    value = " ".join(raw.split())
    if not value:
        raise ValueError(f"{field_name} не может быть пустым.")
    if len(value) > max_length:
        raise ValueError(f"Слишком длинно. Максимум {max_length} символов.")
    return value


def clean_multiline(raw: str, max_length: int) -> str:
    """То же, но с сохранением переносов строк (для комментариев)."""
    lines = [" ".join(line.split()) for line in raw.strip().splitlines()]
    value = "\n".join(line for line in lines if line)
    if len(value) > max_length:
        raise ValueError(f"Слишком длинно. Максимум {max_length} символов.")
    return value
