"""Глобальный обработчик ошибок.

Любое необработанное исключение внутри хендлера гасится здесь,
чтобы long polling продолжал работать.
"""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import CallbackQuery, ErrorEvent, Message

logger = logging.getLogger(__name__)

router = Router(name="errors")

USER_MESSAGE = "⚠️ Что-то пошло не так. Попробуйте ещё раз или нажмите /start."


@router.errors()
async def handle_error(event: ErrorEvent) -> bool:
    update = event.update
    exception = event.exception

    if isinstance(exception, TelegramForbiddenError):
        logger.info("Bot is blocked by user: %s", exception)
        return True

    logger.exception(
        "Unhandled error while processing update %s: %s",
        getattr(update, "update_id", "?"),
        exception,
    )

    target: Message | None = None
    if update.callback_query is not None:
        callback: CallbackQuery = update.callback_query
        try:
            await callback.answer(USER_MESSAGE, show_alert=True)
        except TelegramBadRequest:
            pass
        return True
    if update.message is not None:
        target = update.message

    if target is not None:
        try:
            await target.answer(USER_MESSAGE)
        except (TelegramBadRequest, TelegramForbiddenError):
            pass

    return True
