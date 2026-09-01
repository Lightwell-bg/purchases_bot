"""Команды администратора сервиса."""

from __future__ import annotations

import logging
from typing import Any

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.database.models import User
from src.database.repositories.participants import ParticipantRepository
from src.database.repositories.purchases import PurchaseRepository
from src.database.repositories.users import UserRepository
from src.handlers.common import show_screen
from src.keyboards import inline
from src.keyboards.callbacks import AdminCB, MenuCB
from src.services import purchase_service
from src.texts import ru
from src.utils.pagination import paginate

logger = logging.getLogger(__name__)

router = Router(name="admin")
router.message.filter(F.chat.type == ChatType.PRIVATE)

PAGE_SIZE = 5


def _is_admin(user: User) -> bool:
    return get_settings().is_admin(user.telegram_id)


async def _render_stats(session: AsyncSession) -> str:
    return ru.admin_stats(
        users=await UserRepository(session).count(),
        status_counts=await PurchaseRepository(session).count_by_status_all(),
        active_participants=await ParticipantRepository(session).count_active(),
    )


async def render_admin_purchases_page(session: AsyncSession, page: int) -> tuple[str, Any]:
    """Собирает (текст, клавиатуру) для одной страницы списка «Все закупки»."""
    settings = get_settings()
    repo = PurchaseRepository(session)

    total = await repo.count_all()
    if total == 0:
        return ru.ADMIN_PURCHASES_EMPTY, inline.back_to_menu()

    page, total_pages = paginate(total, page, PAGE_SIZE)
    purchases = await repo.list_all(PAGE_SIZE, page * PAGE_SIZE)

    text = ru.admin_purchases_page(
        [(p, purchase_service.totals(p)) for p in purchases],
        page,
        total_pages,
        total,
        settings.tz,
    )
    keyboard = inline.admin_purchases_list(purchases, page, total_pages)
    return text, keyboard


@router.message(Command("stats"))
async def cmd_stats(message: Message, session: AsyncSession, user: User) -> None:
    if not _is_admin(user):
        await message.answer(ru.ADMIN_ONLY)
        return
    await message.answer(await _render_stats(session))


@router.message(Command("purchases"))
async def cmd_purchases(message: Message, session: AsyncSession, user: User) -> None:
    if not _is_admin(user):
        await message.answer(ru.ADMIN_ONLY)
        return
    text, keyboard = await render_admin_purchases_page(session, 0)
    await message.answer(text, reply_markup=keyboard, disable_web_page_preview=True)


@router.callback_query(MenuCB.filter(F.action == "stats"))
async def menu_stats(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    await state.clear()
    if not _is_admin(user):
        await callback.answer(ru.ADMIN_ONLY, show_alert=True)
        return
    await show_screen(callback, await _render_stats(session), inline.back_to_menu())
    await callback.answer()


@router.callback_query(MenuCB.filter(F.action == "purchases"))
async def menu_admin_purchases(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    await state.clear()
    if not _is_admin(user):
        await callback.answer(ru.ADMIN_ONLY, show_alert=True)
        return
    text, keyboard = await render_admin_purchases_page(session, 0)
    await show_screen(callback, text, keyboard)
    await callback.answer()


@router.callback_query(AdminCB.filter(F.action == "purchases"))
async def paginate_admin_purchases(
    callback: CallbackQuery,
    callback_data: AdminCB,
    session: AsyncSession,
    user: User,
) -> None:
    if not _is_admin(user):
        await callback.answer(ru.ADMIN_ONLY, show_alert=True)
        return
    text, keyboard = await render_admin_purchases_page(session, callback_data.page)
    await show_screen(callback, text, keyboard)
    await callback.answer()
