"""Точка входа в личный чат: /start, deep links и главное меню."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import RulesAction, User
from src.handlers.common import show_main_menu, show_screen
from src.keyboards import inline
from src.keyboards.callbacks import MenuCB
from src.texts import ru

logger = logging.getLogger(__name__)

router = Router(name="start")
router.message.filter(F.chat.type == ChatType.PRIVATE)

JOIN_PREFIX = "join_"


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    command: CommandObject,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    """Разбирает payload deep link и направляет в нужный сценарий."""
    from src.handlers.create_purchase import start_wizard
    from src.handlers.join_purchase import join_entry
    from src.handlers.rules import ensure_rules

    await state.clear()
    payload = (command.args or "").strip()
    logger.info("Start command from tg=%s payload=%r", user.telegram_id, payload)

    if not payload:
        await show_main_menu(message, state)
        return

    if payload == "create":
        if await ensure_rules(message, session, user, RulesAction.CREATE_PURCHASE, "create"):
            await start_wizard(message, state)
        return

    if payload == "rules":
        await message.answer(ru.rules_full(), reply_markup=inline.back_to_menu())
        return

    if payload.startswith(JOIN_PREFIX):
        token = payload[len(JOIN_PREFIX):]
        if token:
            await join_entry(message, state, session, user, token)
            return

    await message.answer(ru.BAD_DEEP_LINK, reply_markup=inline.main_menu())


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext) -> None:
    await show_main_menu(message, state)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(ru.CANCELLED, reply_markup=inline.main_menu())


@router.callback_query(MenuCB.filter(F.action == "main"))
async def menu_main(callback: CallbackQuery, state: FSMContext) -> None:
    await show_main_menu(callback, state)
    await callback.answer()


@router.callback_query(MenuCB.filter(F.action == "rules"))
async def menu_rules(callback: CallbackQuery) -> None:
    await show_screen(callback, ru.rules_full(), inline.rules_after_read("info"))
    await callback.answer()


@router.callback_query(MenuCB.filter(F.action == "create"))
async def menu_create(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    from src.handlers.create_purchase import start_wizard
    from src.handlers.rules import ensure_rules

    await state.clear()
    await callback.answer()
    if await ensure_rules(callback, session, user, RulesAction.CREATE_PURCHASE, "create"):
        await start_wizard(callback, state)


@router.callback_query(MenuCB.filter(F.action == "my"))
async def menu_my(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    from src.handlers.my_purchases import show_my_purchases

    await state.clear()
    await show_my_purchases(callback, session, user)
    await callback.answer()
