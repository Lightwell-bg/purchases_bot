"""Сборка Bot и Dispatcher."""

from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from src.config import get_settings
from src.handlers import register_routers
from src.middlewares.db import DbSessionMiddleware
from src.middlewares.user import UserMiddleware

logger = logging.getLogger(__name__)


def create_bot() -> Bot:
    settings = get_settings()
    return Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher() -> Dispatcher:
    """FSM держим в памяти: диалог короткий, переживать рестарт ему не нужно."""
    dp = Dispatcher(storage=MemoryStorage())

    for observer in (dp.message, dp.callback_query, dp.my_chat_member):
        observer.middleware(DbSessionMiddleware())
        observer.middleware(UserMiddleware())

    register_routers(dp)
    logger.info("Dispatcher configured")
    return dp
