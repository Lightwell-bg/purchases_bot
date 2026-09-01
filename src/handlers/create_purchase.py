"""Мастер создания закупки (FSM) и публикация объявления."""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.database.models import RulesAction, User
from src.handlers.common import show_main_menu, show_screen
from src.keyboards import inline
from src.keyboards.callbacks import WizardCB
from src.services import purchase_service, telegram_service
from src.states.purchase import CreatePurchase
from src.texts import ru
from src.utils import parsing
from src.utils.formatting import fmt_money, group_message_link

logger = logging.getLogger(__name__)

router = Router(name="create_purchase")
router.message.filter(F.chat.type == ChatType.PRIVATE)

# Порядок шагов мастера.
ORDER: tuple[str, ...] = (
    "title",
    "url",
    "photo",
    "price",
    "currency",
    "variants",
    "quantity",
    "deadline",
    "pickup",
    "comment",
)

# field -> (состояние FSM, текст вопроса, можно ли пропустить)
STEPS: dict[str, tuple[State, str, bool]] = {
    "title": (CreatePurchase.title, ru.ASK_TITLE, False),
    "url": (CreatePurchase.product_url, ru.ASK_URL, True),
    "photo": (CreatePurchase.photo, ru.ASK_PHOTO, True),
    "price": (CreatePurchase.unit_price, ru.ASK_PRICE, False),
    "currency": (CreatePurchase.currency, ru.ASK_CURRENCY, False),
    "variants": (CreatePurchase.variants, ru.ASK_VARIANTS, True),
    "quantity": (CreatePurchase.organizer_quantity, ru.ASK_ORGANIZER_QTY, False),
    "deadline": (CreatePurchase.deadline, ru.ASK_DEADLINE, False),
    "pickup": (CreatePurchase.pickup, ru.ASK_PICKUP, False),
    "comment": (CreatePurchase.comment, ru.ASK_COMMENT, True),
}

# field -> ключ в черновике
DATA_KEYS: dict[str, str] = {
    "title": "title",
    "url": "product_url",
    "photo": "photo_file_id",
    "price": "unit_price",
    "currency": "currency",
    "variants": "variant_description",
    "quantity": "organizer_quantity",
    "deadline": "deadline",
    "pickup": "pickup_location",
    "comment": "description",
}

STATE_TO_FIELD: dict[str, str] = {
    STEPS[field][0].state: field for field in STEPS  # type: ignore[union-attr]
}

TEXT_STATES = StateFilter(
    CreatePurchase.title,
    CreatePurchase.product_url,
    CreatePurchase.unit_price,
    CreatePurchase.currency,
    CreatePurchase.variants,
    CreatePurchase.organizer_quantity,
    CreatePurchase.deadline,
    CreatePurchase.pickup,
    CreatePurchase.comment,
)


# --------------------------------------------------------------------------- #
# Вспомогательное
# --------------------------------------------------------------------------- #

def _message_of(target: Message | CallbackQuery) -> Message | None:
    if isinstance(target, CallbackQuery):
        return target.message if isinstance(target.message, Message) else None
    return target


def materialize(data: dict[str, Any]) -> dict[str, Any]:
    """Превращает черновик из FSM в значения нужных типов."""
    draft = dict(data)
    draft["unit_price"] = Decimal(str(data["unit_price"]))
    draft["deadline"] = datetime.fromisoformat(str(data["deadline"]))
    draft["organizer_quantity"] = int(data.get("organizer_quantity") or 0)
    return draft


def _validate(field: str, raw: str, draft: dict[str, Any]) -> Any:
    """Проверяет ввод одного шага. ValueError -> текст ошибки пользователю."""
    settings = get_settings()
    business = settings.business

    if field == "title":
        return parsing.clean_text(raw, 200, "Название")
    if field == "url":
        return parsing.parse_url(raw)
    if field == "price":
        return parsing.parse_price(raw)
    if field == "currency":
        code = raw.strip().upper()
        if not code.isalpha() or not 3 <= len(code) <= 4:
            raise ValueError("Укажите код валюты из трёх букв, например EUR.")
        return code
    if field == "variants":
        return parsing.clean_text(raw, 500, "Описание вариантов")
    if field == "quantity":
        quantity = parsing.parse_quantity(raw, minimum=0, maximum=business.max_items_per_participant)
        price = Decimal(str(draft.get("unit_price", "0")))
        check = purchase_service.check_draft_limit(price, quantity)
        if not check.allowed:
            currency = str(draft.get("currency", "EUR"))
            raise ValueError(
                f"Столько не влезает в лимит {fmt_money(check.limit, currency)}. "
                f"Максимум {check.max_quantity} шт."
            )
        return quantity
    if field == "deadline":
        return parsing.parse_deadline(
            raw, settings.tz, purchase_service.utcnow(), business.max_deadline_days
        )
    if field == "pickup":
        return parsing.clean_text(raw, 200, "Место получения")
    if field == "comment":
        return parsing.clean_multiline(raw, 500)
    raise ValueError("Неизвестный шаг.")


def _store(field: str, value: Any) -> dict[str, Any]:
    """Готовит значение к хранению в FSM (только сериализуемые типы)."""
    key = DATA_KEYS[field]
    if isinstance(value, Decimal):
        return {key: str(value)}
    if isinstance(value, datetime):
        return {key: value.isoformat()}
    return {key: value}


async def _ask(target: Message | CallbackQuery, state: FSMContext, field: str) -> None:
    fsm_state, prompt, skippable = STEPS[field]
    data = await state.get_data()
    editing = bool(data.get("editing"))

    keyboard = (
        inline.wizard_currency()
        if field == "currency"
        else inline.wizard_step(skippable=skippable, editing=editing)
    )
    text = prompt
    if field == "price":
        business = get_settings().business
        text = f"{prompt}\n\n{ru.wizard_price_hint(business.purchase_limit_eur, 'EUR')}"

    await state.set_state(fsm_state)

    message = _message_of(target)
    if message is None:
        return
    if isinstance(target, CallbackQuery) and not (message.photo or message.video):
        await show_screen(target, text, keyboard)
    else:
        await message.answer(text, reply_markup=keyboard)


async def _advance(target: Message | CallbackQuery, state: FSMContext, field: str) -> None:
    """Переход к следующему шагу или к предпросмотру."""
    data = await state.get_data()
    if data.get("editing"):
        await state.update_data(editing=False)
        await show_preview(target, state)
        return

    index = ORDER.index(field)
    if index + 1 < len(ORDER):
        await _ask(target, state, ORDER[index + 1])
    else:
        await show_preview(target, state)


async def show_preview(target: Message | CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    draft = materialize(data)
    text = ru.purchase_preview(draft, get_settings().tz)
    keyboard = inline.wizard_preview()

    await state.set_state(CreatePurchase.preview)

    message = _message_of(target)
    if message is None:
        return
    if draft.get("photo_file_id"):
        await message.answer_photo(
            photo=draft["photo_file_id"], caption=text, reply_markup=keyboard
        )
    else:
        await message.answer(text, reply_markup=keyboard, disable_web_page_preview=True)


async def start_wizard(target: Message | CallbackQuery, state: FSMContext) -> None:
    """Начало мастера. Согласие с правилами проверяется до вызова."""
    await state.clear()
    await state.update_data(editing=False, currency="EUR")
    message = _message_of(target)
    if message is None:
        return
    await message.answer(ru.WIZARD_INTRO)
    # Первый вопрос отправляем новым сообщением, а не правкой меню,
    # иначе он окажется выше вступления.
    await _ask(message, state, ORDER[0])


# --------------------------------------------------------------------------- #
# Шаги
# --------------------------------------------------------------------------- #

@router.message(Command("buy"))
async def cmd_buy_private(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    from src.handlers.rules import ensure_rules

    await state.clear()
    if await ensure_rules(message, session, user, RulesAction.CREATE_PURCHASE, "create"):
        await start_wizard(message, state)


@router.message(TEXT_STATES, F.text)
async def wizard_text_step(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    field = STATE_TO_FIELD.get(current or "")
    if field is None:
        return

    data = await state.get_data()
    try:
        value = _validate(field, message.text or "", data)
    except ValueError as exc:
        await message.answer(f"⚠️ {exc}")
        return

    await state.update_data(**_store(field, value))
    await _advance(message, state, field)


@router.message(TEXT_STATES)
async def wizard_wrong_type(message: Message) -> None:
    await message.answer(ru.NEED_TEXT)


@router.message(CreatePurchase.photo, F.photo)
async def wizard_photo(message: Message, state: FSMContext) -> None:
    """Сохраняем только file_id — файл не скачиваем."""
    photo = message.photo[-1] if message.photo else None
    if photo is None:
        await message.answer(ru.NEED_PHOTO)
        return
    await state.update_data(photo_file_id=photo.file_id)
    await _advance(message, state, "photo")


@router.message(CreatePurchase.photo)
async def wizard_photo_wrong_type(message: Message) -> None:
    await message.answer(ru.NEED_PHOTO)


@router.callback_query(WizardCB.filter(F.action == "currency"), CreatePurchase.currency)
async def wizard_currency(
    callback: CallbackQuery,
    callback_data: WizardCB,
    state: FSMContext,
) -> None:
    await state.update_data(currency=callback_data.value)
    await callback.answer()
    await _advance(callback, state, "currency")


@router.callback_query(WizardCB.filter(F.action == "skip"))
async def wizard_skip(callback: CallbackQuery, state: FSMContext) -> None:
    current = await state.get_state()
    field = STATE_TO_FIELD.get(current or "")
    if field is None or not STEPS[field][2]:
        await callback.answer()
        return
    await state.update_data(**{DATA_KEYS[field]: None})
    await callback.answer()
    await _advance(callback, state, field)


@router.callback_query(WizardCB.filter(F.action == "cancel"))
async def wizard_cancel(callback: CallbackQuery, state: FSMContext, user: User) -> None:
    await show_main_menu(callback, state, user)
    await callback.answer(ru.CANCELLED)


@router.callback_query(WizardCB.filter(F.action == "edit"), CreatePurchase.preview)
async def wizard_edit(callback: CallbackQuery) -> None:
    await show_screen(callback, ru.EDIT_FIELD_PROMPT, inline.wizard_edit_fields())
    await callback.answer()


@router.callback_query(WizardCB.filter(F.action == "edit_field"))
async def wizard_edit_field(
    callback: CallbackQuery,
    callback_data: WizardCB,
    state: FSMContext,
) -> None:
    field = callback_data.value
    if field not in STEPS:
        await callback.answer()
        return
    await state.update_data(editing=True)
    await callback.answer()
    await _ask(callback, state, field)


@router.callback_query(WizardCB.filter(F.action == "back"))
async def wizard_back(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(editing=False)
    await callback.answer()
    await show_preview(callback, state)


@router.callback_query(WizardCB.filter(F.action == "publish"), CreatePurchase.preview)
async def wizard_publish(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    bot: Bot,
) -> None:
    """Создаёт закупку и публикует объявление в группе."""
    settings = get_settings()
    data = await state.get_data()
    if "title" not in data or "unit_price" not in data or "deadline" not in data:
        await callback.answer(ru.OUTDATED_CALLBACK, show_alert=True)
        await show_main_menu(callback, state, user)
        return

    if not settings.main_group_id:
        await callback.answer()
        await show_screen(callback, ru.GROUP_NOT_CONFIGURED, inline.back_to_menu())
        return

    await callback.answer()
    draft = materialize(data)
    purchase = await purchase_service.create_purchase(session, user, draft)

    published = await telegram_service.publish_purchase(bot, session, purchase)
    await state.clear()

    message = _message_of(callback)
    if message is None:
        return

    if not published:
        await message.answer(ru.PUBLISH_FAILED, reply_markup=inline.back_to_menu())
        return

    link = group_message_link(purchase.group_chat_id, purchase.group_message_id)
    await message.answer(
        ru.published(purchase, link),
        reply_markup=inline.organizer_panel(purchase),
        disable_web_page_preview=True,
    )
