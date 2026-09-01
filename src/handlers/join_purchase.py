"""Присоединение к закупке по deep link."""

from __future__ import annotations

import logging
from typing import Any

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.database.models import ParticipantStatus, Purchase, RulesAction, User
from src.database.repositories.participants import ParticipantRepository
from src.database.repositories.purchases import PurchaseRepository
from src.handlers.common import show_main_menu, show_screen
from src.keyboards import inline
from src.keyboards.callbacks import JoinCB
from src.services import availability, purchase_service, telegram_service
from src.services.purchase_service import PurchaseError
from src.states.purchase import JoinPurchase
from src.texts import ru
from src.utils import parsing

logger = logging.getLogger(__name__)

router = Router(name="join_purchase")
router.message.filter(F.chat.type == ChatType.PRIVATE)

ORDER: tuple[str, ...] = ("quantity", "variant", "comment")

STEPS: dict[str, tuple[State, bool]] = {
    "quantity": (JoinPurchase.quantity, False),
    "variant": (JoinPurchase.variant, True),
    "comment": (JoinPurchase.comment, True),
}

DATA_KEYS = {"quantity": "quantity", "variant": "variant", "comment": "comment"}

STATE_TO_FIELD = {STEPS[field][0].state: field for field in STEPS}  # type: ignore[union-attr]

TEXT_STATES = StateFilter(JoinPurchase.quantity, JoinPurchase.variant, JoinPurchase.comment)


def _message_of(target: Message | CallbackQuery) -> Message | None:
    if isinstance(target, CallbackQuery):
        return target.message if isinstance(target.message, Message) else None
    return target


async def _load_purchase(session: AsyncSession, token: str) -> Purchase | None:
    return await PurchaseRepository(session).get_by_token(token)


# --------------------------------------------------------------------------- #
# Вход по ссылке
# --------------------------------------------------------------------------- #

async def join_entry(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    token: str,
) -> None:
    """Экран закупки для пришедшего по ссылке пользователя."""
    await state.clear()
    settings = get_settings()
    purchase = await _load_purchase(session, token)
    if purchase is None:
        await message.answer(ru.PURCHASE_NOT_FOUND, reply_markup=inline.main_menu())
        return

    totals = purchase_service.totals(purchase)
    card = ru.purchase_short_card(purchase, totals, settings.tz)

    if purchase_service.is_organizer(purchase, user):
        await telegram_service.send_purchase_card(
            message,
            purchase,
            f"{card}\n\n{ru.ORGANIZER_CANNOT_JOIN}",
            inline.organizer_panel(purchase),
        )
        return

    participant = await ParticipantRepository(session).get_for_user(purchase.id, user.id)
    if participant is not None and participant.status == ParticipantStatus.ACTIVE:
        editable = availability.can_modify_participation(
            purchase.status, purchase.deadline, purchase_service.utcnow()
        )
        await telegram_service.send_purchase_card(
            message,
            purchase,
            ru.participation_card(purchase, participant, settings.tz),
            inline.participation(purchase.id, editable=editable),
        )
        return

    reason = availability.join_block_reason(
        purchase.status, purchase.deadline, purchase_service.utcnow()
    )
    if reason is not None:
        await telegram_service.send_purchase_card(
            message,
            purchase,
            f"{card}\n\n{ru.join_unavailable(reason.value)}",
            inline.back_to_menu(),
        )
        return

    await telegram_service.send_purchase_card(
        message, purchase, card, inline.join_start(purchase.public_token)
    )


@router.callback_query(JoinCB.filter(F.action == "start"))
async def join_start(
    callback: CallbackQuery,
    callback_data: JoinCB,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    from src.handlers.rules import ensure_rules

    purchase = await _load_purchase(session, callback_data.token)
    if purchase is None:
        await callback.answer(ru.PURCHASE_NOT_FOUND, show_alert=True)
        return

    reason = availability.join_block_reason(
        purchase.status, purchase.deadline, purchase_service.utcnow()
    )
    if reason is not None:
        await callback.answer(ru.join_unavailable(reason.value), show_alert=True)
        return

    if purchase_service.is_organizer(purchase, user):
        await callback.answer(ru.ORGANIZER_CANNOT_JOIN, show_alert=True)
        return

    await callback.answer()
    if await ensure_rules(
        callback, session, user, RulesAction.JOIN_PURCHASE, "join", purchase.public_token
    ):
        await start_join_form(callback, state, session, user, purchase)


async def start_join_form(
    target: Message | CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    purchase: Purchase,
) -> None:
    """Запускает форму участия. Правила к этому моменту уже приняты."""
    await state.clear()
    await state.update_data(token=purchase.public_token, editing=False)
    await _ask(target, state, "quantity", purchase)


# --------------------------------------------------------------------------- #
# Шаги формы
# --------------------------------------------------------------------------- #

async def _ask(
    target: Message | CallbackQuery,
    state: FSMContext,
    field: str,
    purchase: Purchase,
) -> None:
    fsm_state, skippable = STEPS[field]
    prompts = {
        "quantity": ru.ASK_JOIN_QUANTITY,
        "variant": ru.ask_join_variant(purchase),
        "comment": ru.ASK_JOIN_COMMENT,
    }
    await state.set_state(fsm_state)
    keyboard = inline.join_step(purchase.public_token, skippable=skippable)

    message = _message_of(target)
    if message is None:
        return
    await message.answer(prompts[field], reply_markup=keyboard)


async def _advance(
    target: Message | CallbackQuery,
    state: FSMContext,
    field: str,
    purchase: Purchase,
) -> None:
    data = await state.get_data()
    if data.get("editing"):
        await state.update_data(editing=False)
        await _show_preview(target, state, purchase)
        return

    index = ORDER.index(field)
    if index + 1 < len(ORDER):
        await _ask(target, state, ORDER[index + 1], purchase)
    else:
        await _show_preview(target, state, purchase)


async def _show_preview(
    target: Message | CallbackQuery,
    state: FSMContext,
    purchase: Purchase,
) -> None:
    data = await state.get_data()
    text = ru.join_preview(
        purchase,
        int(data.get("quantity", 1)),
        data.get("variant"),
        data.get("comment"),
    )
    await state.set_state(JoinPurchase.preview)
    message = _message_of(target)
    if message is None:
        return
    await message.answer(text, reply_markup=inline.join_preview(purchase.public_token))


class LimitError(Exception):
    """Превышение лимита закупки: текст уже готов к показу."""


def _validate(field: str, raw: str, purchase: Purchase, user_id: int) -> Any:
    business = get_settings().business
    if field == "quantity":
        quantity = parsing.parse_quantity(
            raw, minimum=1, maximum=business.max_items_per_participant
        )
        check = purchase_service.check_participant_limit(purchase, user_id, quantity)
        if not check.allowed:
            raise LimitError(ru.limit_exceeded(check, purchase.currency))
        return quantity
    if field == "variant":
        return parsing.clean_text(raw, 300, "Вариант")
    if field == "comment":
        return parsing.clean_multiline(raw, 500)
    raise ValueError("Неизвестный шаг.")


@router.message(TEXT_STATES, F.text)
async def join_text_step(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    current = await state.get_state()
    field = STATE_TO_FIELD.get(current or "")
    if field is None:
        return

    data = await state.get_data()
    purchase = await _load_purchase(session, str(data.get("token", "")))
    if purchase is None:
        await state.clear()
        await message.answer(ru.PURCHASE_NOT_FOUND, reply_markup=inline.main_menu())
        return

    try:
        value = _validate(field, message.text or "", purchase, user.id)
    except LimitError as exc:
        await message.answer(str(exc))
        return
    except ValueError as exc:
        await message.answer(f"⚠️ {exc}")
        return

    await state.update_data(**{DATA_KEYS[field]: value})
    await _advance(message, state, field, purchase)


@router.message(TEXT_STATES)
async def join_wrong_type(message: Message) -> None:
    await message.answer(ru.NEED_TEXT)


@router.callback_query(JoinCB.filter(F.action == "skip"))
async def join_skip(
    callback: CallbackQuery,
    callback_data: JoinCB,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    current = await state.get_state()
    field = STATE_TO_FIELD.get(current or "")
    if field is None or not STEPS[field][1]:
        await callback.answer()
        return

    purchase = await _load_purchase(session, callback_data.token)
    if purchase is None:
        await callback.answer(ru.PURCHASE_NOT_FOUND, show_alert=True)
        return

    await state.update_data(**{DATA_KEYS[field]: None})
    await callback.answer()
    await _advance(callback, state, field, purchase)


@router.callback_query(JoinCB.filter(F.action == "cancel"))
async def join_cancel(callback: CallbackQuery, state: FSMContext, user: User) -> None:
    await show_main_menu(callback, state, user)
    await callback.answer(ru.CANCELLED)


@router.callback_query(JoinCB.filter(F.action == "edit"), JoinPurchase.preview)
async def join_edit(callback: CallbackQuery, callback_data: JoinCB) -> None:
    await show_screen(
        callback, ru.EDIT_FIELD_PROMPT, inline.join_edit_fields(callback_data.token)
    )
    await callback.answer()


@router.callback_query(JoinCB.filter(F.action == "edit_field"))
async def join_edit_field(
    callback: CallbackQuery,
    callback_data: JoinCB,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    field = callback_data.value
    if field not in STEPS:
        await callback.answer()
        return
    purchase = await _load_purchase(session, callback_data.token)
    if purchase is None:
        await callback.answer(ru.PURCHASE_NOT_FOUND, show_alert=True)
        return

    await state.update_data(editing=True)
    await callback.answer()
    await _ask(callback, state, field, purchase)


@router.callback_query(JoinCB.filter(F.action == "confirm"), JoinPurchase.preview)
async def join_confirm(
    callback: CallbackQuery,
    callback_data: JoinCB,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    bot: Bot,
) -> None:
    """Финальная проверка и сохранение заявки."""
    settings = get_settings()
    data = await state.get_data()
    purchase = await _load_purchase(session, callback_data.token)
    if purchase is None:
        await state.clear()
        await callback.answer(ru.PURCHASE_NOT_FOUND, show_alert=True)
        return

    reason = availability.join_block_reason(
        purchase.status, purchase.deadline, purchase_service.utcnow()
    )
    if reason is not None:
        await state.clear()
        await callback.answer(ru.join_unavailable(reason.value), show_alert=True)
        return

    if purchase_service.is_organizer(purchase, user):
        await state.clear()
        await callback.answer(ru.ORGANIZER_CANNOT_JOIN, show_alert=True)
        return

    quantity = int(data.get("quantity", 0))
    if quantity <= 0:
        await callback.answer(ru.OUTDATED_CALLBACK, show_alert=True)
        await show_main_menu(callback, state, user)
        return

    try:
        result = await purchase_service.join_purchase(
            session,
            purchase,
            user,
            quantity=quantity,
            variant=data.get("variant"),
            comment=data.get("comment"),
        )
    except PurchaseError:
        check = purchase_service.check_participant_limit(purchase, user.id, quantity)
        await callback.answer()
        message = _message_of(callback)
        if message is not None:
            await message.answer(ru.limit_exceeded(check, purchase.currency))
        return

    await state.clear()
    await telegram_service.refresh_announcement(bot, session, purchase)
    await session.commit()

    totals = purchase_service.totals(purchase)
    await telegram_service.notify_users(
        bot,
        [purchase.organizer.telegram_id],
        ru.notify_organizer_new_participant(purchase, result.participant, totals),
    )

    await callback.answer(ru.JOINED)
    message = _message_of(callback)
    if message is not None:
        await message.answer(
            ru.participation_card(purchase, result.participant, settings.tz),
            reply_markup=inline.participation(purchase.id),
        )
