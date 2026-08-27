"""Хендлеры для группового чата.

Бот работает с включённым Privacy Mode: обычные сообщения он не видит
и не анализирует — только свои команды и свои сообщения.
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import Message

from src.config import get_settings
from src.database.models import User
from src.keyboards import inline
from src.texts import ru

logger = logging.getLogger(__name__)

router = Router(name="group")
router.message.filter(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))


@router.message(Command("buy"))
async def cmd_buy(message: Message) -> None:
    """Создание закупки всегда уходит в личку — в группе только редирект."""
    settings = get_settings()
    if not settings.bot_username:
        await message.reply("Напишите боту в личные сообщения, чтобы создать закупку.")
        return
    await message.reply(
        ru.GROUP_REDIRECT,
        reply_markup=inline.group_open_bot(settings.deep_link("create")),
    )


@router.message(Command("setup"))
async def cmd_setup(message: Message, user: User) -> None:
    """Публикует сообщение-приглашение, которое админ группы закрепляет."""
    settings = get_settings()
    if not settings.is_admin(user.telegram_id):
        await message.reply(ru.ADMIN_ONLY)
        return
    if not settings.bot_username:
        await message.reply("Не задан BOT_USERNAME — deep link не построить.")
        return

    await message.answer(
        ru.GROUP_PINNED,
        reply_markup=inline.group_create_link(settings.deep_link("create")),
    )
    logger.info("Setup message posted in chat=%s by tg=%s", message.chat.id, user.telegram_id)


@router.message(Command("chatid"))
async def cmd_chat_id(message: Message, user: User) -> None:
    """Помогает узнать MAIN_GROUP_ID при первичной настройке."""
    if not get_settings().is_admin(user.telegram_id):
        return
    await message.reply(f"ID этого чата: <code>{message.chat.id}</code>")
