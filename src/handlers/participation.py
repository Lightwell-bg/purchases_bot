"""Изменение и отзыв собственной заявки участником."""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.database.models import Participant, ParticipantStatus, Purchase, User
from src.database.repositories.participants import ParticipantRepository
from src.database.repositories.purchases import PurchaseRepository
from src.handlers.common import show_screen
from src.keyboards import inline
from src.keyboards.callbacks import PartCB
from src.services import availability, purchase_service, telegram_service
from src.services.purchase_service import PurchaseError
from src.states.purchase import EditParticipation
from src.texts import ru
from src.utils import parsing

logger = logging.getLogger(__name__)

router = Router(name="participation")
router.message.filter(F.chat.type == ChatType.PRIVATE)

PROMPTS = {
    "quantity": ru.ASK_JOIN_QUANTITY,
    "variant": "Новый вариант товара:",
    "comment": "Новый комментарий организатору:",
}


async def _load(
    session: AsyncSession,
    purchase_id: int,
    user: User,
) -> tuple[Purchase, Participant] | None:
    """Закупка и активная заявка пользователя. Права проверяем по базе."""
    purchase = await PurchaseRepository(session).get(purchase_id)
    if purchase is None:
        return None
    participant = await ParticipantRepository(session).get_for_user(purchase.id, user.id)
    if participant is None or participant.status != ParticipantStatus.ACTIVE:
        return None
    return purchase, participant


def _editable(purchase: Purchase) -> bool:
    return availability.can_modify_participation(
        purchase.status, purchase.deadline, purchase_service.utcnow()
    )


@router.callback_query(PartCB.filter(F.action == "view"))
async def view_participation(
    callback: CallbackQuery,
    callback_data: PartCB,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    await state.clear()
    loaded = await _load(session, callback_data.purchase_id, user)
    if loaded is None:
        await callback.answer(ru.PURCHASE_NOT_FOUND, show_alert=True)
        return
    purchase, participant = loaded
    await show_screen(
        callback,
        ru.participation_card(purchase, participant, get_settings().tz),
        inline.participation(purchase.id, editable=_editable(purchase)),
    )
    await callback.answer()


@router.callback_query(PartCB.filter(F.action == "edit"))
async def edit_menu(
    callback: CallbackQuery,
    callback_data: PartCB,
    session: AsyncSession,
    user: User,
) -> None:
    loaded = await _load(session, callback_data.purchase_id, user)
    if loaded is None:
        await callback.answer(ru.PURCHASE_NOT_FOUND, show_alert=True)
        return
    purchase, _ = loaded
    if not _editable(purchase):
        await callback.answer(ru.join_unavailable("CLOSED"), show_alert=True)
        return
    await show_screen(
        callback, ru.EDIT_FIELD_PROMPT, inline.participation_edit_fields(purchase.id)
    )
    await callback.answer()


@router.callback_query(PartCB.filter(F.action == "edit_field"))
async def edit_field(
    callback: CallbackQuery,
    callback_data: PartCB,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    field = callback_data.value
    if field not in PROMPTS:
        await callback.answer()
        return

    loaded = await _load(session, callback_data.purchase_id, user)
    if loaded is None:
        await callback.answer(ru.PURCHASE_NOT_FOUND, show_alert=True)
        return
    purchase, _ = loaded
    if not _editable(purchase):
        await callback.answer(ru.join_unavailable("CLOSED"), show_alert=True)
        return

    await state.set_state(EditParticipation.waiting_value)
    await state.update_data(purchase_id=purchase.id, field=field)
    await show_screen(
        callback, PROMPTS[field], inline.participation_edit_cancel(purchase.id)
    )
    await callback.answer()


@router.message(EditParticipation.waiting_value, F.text)
async def apply_edit(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    bot: Bot,
) -> None:
    settings = get_settings()
    data = await state.get_data()
    field = str(data.get("field", ""))
    loaded = await _load(session, int(data.get("purchase_id", 0)), user)
    if loaded is None or field not in PROMPTS:
        await state.clear()
        await message.answer(ru.PURCHASE_NOT_FOUND, reply_markup=inline.main_menu())
        return

    purchase, participant = loaded
    if not _editable(purchase):
        await state.clear()
        await message.answer(ru.join_unavailable("CLOSED"), reply_markup=inline.main_menu())
        return

    raw = message.text or ""
    try:
        if field == "quantity":
            quantity = parsing.parse_quantity(
                raw, minimum=1, maximum=settings.business.max_items_per_participant
            )
        elif field == "variant":
            variant = parsing.clean_text(raw, 300, "Вариант")
        else:
            comment = parsing.clean_multiline(raw, 500)
    except ValueError as exc:
        await message.answer(f"⚠️ {exc}")
        return

    try:
        if field == "quantity":
            await purchase_service.update_participation(
                session, purchase, participant, quantity=quantity
            )
        elif field == "variant":
            await purchase_service.update_participation(
                session, purchase, participant, variant=variant
            )
        else:
            await purchase_service.update_participation(
                session, purchase, participant, comment=comment
            )
    except PurchaseError:
        check = purchase_service.check_participant_limit(purchase, participant.user_id, quantity)
        await message.answer(ru.limit_exceeded(check, purchase.currency))
        return

    await state.clear()
    await telegram_service.refresh_announcement(bot, session, purchase)
    await session.commit()

    await message.answer(ru.PARTICIPATION_UPDATED)
    await message.answer(
        ru.participation_card(purchase, participant, settings.tz),
        reply_markup=inline.participation(purchase.id),
    )


@router.message(EditParticipation.waiting_value)
async def apply_edit_wrong_type(message: Message) -> None:
    await message.answer(ru.NEED_TEXT)


@router.callback_query(PartCB.filter(F.action == "leave"))
async def leave_prompt(
    callback: CallbackQuery,
    callback_data: PartCB,
    session: AsyncSession,
    user: User,
) -> None:
    loaded = await _load(session, callback_data.purchase_id, user)
    if loaded is None:
        await callback.answer(ru.PURCHASE_NOT_FOUND, show_alert=True)
        return
    purchase, _ = loaded
    if not _editable(purchase):
        await callback.answer(ru.join_unavailable("CLOSED"), show_alert=True)
        return
    await show_screen(callback, ru.LEAVE_CONFIRM, inline.leave_confirm(purchase.id))
    await callback.answer()


@router.callback_query(PartCB.filter(F.action == "leave_confirm"))
async def leave_confirm(
    callback: CallbackQuery,
    callback_data: PartCB,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    bot: Bot,
) -> None:
    loaded = await _load(session, callback_data.purchase_id, user)
    if loaded is None:
        await callback.answer(ru.PURCHASE_NOT_FOUND, show_alert=True)
        return
    purchase, participant = loaded
    if not _editable(purchase):
        await callback.answer(ru.join_unavailable("CLOSED"), show_alert=True)
        return

    await purchase_service.leave_purchase(session, purchase, participant)
    await telegram_service.refresh_announcement(bot, session, purchase)
    await session.commit()

    await state.clear()
    await callback.answer(ru.PARTICIPATION_CANCELLED)
    await show_screen(callback, ru.PARTICIPATION_CANCELLED, inline.main_menu())
