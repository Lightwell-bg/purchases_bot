"""Просмотр списка всех активных закупок.

Доступен из личного меню (кнопка и команда `/active`) и из группы —
через постоянную reply-клавиатуру (см. handlers/group.py). Рендер вынесен
в отдельную функцию, чтобы группа и личка использовали один и тот же код.
"""

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
from src.database.models import PurchaseStatus
from src.database.repositories.purchases import PurchaseRepository
from src.handlers.common import show_screen
from src.keyboards import inline
from src.keyboards.callbacks import ListCB, MenuCB
from src.services import purchase_service
from src.texts import ru
from src.utils.pagination import paginate

logger = logging.getLogger(__name__)

router = Router(name="active_purchases")

PAGE_SIZE = 5


async def render_active_purchases_page(session: AsyncSession, page: int) -> tuple[str, Any]:
    """Собирает (текст, клавиатуру) для одной страницы списка."""
    settings = get_settings()
    repo = PurchaseRepository(session)

    total = await repo.count_by_status(PurchaseStatus.OPEN)
    if total == 0:
        return ru.ACTIVE_PURCHASES_EMPTY, inline.back_to_menu()

    page, total_pages = paginate(total, page, PAGE_SIZE)
    purchases = await repo.list_open(PAGE_SIZE, page * PAGE_SIZE)

    text = ru.active_purchases_page(
        [(p, purchase_service.totals(p)) for p in purchases],
        page,
        total_pages,
        total,
        settings.tz,
    )
    keyboard = inline.active_purchases(purchases, page, total_pages, settings.bot_username)
    return text, keyboard


async def show_active_purchases(
    target: Message | CallbackQuery, session: AsyncSession, page: int = 0
) -> None:
    text, keyboard = await render_active_purchases_page(session, page)
    if isinstance(target, CallbackQuery):
        await show_screen(target, text, keyboard)
    else:
        await target.answer(text, reply_markup=keyboard, disable_web_page_preview=True)


@router.message(Command("active"), F.chat.type == ChatType.PRIVATE)
async def cmd_active(message: Message, state: FSMContext, session: AsyncSession) -> None:
    await state.clear()
    await show_active_purchases(message, session)


@router.callback_query(MenuCB.filter(F.action == "active"))
async def menu_active(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await state.clear()
    await show_active_purchases(callback, session)
    await callback.answer()


@router.callback_query(ListCB.filter(F.action == "page"))
async def paginate_active(
    callback: CallbackQuery, callback_data: ListCB, session: AsyncSession
) -> None:
    await show_active_purchases(callback, session, callback_data.page)
    await callback.answer()
