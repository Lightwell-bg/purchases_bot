"""Форматирование значений для Telegram HTML."""

from __future__ import annotations

import html
import re
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

# Лимиты Telegram Bot API.
MAX_MESSAGE_LENGTH = 4096
MAX_CAPTION_LENGTH = 1024

TAG_RE = re.compile(r"<[^>]+>")

CURRENCY_SYMBOLS = {
    "EUR": "€",
    "USD": "$",
    "BGN": "лв.",
    "PLN": "zł",
    "RON": "lei",
}


def esc(value: object) -> str:
    """Экранирует пользовательский текст перед вставкой в HTML-сообщение."""
    if value is None:
        return ""
    return html.escape(str(value), quote=False)


def currency_symbol(currency: str) -> str:
    return CURRENCY_SYMBOLS.get(currency.upper(), currency.upper())


def fmt_amount(value: Decimal) -> str:
    """`2.8` -> `2,80` — привычный для пользователя вид."""
    return f"{Decimal(value):.2f}".replace(".", ",")


def fmt_money(value: Decimal, currency: str = "EUR") -> str:
    symbol = currency_symbol(currency)
    amount = fmt_amount(value)
    # Символы валют пишем перед суммой, буквенные коды — после.
    if symbol in {"€", "$", "zł"}:
        return f"{symbol}{amount}"
    return f"{amount} {symbol}"


def fmt_datetime(value: datetime, tz: ZoneInfo, with_time: bool = True) -> str:
    local = value.astimezone(tz)
    return local.strftime("%d.%m.%Y %H:%M" if with_time else "%d.%m.%Y")


def truncate(value: str | None, limit: int) -> str:
    """Обрезает длинное пользовательское поле, чтобы влезть в лимиты Telegram."""
    if not value:
        return ""
    value = value.strip()
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def visible_length(text: str) -> int:
    """Длина сообщения так, как её считает Telegram.

    Разметка и адреса ссылок в лимит не входят: Telegram парсит HTML и хранит
    их отдельными entity. Без этого одна длинная ссылка на товар съедала бы
    почти весь бюджет объявления.
    """
    return len(html.unescape(TAG_RE.sub("", text)))


def fit_html(text: str, limit: int) -> str:
    """Страховка от превышения лимита длины сообщения.

    Режем по границе строки, чтобы не разорвать HTML-тег: все теги в наших
    сообщениях закрываются внутри одной строки.
    """
    if visible_length(text) <= limit:
        return text
    lines = text.split("\n")
    result: list[str] = []
    total = 0
    for line in lines:
        line_length = visible_length(line) + 1
        if total + line_length > limit - 2:
            break
        result.append(line)
        total += line_length
    return "\n".join(result).rstrip() + "\n…"


def link(url: str | None, label: str) -> str:
    """Ссылка, безопасная для HTML. Без url возвращает пустую строку."""
    if not url:
        return ""
    return f'<a href="{html.escape(url, quote=True)}">{esc(label)}</a>'


def group_message_link(chat_id: int | None, message_id: int | None) -> str | None:
    """Ссылка на сообщение в супергруппе (t.me/c/...). Для обычных групп её нет."""
    if not chat_id or not message_id:
        return None
    raw = str(chat_id)
    if not raw.startswith("-100"):
        return None
    return f"https://t.me/c/{raw[4:]}/{message_id}"


def plural_ru(number: int, one: str, few: str, many: str) -> str:
    """Русское склонение: 1 участник / 2 участника / 5 участников."""
    n = abs(number) % 100
    if 11 <= n <= 14:
        return many
    n %= 10
    if n == 1:
        return one
    if 2 <= n <= 4:
        return few
    return many
