"""Команды администратора сервиса."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.database.models import PurchaseStatus, User
from src.database.repositories.participants import ParticipantRepository
from src.database.repositories.purchases import PurchaseRepository
from src.database.repositories.users import UserRepository
from src.services import purchase_service
from src.texts import ru

logger = logging.getLogger(__name__)

router = Router(name="admin")
router.message.filter(F.chat.type == ChatType.PRIVATE)


def _is_admin(user: User) -> bool:
    return get_settings().is_admin(user.telegram_id)


@router.message(Command("stats"))
async def cmd_stats(message: Message, session: AsyncSession, user: User) -> None:
    if not _is_admin(user):
        await message.answer(ru.ADMIN_ONLY)
        return

    purchases = PurchaseRepository(session)
    await message.answer(
        ru.admin_stats(
            users=await UserRepository(session).count(),
            open_purchases=await purchases.count_by_status(PurchaseStatus.OPEN),
            closed_purchases=await purchases.count_by_status(PurchaseStatus.CLOSED),
            cancelled_purchases=await purchases.count_by_status(PurchaseStatus.CANCELLED),
            active_participants=await ParticipantRepository(session).count_active(),
        )
    )


@router.message(Command("purchases"))
async def cmd_purchases(message: Message, session: AsyncSession, user: User) -> None:
    if not _is_admin(user):
        await message.answer(ru.ADMIN_ONLY)
        return

    rows = await PurchaseRepository(session).list_recent(limit=10)
    await message.answer(
        ru.admin_purchases(
            [(purchase, purchase_service.totals(purchase)) for purchase in rows],
            get_settings().tz,
        ),
        disable_web_page_preview=True,
    )
