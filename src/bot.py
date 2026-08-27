"""Сборка Bot и Dispatcher."""

from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
)

from src.config import get_settings
from src.handlers import register_routers
from src.middlewares.db import DbSessionMiddleware
from src.middlewares.user import UserMiddleware

logger = logging.getLogger(__name__)


# Список в синей кнопке «Меню» — главный способ для новичка понять,
# что боту вообще можно сказать.
PRIVATE_COMMANDS = [
    BotCommand(command="start", description="Главное меню"),
    BotCommand(command="buy", description="Создать совместную покупку"),
    BotCommand(command="active", description="Активные закупки"),
    BotCommand(command="my", description="Мои покупки"),
    BotCommand(command="cancel", description="Прервать текущий диалог"),
]

GROUP_COMMANDS = [
    BotCommand(command="help", description="Как работают совместные покупки"),
    BotCommand(command="buy", description="Создать совместную покупку"),
    BotCommand(command="active", description="Активные закупки"),
]


async def setup_bot_commands(bot: Bot) -> None:
    await bot.set_my_commands(PRIVATE_COMMANDS, scope=BotCommandScopeAllPrivateChats())
    await bot.set_my_commands(GROUP_COMMANDS, scope=BotCommandScopeAllGroupChats())
    logger.info("Bot command menu updated")


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
