"""Общие помощники хендлеров."""

from __future__ import annotations

import logging

from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from src.config import get_settings
from src.database.models import User
from src.keyboards import inline
from src.texts import ru

logger = logging.getLogger(__name__)


async def show_screen(
    callback: CallbackQuery,
    text: str,
    keyboard: InlineKeyboardMarkup | None = None,
) -> None:
    """Перерисовывает текущий экран.

    Сообщение с фото отредактировать текстом нельзя — в этом случае
    отправляем новое сообщение вместо правки.
    """
    message = callback.message
    if message is None:
        await callback.answer(ru.OUTDATED_CALLBACK, show_alert=True)
        return

    if message.photo or message.document or message.video:
        await message.answer(text, reply_markup=keyboard, disable_web_page_preview=True)
        return

    try:
        await message.edit_text(text, reply_markup=keyboard, disable_web_page_preview=True)
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc):
            return
        logger.debug("Cannot edit message, sending a new one: %s", exc)
        await message.answer(text, reply_markup=keyboard, disable_web_page_preview=True)


async def show_main_menu(target: Message | CallbackQuery, state: FSMContext, user: User) -> None:
    await state.clear()
    is_admin = get_settings().is_admin(user.telegram_id)
    if isinstance(target, CallbackQuery):
        await show_screen(target, ru.MAIN_MENU, inline.main_menu(is_admin))
    else:
        await target.answer(ru.MAIN_MENU, reply_markup=inline.main_menu(is_admin))


async def notify_outdated(callback: CallbackQuery, text: str = ru.OUTDATED_CALLBACK) -> None:
    """Ответ на нажатие кнопки под устаревшим сообщением."""
    await callback.answer(text, show_alert=True)
