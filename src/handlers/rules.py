"""Экран правил и фиксация согласия."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import RulesAction, User
from src.database.repositories.purchases import PurchaseRepository
from src.handlers.common import show_main_menu, show_screen
from src.keyboards import inline
from src.keyboards.callbacks import RulesCB
from src.services import rules_service
from src.texts import ru

logger = logging.getLogger(__name__)

router = Router(name="rules")


async def ensure_rules(
    target: Message | CallbackQuery,
    session: AsyncSession,
    user: User,
    action: RulesAction,
    scope: str,
    token: str = "",
) -> bool:
    """True — согласие актуально. Иначе показывает экран правил."""
    if await rules_service.has_accepted(session, user, action):
        return True

    text = ru.rules_screen(
        rules_service.current_version(),
        joining=action == RulesAction.JOIN_PURCHASE,
    )
    keyboard = inline.rules_gate(scope, token)

    if isinstance(target, CallbackQuery):
        await show_screen(target, text, keyboard)
    else:
        await target.answer(text, reply_markup=keyboard)
    return False


@router.callback_query(RulesCB.filter(F.action == "read"))
async def read_rules(callback: CallbackQuery, callback_data: RulesCB) -> None:
    await show_screen(
        callback,
        ru.rules_full(),
        inline.rules_after_read(callback_data.scope, callback_data.token),
    )
    await callback.answer()


@router.callback_query(RulesCB.filter(F.action == "cancel"))
async def cancel_rules(callback: CallbackQuery, state: FSMContext) -> None:
    await show_main_menu(callback, state)
    await callback.answer()


@router.callback_query(RulesCB.filter(F.action == "accept"))
async def accept_rules(
    callback: CallbackQuery,
    callback_data: RulesCB,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    """Фиксируем согласие и возвращаем пользователя в прерванный сценарий."""
    # Импорты локальные: сценарии сами зависят от модуля правил.
    from src.handlers.create_purchase import start_wizard
    from src.handlers.join_purchase import start_join_form

    if callback_data.scope == "create":
        await rules_service.accept(session, user, RulesAction.CREATE_PURCHASE)
        await callback.answer(ru.RULES_ACCEPTED)
        await start_wizard(callback, state)
        return

    if callback_data.scope == "join":
        purchase = await PurchaseRepository(session).get_by_token(callback_data.token)
        if purchase is None:
            await show_screen(callback, ru.PURCHASE_NOT_FOUND, inline.back_to_menu())
            await callback.answer()
            return
        await rules_service.accept(session, user, RulesAction.JOIN_PURCHASE, purchase.id)
        await callback.answer(ru.RULES_ACCEPTED)
        await start_join_form(callback, state, session, user, purchase)
        return

    await show_main_menu(callback, state)
    await callback.answer()
