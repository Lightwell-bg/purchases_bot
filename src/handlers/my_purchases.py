"""Экран «Мои покупки»."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.database.models import Participant, ParticipantStatus, Purchase, User
from src.database.repositories.purchases import PurchaseRepository
from src.handlers.common import show_screen
from src.keyboards import inline
from src.services import purchase_service
from src.texts import ru

logger = logging.getLogger(__name__)

router = Router(name="my_purchases")
router.message.filter(F.chat.type == ChatType.PRIVATE)


async def _collect(
    session: AsyncSession, user: User
) -> tuple[list[Purchase], list[tuple[Purchase, Participant]]]:
    repo = PurchaseRepository(session)
    organized = await repo.list_organized(user.id)

    joined: list[tuple[Purchase, Participant]] = []
    for purchase in await repo.list_joined(user.id):
        participant = next(
            (
                p
                for p in purchase.participants
                if p.user_id == user.id and p.status == ParticipantStatus.ACTIVE
            ),
            None,
        )
        if participant is not None:
            joined.append((purchase, participant))
    return organized, joined


def _render(
    organized: list[Purchase], joined: list[tuple[Purchase, Participant]]
) -> tuple[str, object]:
    if not organized and not joined:
        return ru.MY_PURCHASES_EMPTY, inline.main_menu()

    tz = get_settings().tz
    text = ru.my_purchases(
        [(purchase, purchase_service.totals(purchase)) for purchase in organized],
        joined,
        tz,
    )
    return text, inline.my_purchases(organized, joined)


async def show_my_purchases(
    target: Message | CallbackQuery, session: AsyncSession, user: User
) -> None:
    organized, joined = await _collect(session, user)
    text, keyboard = _render(organized, joined)
    if isinstance(target, CallbackQuery):
        await show_screen(target, text, keyboard)  # type: ignore[arg-type]
    else:
        await target.answer(text, reply_markup=keyboard)  # type: ignore[arg-type]


@router.message(Command("my"))
async def cmd_my(
    message: Message, state: FSMContext, session: AsyncSession, user: User
) -> None:
    await state.clear()
    await show_my_purchases(message, session, user)
