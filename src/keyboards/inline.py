"""Инлайн-клавиатуры."""

from __future__ import annotations

from typing import Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.database.models import Participant, Purchase, PurchaseStatus
from src.keyboards.callbacks import JoinCB, ManageCB, MenuCB, PartCB, RulesCB, WizardCB
from src.utils.formatting import truncate

BTN_CANCEL = "❌ Отмена"
BTN_SKIP = "⏭ Пропустить"
BTN_BACK_TO_MENU = "⬅️ В меню"

# Поля, доступные для правки, — общий словарь для мастера и панели организатора.
PURCHASE_FIELDS: dict[str, str] = {
    "title": "Название",
    "url": "Ссылка",
    "photo": "Фото",
    "price": "Цена",
    "currency": "Валюта",
    "variants": "Варианты",
    "quantity": "Своё количество",
    "deadline": "Дата сбора",
    "pickup": "Место получения",
    "comment": "Комментарий",
}

PARTICIPATION_FIELDS: dict[str, str] = {
    "quantity": "Количество",
    "variant": "Вариант",
    "comment": "Комментарий",
}

CURRENCIES = ("EUR", "USD", "BGN")


def main_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🛒 Создать закупку", callback_data=MenuCB(action="create"))
    builder.button(text="📦 Мои покупки", callback_data=MenuCB(action="my"))
    builder.button(text="📜 Правила", callback_data=MenuCB(action="rules"))
    builder.adjust(1)
    return builder.as_markup()


def back_to_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=BTN_BACK_TO_MENU, callback_data=MenuCB(action="main"))
    return builder.as_markup()


# --------------------------------------------------------------------------- #
# Правила
# --------------------------------------------------------------------------- #

def rules_gate(scope: str, token: str = "") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="📄 Читать правила", callback_data=RulesCB(action="read", scope=scope, token=token)
    )
    builder.button(
        text="✅ Принимаю правила",
        callback_data=RulesCB(action="accept", scope=scope, token=token),
    )
    builder.button(
        text=BTN_CANCEL, callback_data=RulesCB(action="cancel", scope=scope, token=token)
    )
    builder.adjust(1)
    return builder.as_markup()


def rules_after_read(scope: str, token: str = "") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if scope in ("create", "join"):
        builder.button(
            text="✅ Принимаю правила",
            callback_data=RulesCB(action="accept", scope=scope, token=token),
        )
        builder.button(
            text=BTN_CANCEL, callback_data=RulesCB(action="cancel", scope=scope, token=token)
        )
    else:
        builder.button(text=BTN_BACK_TO_MENU, callback_data=MenuCB(action="main"))
    builder.adjust(1)
    return builder.as_markup()


# --------------------------------------------------------------------------- #
# Мастер создания закупки
# --------------------------------------------------------------------------- #

def wizard_step(skippable: bool = False, editing: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if skippable:
        builder.button(text=BTN_SKIP, callback_data=WizardCB(action="skip"))
    if editing:
        builder.button(text="⬅️ К предпросмотру", callback_data=WizardCB(action="back"))
    builder.button(text=BTN_CANCEL, callback_data=WizardCB(action="cancel"))
    builder.adjust(1)
    return builder.as_markup()


def wizard_currency() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for code in CURRENCIES:
        builder.button(text=code, callback_data=WizardCB(action="currency", value=code))
    builder.button(text=BTN_CANCEL, callback_data=WizardCB(action="cancel"))
    builder.adjust(len(CURRENCIES), 1)
    return builder.as_markup()


def wizard_preview() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Опубликовать", callback_data=WizardCB(action="publish"))
    builder.button(text="✏️ Изменить", callback_data=WizardCB(action="edit"))
    builder.button(text=BTN_CANCEL, callback_data=WizardCB(action="cancel"))
    builder.adjust(1)
    return builder.as_markup()


def wizard_edit_fields() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for field, label in PURCHASE_FIELDS.items():
        builder.button(
            text=label, callback_data=WizardCB(action="edit_field", value=field)
        )
    builder.button(text="⬅️ К предпросмотру", callback_data=WizardCB(action="back"))
    builder.adjust(2, 2, 2, 2, 2, 1)
    return builder.as_markup()


# --------------------------------------------------------------------------- #
# Группа
# --------------------------------------------------------------------------- #

def group_create_link(deep_link: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Создать совместную покупку", url=deep_link)
    return builder.as_markup()


def group_open_bot(deep_link: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✍️ Открыть бота", url=deep_link)
    return builder.as_markup()


def announcement(
    join_link: str,
    rules_link: str,
    joinable: bool,
    create_link: str | None = None,
) -> InlineKeyboardMarkup:
    """Клавиатура под объявлением в группе.

    Кнопка создания своей закупки повторяется на каждом объявлении: человек,
    листающий чужие закупки, не должен искать закреплённое сообщение или
    вспоминать команду — выход к созданию должен быть там же, где он смотрит.
    """
    builder = InlineKeyboardBuilder()
    if joinable:
        builder.button(text="🛒 Присоединиться", url=join_link)
    if create_link:
        builder.button(text="➕ Создать свою закупку", url=create_link)
    builder.button(text="📜 Правила", url=rules_link)
    builder.adjust(1)
    return builder.as_markup()


# --------------------------------------------------------------------------- #
# Присоединение
# --------------------------------------------------------------------------- #

def join_start(token: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🛒 Присоединиться", callback_data=JoinCB(action="start", token=token))
    builder.button(text=BTN_BACK_TO_MENU, callback_data=MenuCB(action="main"))
    builder.adjust(1)
    return builder.as_markup()


def join_step(token: str, skippable: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if skippable:
        builder.button(text=BTN_SKIP, callback_data=JoinCB(action="skip", token=token))
    builder.button(text=BTN_CANCEL, callback_data=JoinCB(action="cancel", token=token))
    builder.adjust(1)
    return builder.as_markup()


def join_preview(token: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить", callback_data=JoinCB(action="confirm", token=token))
    builder.button(text="✏️ Изменить", callback_data=JoinCB(action="edit", token=token))
    builder.button(text=BTN_CANCEL, callback_data=JoinCB(action="cancel", token=token))
    builder.adjust(1)
    return builder.as_markup()


def join_edit_fields(token: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for field, label in PARTICIPATION_FIELDS.items():
        builder.button(
            text=label, callback_data=JoinCB(action="edit_field", token=token, value=field)
        )
    builder.button(text=BTN_CANCEL, callback_data=JoinCB(action="cancel", token=token))
    builder.adjust(1)
    return builder.as_markup()


# --------------------------------------------------------------------------- #
# Своя заявка
# --------------------------------------------------------------------------- #

def participation(purchase_id: int, editable: bool = True) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if editable:
        builder.button(
            text="✏️ Изменить", callback_data=PartCB(action="edit", purchase_id=purchase_id)
        )
        builder.button(
            text="❌ Отказаться", callback_data=PartCB(action="leave", purchase_id=purchase_id)
        )
    builder.button(text="📦 Мои покупки", callback_data=MenuCB(action="my"))
    builder.adjust(2, 1)
    return builder.as_markup()


def participation_edit_fields(purchase_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for field, label in PARTICIPATION_FIELDS.items():
        builder.button(
            text=label,
            callback_data=PartCB(action="edit_field", purchase_id=purchase_id, value=field),
        )
    builder.button(
        text="⬅️ Назад", callback_data=PartCB(action="view", purchase_id=purchase_id)
    )
    builder.adjust(1)
    return builder.as_markup()


def participation_edit_cancel(purchase_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=BTN_CANCEL, callback_data=PartCB(action="view", purchase_id=purchase_id))
    return builder.as_markup()


def leave_confirm(purchase_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="❌ Да, отказаться",
        callback_data=PartCB(action="leave_confirm", purchase_id=purchase_id),
    )
    builder.button(
        text="⬅️ Назад", callback_data=PartCB(action="view", purchase_id=purchase_id)
    )
    builder.adjust(1)
    return builder.as_markup()


# --------------------------------------------------------------------------- #
# Мои покупки
# --------------------------------------------------------------------------- #

def my_purchases(
    organized: Sequence[Purchase],
    joined: Sequence[tuple[Purchase, Participant]],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for purchase in organized:
        builder.button(
            text=f"🛠 #{purchase.id} {truncate(purchase.title, 24)}",
            callback_data=ManageCB(action="panel", purchase_id=purchase.id),
        )
    for purchase, _ in joined:
        builder.button(
            text=f"📦 #{purchase.id} {truncate(purchase.title, 24)}",
            callback_data=PartCB(action="view", purchase_id=purchase.id),
        )
    builder.button(text=BTN_BACK_TO_MENU, callback_data=MenuCB(action="main"))
    builder.adjust(1)
    return builder.as_markup()


# --------------------------------------------------------------------------- #
# Панель организатора
# --------------------------------------------------------------------------- #

def organizer_panel(purchase: Purchase) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="👥 Участники",
        callback_data=ManageCB(action="participants", purchase_id=purchase.id),
    )
    if purchase.status == PurchaseStatus.OPEN:
        builder.button(
            text="✏️ Изменить закупку",
            callback_data=ManageCB(action="edit", purchase_id=purchase.id),
        )
        builder.button(
            text="🔒 Закрыть сбор",
            callback_data=ManageCB(action="close", purchase_id=purchase.id),
        )
    if purchase.status in (PurchaseStatus.OPEN, PurchaseStatus.CLOSED):
        builder.button(
            text="❌ Отменить закупку",
            callback_data=ManageCB(action="cancel", purchase_id=purchase.id),
        )
    builder.button(text="📦 Мои покупки", callback_data=MenuCB(action="my"))
    builder.adjust(1)
    return builder.as_markup()


def manage_edit_fields(purchase_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for field, label in PURCHASE_FIELDS.items():
        if field == "currency":
            continue  # менять валюту после публикации нельзя — собьются расчёты
        builder.button(
            text=label,
            callback_data=ManageCB(action="edit_field", purchase_id=purchase_id, value=field),
        )
    builder.button(
        text="⬅️ Назад", callback_data=ManageCB(action="panel", purchase_id=purchase_id)
    )
    builder.adjust(2, 2, 2, 2, 1)
    return builder.as_markup()


def manage_edit_cancel(purchase_id: int, skippable: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if skippable:
        builder.button(
            text="🗑 Очистить поле",
            callback_data=ManageCB(action="clear_field", purchase_id=purchase_id),
        )
    builder.button(
        text=BTN_CANCEL, callback_data=ManageCB(action="panel", purchase_id=purchase_id)
    )
    builder.adjust(1)
    return builder.as_markup()


def back_to_panel(purchase_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="⬅️ Назад", callback_data=ManageCB(action="panel", purchase_id=purchase_id)
    )
    return builder.as_markup()


def confirm_close(purchase_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🔒 Да, закрыть сбор",
        callback_data=ManageCB(action="close_yes", purchase_id=purchase_id),
    )
    builder.button(
        text="⬅️ Назад", callback_data=ManageCB(action="panel", purchase_id=purchase_id)
    )
    builder.adjust(1)
    return builder.as_markup()


def confirm_cancel(purchase_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="❌ Да, отменить закупку",
        callback_data=ManageCB(action="cancel_yes", purchase_id=purchase_id),
    )
    builder.button(
        text="⬅️ Назад", callback_data=ManageCB(action="panel", purchase_id=purchase_id)
    )
    builder.adjust(1)
    return builder.as_markup()


def url_button(text: str, url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text, url=url)]])
