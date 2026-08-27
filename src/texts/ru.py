"""Все пользовательские тексты и сборка сообщений.

Хендлеры не должны собирать HTML сами — только звать функции отсюда.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

from src.database.models import Participant, Purchase, PurchaseStatus
from src.services.calculations import LimitCheck, PurchaseTotals
from src.utils.formatting import (
    MAX_CAPTION_LENGTH,
    MAX_MESSAGE_LENGTH,
    esc,
    fit_html,
    fmt_datetime,
    fmt_money,
    link,
    plural_ru,
    truncate,
)

RULES_FILE = Path(__file__).with_name("rules.md")

DISCLAIMER = (
    "ℹ️ Фактическое количество отправлений и таможенных позиций зависит от продавца, "
    "площадки, перевозчика и таможенного оформления. Все расчёты ориентировочные."
)

STATUS_LABELS: dict[PurchaseStatus, str] = {
    PurchaseStatus.DRAFT: "📝 Черновик",
    PurchaseStatus.OPEN: "🟢 Сбор открыт",
    PurchaseStatus.CLOSED: "🔒 Сбор закрыт",
    PurchaseStatus.ORDERED: "📮 Заказано",
    PurchaseStatus.SHIPPED: "🚚 В пути",
    PurchaseStatus.RECEIVED: "📬 Получено",
    PurchaseStatus.COMPLETED: "✅ Завершено",
    PurchaseStatus.CANCELLED: "❌ Отменена",
}

# Ограничения на длину полей в объявлении, чтобы влезать в лимит caption.
LIMITS = {
    "title": 120,
    "variant": 150,
    "pickup": 80,
    "description": 300,
    "participant_variant": 100,
    "participant_comment": 200,
}


# --------------------------------------------------------------------------- #
# Общие экраны
# --------------------------------------------------------------------------- #

MAIN_MENU = (
    "🛒 <b>Совместные покупки</b>\n\n"
    "Здесь можно собрать участников для общего заказа "
    "или присоединиться к чужой закупке.\n\n"
    "Выберите действие:"
)

GROUP_PINNED = (
    "🛒 <b>Совместные покупки</b>\n\n"
    "Хотите собрать участников для общего заказа?\n\n"
    "Нажмите кнопку ниже — бот проведёт по шагам в личном чате."
)

GROUP_HELP = (
    "🛒 <b>Как работают совместные покупки</b>\n\n"
    "1. Нажмите кнопку ниже — бот откроется в личном чате.\n"
    "2. Ответьте на несколько вопросов о товаре.\n"
    "3. Бот сам опубликует объявление в этой группе.\n"
    "4. Остальные присоединятся по кнопке под объявлением.\n\n"
    "Чтобы присоединиться к чужой закупке — нажмите «🛒 Присоединиться» "
    "под её объявлением в группе."
)

GROUP_WELCOME = (
    "👋 Добро пожаловать!\n\n"
    "В этой группе можно собирать совместные заказы: несколько человек "
    "объединяют покупку одного товара и делят расходы на доставку.\n\n"
    "Своя закупка — по кнопке ниже. Чужие ищите в закреплённом сообщении "
    "и в ленте группы."
)

GROUP_BOT_ADDED = (
    "🛒 Бот совместных покупок подключён.\n\n"
    "Администратору: отправьте <code>/setup</code>, чтобы опубликовать "
    "сообщение для закрепления."
)

GROUP_KEYBOARD_ARMED = (
    "🔘 Кнопка «📋 Активные закупки» теперь всегда под рукой, рядом с полем ввода."
)

GROUP_REDIRECT = (
    "Создание закупки проходит в личном чате с ботом.\n"
    "Нажмите кнопку ниже, чтобы открыть личку."
)

CANCELLED = "❌ Отменено."
UNKNOWN_COMMAND = "Не понимаю команду. Нажмите /start, чтобы открыть меню."
OUTDATED_CALLBACK = "Это сообщение устарело. Откройте /start."
ONLY_PRIVATE = "Это действие доступно только в личном чате с ботом."
NOT_YOUR_PURCHASE = "Это чужая закупка — действие недоступно."
PURCHASE_NOT_FOUND = "Закупка не найдена. Возможно, её отменили."
BAD_DEEP_LINK = "Ссылка не распознана. Нажмите /start, чтобы открыть меню."
GROUP_NOT_CONFIGURED = (
    "⚠️ Группа для публикации не настроена (MAIN_GROUP_ID). "
    "Сообщите администратору сервиса."
)
PUBLISH_FAILED = (
    "⚠️ Не удалось опубликовать объявление в группе. "
    "Проверьте, что бот добавлен в группу и может отправлять сообщения. "
    "Закупка сохранена как черновик — попробуйте опубликовать позже."
)


# --------------------------------------------------------------------------- #
# Правила
# --------------------------------------------------------------------------- #

@lru_cache(maxsize=1)
def rules_full() -> str:
    return RULES_FILE.read_text(encoding="utf-8").strip()


def rules_screen(version: str, joining: bool = False) -> str:
    intro = (
        "Прежде чем присоединиться к закупке, примите правила."
        if joining
        else "Прежде чем создать закупку, примите правила."
    )
    return (
        "📜 <b>Правила совместных покупок</b>\n\n"
        f"{intro}\n\n"
        "Коротко:\n"
        "• одна закупка — один товар;\n"
        "• бот не принимает платежи, расчёты идут напрямую с организатором;\n"
        "• суммы пошлины и стоимости на единицу — ориентировочные;\n"
        "• пока сбор открыт, заявку можно изменить или отозвать;\n"
        "• общая стоимость закупки ограничена лимитом.\n\n"
        f"Версия правил: {esc(version)}"
    )


RULES_ACCEPTED = "✅ Правила приняты."
RULES_REQUIRED = "Чтобы продолжить, нужно принять правила."


# --------------------------------------------------------------------------- #
# Мастер создания закупки
# --------------------------------------------------------------------------- #

WIZARD_INTRO = (
    "Создаём закупку. Отвечайте по шагам — в конце покажу предпросмотр.\n"
    "В любой момент можно нажать «Отмена»."
)

ASK_TITLE = "<b>Шаг 1 из 10.</b> Название товара.\n\nНапример: Baseus USB-C 100W"
ASK_URL = (
    "<b>Шаг 2 из 10.</b> Ссылка на товар.\n\n"
    "Вставьте ссылку целиком (http:// или https://) "
    "или нажмите «Пропустить»."
)
ASK_PHOTO = (
    "<b>Шаг 3 из 10.</b> Фото товара.\n\n"
    "Отправьте фотографию или нажмите «Пропустить»."
)
ASK_PRICE = "<b>Шаг 4 из 10.</b> Цена одной единицы.\n\nНапример: 2,80"
ASK_CURRENCY = "<b>Шаг 5 из 10.</b> Валюта цены."
ASK_VARIANTS = (
    "<b>Шаг 6 из 10.</b> Какие варианты товара допустимы?\n\n"
    "Например: «цвет, размер» или «длина кабеля».\n"
    "Если вариантов нет — нажмите «Пропустить»."
)
ASK_ORGANIZER_QTY = (
    "<b>Шаг 7 из 10.</b> Сколько единиц берёте себе?\n\n"
    "Введите число. Если пока не берёте — 0."
)
ASK_DEADLINE = (
    "<b>Шаг 8 из 10.</b> До какого числа идёт сбор?\n\n"
    "Формат: 30.08.2026 или 30.08.2026 18:00"
)
ASK_PICKUP = "<b>Шаг 9 из 10.</b> Город или место получения.\n\nНапример: Бургас"
ASK_COMMENT = (
    "<b>Шаг 10 из 10.</b> Дополнительный комментарий для участников.\n\n"
    "Или нажмите «Пропустить»."
)

NEED_PHOTO = "Нужна фотография. Отправьте фото или нажмите «Пропустить»."
NEED_TEXT = "Нужен текст. Отправьте сообщение текстом."
EDIT_FIELD_PROMPT = "Что изменить?"


def wizard_price_hint(limit: Decimal, currency: str) -> str:
    return (
        f"Лимит одной закупки: {fmt_money(limit, currency)}. "
        "Заявки сверх лимита бот не примет."
    )


# --------------------------------------------------------------------------- #
# Сборка карточек закупки
# --------------------------------------------------------------------------- #

def _price_line(unit_price: Decimal, currency: str) -> str:
    return f"💶 Цена: {fmt_money(unit_price, currency)} / шт."


def purchase_preview(data: Mapping[str, Any], tz: ZoneInfo) -> str:
    """Предпросмотр перед публикацией. `data` — черновик из FSM."""
    lines = [
        "🛒 <b>Совместная покупка</b>",
        "",
        f"<b>{esc(truncate(data['title'], LIMITS['title']))}</b>",
        "",
        _price_line(data["unit_price"], data["currency"]),
    ]
    if data.get("product_url"):
        lines.append(f"🔗 {link(data['product_url'], 'Ссылка на товар')}")
    lines.append(f"📦 Организатор берёт: {data['organizer_quantity']} шт.")
    if data.get("pickup_location"):
        lines.append(f"📍 Получение: {esc(truncate(data['pickup_location'], LIMITS['pickup']))}")
    lines.append(f"⏰ Сбор до: {fmt_datetime(data['deadline'], tz)}")

    if data.get("variant_description"):
        lines += [
            "",
            "Допустимые варианты:",
            esc(truncate(data["variant_description"], LIMITS["variant"])),
        ]
    if data.get("description"):
        lines += ["", esc(truncate(data["description"], LIMITS["description"]))]
    if not data.get("photo_file_id"):
        lines += ["", "📷 Фото не добавлено."]

    lines += ["", DISCLAIMER]
    return fit_html("\n".join(lines), MAX_CAPTION_LENGTH)


def published(purchase: Purchase, message_link: str | None) -> str:
    lines = [
        f"✅ Объявление опубликовано в группе. Закупка <b>#{purchase.id}</b>.",
        "",
        "Бот будет сам обновлять объявление, когда кто-то присоединится.",
    ]
    if message_link:
        lines += ["", f'<a href="{message_link}">Открыть объявление в группе</a>']
    return "\n".join(lines)


def group_announcement(purchase: Purchase, totals: PurchaseTotals, tz: ZoneInfo) -> str:
    """Публичное объявление в группе. Без Telegram ID участников."""
    currency = purchase.currency
    header = f"🛒 <b>Совместная покупка #{purchase.id}</b>"
    if purchase.status == PurchaseStatus.CLOSED:
        header = f"🔒 <b>СБОР ЗАКРЫТ</b>\n\n{header}"
    elif purchase.status == PurchaseStatus.CANCELLED:
        header = f"❌ <b>ЗАКУПКА ОТМЕНЕНА</b>\n\n{header}"
    elif purchase.status not in (PurchaseStatus.OPEN, PurchaseStatus.DRAFT):
        header = f"{STATUS_LABELS[purchase.status]}\n\n{header}"

    lines = [
        header,
        "",
        f"<b>{esc(truncate(purchase.title, LIMITS['title']))}</b>",
        "",
        f"💶 {fmt_money(purchase.unit_price, currency)} / шт.",
    ]
    if purchase.product_url:
        lines.append(f"🔗 {link(purchase.product_url, 'Ссылка на товар')}")

    lines += [
        "",
        f"📦 Собрано: {totals.total_quantity} шт.",
        f"👥 Участников: {totals.participants_count}",
        "💰 Стоимость товаров: "
        f"{fmt_money(totals.total_value, currency)} / {fmt_money(totals.limit, currency)}",
        "",
        f"🛃 Ориентировочная пошлина: {fmt_money(totals.estimated_customs_fee, currency)}",
        "💶 Ориентировочно на единицу: "
        f"{fmt_money(totals.estimated_fee_per_item, currency)}",
        "",
        f"⏰ Сбор до: {fmt_datetime(purchase.deadline, tz)}",
    ]
    if purchase.pickup_location:
        lines.append(f"📍 Получение: {esc(truncate(purchase.pickup_location, LIMITS['pickup']))}")
    lines.append(f"👤 Организатор: {esc(purchase.organizer.display_name)}")

    if purchase.variant_description:
        lines += [
            "",
            "Допустимые варианты: "
            f"{esc(truncate(purchase.variant_description, LIMITS['variant']))}",
        ]
    if purchase.description:
        lines += ["", esc(truncate(purchase.description, LIMITS["description"]))]

    lines += ["", DISCLAIMER]

    limit = MAX_CAPTION_LENGTH if purchase.photo_file_id else MAX_MESSAGE_LENGTH
    return fit_html("\n".join(lines), limit)


def purchase_short_card(purchase: Purchase, totals: PurchaseTotals, tz: ZoneInfo) -> str:
    """Краткая карточка, которую видит пришедший по ссылке пользователь."""
    lines = [
        f"🛒 <b>Совместная покупка #{purchase.id}</b>",
        "",
        f"<b>{esc(truncate(purchase.title, LIMITS['title']))}</b>",
        "",
        _price_line(purchase.unit_price, purchase.currency),
    ]
    if purchase.product_url:
        lines.append(f"🔗 {link(purchase.product_url, 'Ссылка на товар')}")
    lines += [
        f"📦 Уже собрано: {totals.total_quantity} шт. "
        f"({fmt_money(totals.total_value, purchase.currency)} "
        f"из {fmt_money(totals.limit, purchase.currency)})",
        f"⏰ Сбор до: {fmt_datetime(purchase.deadline, tz)}",
    ]
    if purchase.pickup_location:
        lines.append(f"📍 Получение: {esc(truncate(purchase.pickup_location, LIMITS['pickup']))}")
    lines.append(f"👤 Организатор: {esc(purchase.organizer.display_name)}")
    if purchase.variant_description:
        lines += [
            "",
            "Допустимые варианты: "
            f"{esc(truncate(purchase.variant_description, LIMITS['variant']))}",
        ]
    if purchase.description:
        lines += ["", esc(truncate(purchase.description, LIMITS["description"]))]
    return fit_html("\n".join(lines), MAX_CAPTION_LENGTH)


# --------------------------------------------------------------------------- #
# Присоединение
# --------------------------------------------------------------------------- #

ASK_JOIN_QUANTITY = "Сколько единиц вам нужно?\n\nВведите число, например: 2"
ASK_JOIN_COMMENT = (
    "Комментарий организатору.\n\nНапример: артикул или пожелание. "
    "Или нажмите «Пропустить»."
)


def ask_join_variant(purchase: Purchase) -> str:
    if purchase.variant_description:
        return (
            "Какой вариант товара вам нужен?\n\n"
            f"Организатор просит указать: "
            f"{esc(truncate(purchase.variant_description, LIMITS['variant']))}"
        )
    return "Какой вариант товара вам нужен?\n\nЕсли вариант не важен — нажмите «Пропустить»."


def join_preview(
    purchase: Purchase,
    quantity: int,
    variant: str | None,
    comment: str | None,
) -> str:
    total = purchase.unit_price * quantity
    lines = [
        f"Вы присоединяетесь к закупке <b>#{purchase.id}</b>.",
        "",
        f"{quantity} × {esc(truncate(purchase.title, LIMITS['title']))}",
    ]
    if variant:
        lines.append(f"Вариант: {esc(truncate(variant, LIMITS['participant_variant']))}")
    if comment:
        lines.append(f"Комментарий: {esc(truncate(comment, LIMITS['participant_comment']))}")
    lines += [
        "",
        f"Сумма товара: <b>{fmt_money(total, purchase.currency)}</b>",
        "",
        "Оплата — напрямую организатору, бот деньги не принимает.",
    ]
    return "\n".join(lines)


def participation_card(purchase: Purchase, participant: Participant, tz: ZoneInfo) -> str:
    total = purchase.unit_price * participant.quantity
    lines = [
        f"✅ <b>Ваша заявка в закупке #{purchase.id}</b>",
        "",
        f"<b>{esc(truncate(purchase.title, LIMITS['title']))}</b>",
        "",
        f"Количество: {participant.quantity}",
    ]
    if participant.variant:
        lines.append(
            f"Вариант: {esc(truncate(participant.variant, LIMITS['participant_variant']))}"
        )
    if participant.comment:
        lines.append(
            f"Комментарий: {esc(truncate(participant.comment, LIMITS['participant_comment']))}"
        )
    lines += [
        f"Сумма: <b>{fmt_money(total, purchase.currency)}</b>",
        "",
        f"Статус закупки: {STATUS_LABELS[purchase.status]}",
        f"⏰ Сбор до: {fmt_datetime(purchase.deadline, tz)}",
    ]
    return "\n".join(lines)


JOINED = "✅ Вы присоединились."
PARTICIPATION_UPDATED = "✅ Заявка обновлена."
PARTICIPATION_CANCELLED = "❌ Вы отказались от участия в закупке."
ALREADY_JOINED = "Вы уже участвуете в этой закупке. Заявку можно изменить или отозвать."
ORGANIZER_CANNOT_JOIN = (
    "Вы организатор этой закупки. Своё количество меняйте в панели организатора."
)
LEAVE_CONFIRM = "Отказаться от участия? Заявка будет удалена из закупки."


def limit_exceeded(check: LimitCheck, currency: str) -> str:
    lines = [
        f"⚠️ После добавления закупка превысит лимит {fmt_money(check.limit, currency)}.",
        "",
        f"Сейчас собрано: {fmt_money(check.current_total, currency)}",
        f"Вы хотите добавить: {fmt_money(check.added_value, currency)}",
        f"Итого получилось бы: {fmt_money(check.projected_total, currency)}",
        "",
    ]
    if check.max_quantity > 0:
        lines.append(f"Максимально можно добавить: <b>{check.max_quantity} шт.</b>")
        lines.append("Введите другое количество.")
    else:
        lines.append("Свободного места в этой закупке не осталось.")
    return "\n".join(lines)


def join_unavailable(reason: str) -> str:
    return {
        "CLOSED": "🔒 Сбор по этой закупке уже закрыт.",
        "CANCELLED": "❌ Эта закупка отменена.",
        "EXPIRED": "⏰ Срок сбора истёк — присоединиться нельзя.",
        "NOT_PUBLISHED": "Эта закупка ещё не опубликована.",
    }.get(reason, "Присоединиться к этой закупке нельзя.")


# --------------------------------------------------------------------------- #
# Список активных закупок
# --------------------------------------------------------------------------- #

ACTIVE_PURCHASES_EMPTY = (
    "📋 <b>Активные закупки</b>\n\n"
    "Сейчас открытых закупок нет. Будьте первым — создайте свою!"
)


def active_purchases_page(
    purchases: Sequence[tuple[Purchase, PurchaseTotals]],
    page: int,
    total_pages: int,
    total: int,
    tz: ZoneInfo,
) -> str:
    lines = [f"📋 <b>Активные закупки</b> ({total})"]
    for purchase, totals in purchases:
        lines += [
            "",
            f"<b>#{purchase.id} · {esc(truncate(purchase.title, 60))}</b>",
            f"{fmt_money(purchase.unit_price, purchase.currency)} / шт. · "
            f"{totals.total_quantity} шт. · до {fmt_datetime(purchase.deadline, tz, False)}",
        ]
    if total_pages > 1:
        lines += ["", f"Страница {page + 1} из {total_pages}"]
    return fit_html("\n".join(lines), MAX_MESSAGE_LENGTH)


# --------------------------------------------------------------------------- #
# Мои покупки и панель организатора
# --------------------------------------------------------------------------- #

MY_PURCHASES_EMPTY = (
    "📦 <b>Мои покупки</b>\n\n"
    "Пока пусто. Создайте закупку или присоединитесь к чужой по ссылке из группы."
)


def my_purchases(
    organized: Sequence[tuple[Purchase, PurchaseTotals]],
    joined: Sequence[tuple[Purchase, Participant]],
    tz: ZoneInfo,
) -> str:
    lines = ["📦 <b>Мои покупки</b>"]

    if organized:
        lines += ["", "<b>Организую</b>"]
        for purchase, totals in organized:
            lines += [
                "",
                f"#{purchase.id} · {esc(truncate(purchase.title, 60))}",
                f"{STATUS_LABELS[purchase.status]} · до {fmt_datetime(purchase.deadline, tz, False)}",
                f"{totals.total_quantity} шт. · "
                f"{fmt_money(totals.total_value, purchase.currency)} · "
                f"{totals.participants_count} "
                f"{plural_ru(totals.participants_count, 'участник', 'участника', 'участников')}",
            ]

    if joined:
        lines += ["", "<b>Участвую</b>"]
        for purchase, participant in joined:
            total = purchase.unit_price * participant.quantity
            lines += [
                "",
                f"#{purchase.id} · {esc(truncate(purchase.title, 60))}",
                f"{STATUS_LABELS[purchase.status]} · до {fmt_datetime(purchase.deadline, tz, False)}",
                f"{participant.quantity} шт. · {fmt_money(total, purchase.currency)}",
            ]

    return fit_html("\n".join(lines), MAX_MESSAGE_LENGTH)


def organizer_panel(purchase: Purchase, totals: PurchaseTotals, tz: ZoneInfo) -> str:
    lines = [
        f"🛠 <b>Совместная покупка #{purchase.id}</b>",
        "",
        f"<b>{esc(truncate(purchase.title, LIMITS['title']))}</b>",
        "",
        f"Статус: {STATUS_LABELS[purchase.status]}",
        f"⏰ Сбор до: {fmt_datetime(purchase.deadline, tz)}",
        "",
        f"👥 Участников: {totals.participants_count}",
        f"📦 Товаров: {totals.total_quantity} шт.",
        f"💰 Общая сумма: {fmt_money(totals.total_value, purchase.currency)}"
        f" из {fmt_money(totals.limit, purchase.currency)}",
        f"🛃 Ориентировочно на единицу: "
        f"{fmt_money(totals.estimated_fee_per_item, purchase.currency)}",
    ]
    if purchase.group_message_id is None and purchase.status != PurchaseStatus.DRAFT:
        lines += ["", "⚠️ Объявление в группе не найдено — обновление недоступно."]
    return "\n".join(lines)


def participants_list(purchase: Purchase, participants: Sequence[Participant]) -> str:
    """Виден только организатору и администратору — здесь допустим Telegram ID."""
    lines = [f"👥 <b>Участники закупки #{purchase.id}</b>", ""]

    if purchase.organizer_quantity > 0:
        organizer_total = purchase.unit_price * purchase.organizer_quantity
        lines += [
            f"👤 {esc(purchase.organizer.display_name)} (организатор)",
            f"   {purchase.organizer_quantity} шт. · "
            f"{fmt_money(organizer_total, purchase.currency)}",
            "",
        ]

    if not participants:
        lines.append("Пока никто не присоединился.")
        return fit_html("\n".join(lines), MAX_MESSAGE_LENGTH)

    for index, participant in enumerate(participants, start=1):
        user = participant.user
        name = esc(user.display_name)
        if not user.username:
            name = f"{name} (ID {user.telegram_id})"
        total = purchase.unit_price * participant.quantity
        lines.append(f"{index}. {name}")
        lines.append(f"   {participant.quantity} шт. · {fmt_money(total, purchase.currency)}")
        if participant.variant:
            lines.append(
                f"   {esc(truncate(participant.variant, LIMITS['participant_variant']))}"
            )
        if participant.comment:
            lines.append(
                f"   💬 {esc(truncate(participant.comment, LIMITS['participant_comment']))}"
            )
        lines.append("")

    return fit_html("\n".join(lines).rstrip(), MAX_MESSAGE_LENGTH)


CLOSE_CONFIRM = (
    "🔒 Закрыть сбор?\n\n"
    "После закрытия новые участники присоединиться не смогут, "
    "а текущие не смогут изменить заявку. Всем участникам придёт уведомление."
)
CANCEL_PURCHASE_CONFIRM = (
    "❌ Отменить закупку?\n\n"
    "Объявление в группе будет помечено как отменённое, "
    "участники получат уведомление. Действие необратимо."
)
PURCHASE_CLOSED = "🔒 Сбор закрыт."
PURCHASE_CANCELLED = "❌ Закупка отменена."


def notify_closed(purchase: Purchase) -> str:
    return (
        f"Сбор по закупке <b>#{purchase.id}</b> "
        f"«{esc(truncate(purchase.title, 80))}» закрыт.\n\n"
        "Организатор переходит к оформлению заказа."
    )


def notify_cancelled(purchase: Purchase) -> str:
    return (
        f"❌ Закупка <b>#{purchase.id}</b> «{esc(truncate(purchase.title, 80))}» отменена "
        "организатором."
    )


def notify_organizer_new_participant(
    purchase: Purchase,
    participant: Participant,
    totals: PurchaseTotals,
) -> str:
    return (
        f"👥 Новый участник в закупке <b>#{purchase.id}</b>.\n\n"
        f"{esc(participant.user.display_name)} — {participant.quantity} шт.\n"
        f"Сейчас собрано: {totals.total_quantity} шт. на "
        f"{fmt_money(totals.total_value, purchase.currency)}."
    )


# --------------------------------------------------------------------------- #
# Администратор
# --------------------------------------------------------------------------- #

ADMIN_ONLY = "Команда доступна только администраторам."


def admin_stats(
    users: int,
    open_purchases: int,
    closed_purchases: int,
    cancelled_purchases: int,
    active_participants: int,
) -> str:
    return (
        "📊 <b>Статистика</b>\n\n"
        f"👤 Пользователей: {users}\n"
        f"🟢 Открытых закупок: {open_purchases}\n"
        f"🔒 Закрытых закупок: {closed_purchases}\n"
        f"❌ Отменённых закупок: {cancelled_purchases}\n"
        f"👥 Активных заявок: {active_participants}"
    )


def admin_purchases(purchases: Sequence[tuple[Purchase, PurchaseTotals]], tz: ZoneInfo) -> str:
    if not purchases:
        return "Закупок пока нет."
    lines = ["🗂 <b>Последние закупки</b>"]
    for purchase, totals in purchases:
        lines += [
            "",
            f"#{purchase.id} · {esc(truncate(purchase.title, 60))}",
            f"{STATUS_LABELS[purchase.status]} · "
            f"{esc(purchase.organizer.display_name)} · "
            f"до {fmt_datetime(purchase.deadline, tz, False)}",
            f"{totals.total_quantity} шт. · {fmt_money(totals.total_value, purchase.currency)}",
        ]
    return fit_html("\n".join(lines), MAX_MESSAGE_LENGTH)


def deadline_autoclosed(purchase: Purchase, when: datetime, tz: ZoneInfo) -> str:
    return (
        f"⏰ Срок сбора по закупке <b>#{purchase.id}</b> "
        f"«{esc(truncate(purchase.title, 80))}» истёк "
        f"{fmt_datetime(when, tz)} — сбор закрыт автоматически."
    )
