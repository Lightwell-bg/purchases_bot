"""Хендлеры для группового чата.

Бот работает с включённым Privacy Mode: обычные сообщения он не видит
и не анализирует — только свои команды, служебные события о новых участниках
и свои сообщения.

Служебная переписка (команды и ответы на них) удаляется через
GROUP_CLEANUP_SECONDS, чтобы не засорять ленту группы. В группе постоянно
живёт только закреплённое приглашение и сами объявления о закупках.
"""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import Message

from src.config import get_settings
from src.database.models import User
from src.keyboards import inline
from src.services.telegram_service import delete_later
from src.texts import ru

logger = logging.getLogger(__name__)

router = Router(name="group")
router.message.filter(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))

# Приветствие новичку живёт дольше обычного ответа: человек может
# открыть Telegram не сразу.
WELCOME_LIFETIME_FACTOR = 10


async def _reply_and_cleanup(
    message: Message,
    bot: Bot,
    text: str,
    keyboard=None,
    lifetime_factor: int = 1,
) -> None:
    """Отвечает в группе и планирует уборку своего ответа вместе с командой."""
    sent = await message.answer(text, reply_markup=keyboard)
    delay = get_settings().business.group_cleanup_seconds * lifetime_factor
    delete_later(bot, message.chat.id, [message.message_id, sent.message_id], delay)


@router.message(Command("buy"))
async def cmd_buy(message: Message, bot: Bot) -> None:
    """Создание закупки всегда уходит в личку — в группе только редирект."""
    settings = get_settings()
    if not settings.bot_username:
        await _reply_and_cleanup(
            message, bot, "Напишите боту в личные сообщения, чтобы создать закупку."
        )
        return
    await _reply_and_cleanup(
        message,
        bot,
        ru.GROUP_REDIRECT,
        inline.group_open_bot(settings.deep_link("create")),
    )


@router.message(Command("help"))
async def cmd_help(message: Message, bot: Bot) -> None:
    """Короткая инструкция для тех, кто не понял, с чего начать."""
    settings = get_settings()
    keyboard = (
        inline.group_create_link(settings.deep_link("create"))
        if settings.bot_username
        else None
    )
    await _reply_and_cleanup(message, bot, ru.GROUP_HELP, keyboard)


@router.message(F.new_chat_members)
async def on_new_members(message: Message, bot: Bot) -> None:
    """Онбординг: новичок не листает историю и не видит закреп сразу."""
    settings = get_settings()
    me = await bot.me()

    if any(member.id == me.id for member in message.new_chat_members or []):
        # Добавили самого бота — подсказываем администратору следующий шаг.
        await _reply_and_cleanup(message, bot, ru.GROUP_BOT_ADDED, lifetime_factor=WELCOME_LIFETIME_FACTOR)
        return

    if all(member.is_bot for member in message.new_chat_members or []):
        return
    if not settings.bot_username:
        return

    await _reply_and_cleanup(
        message,
        bot,
        ru.GROUP_WELCOME,
        inline.group_create_link(settings.deep_link("create")),
        lifetime_factor=WELCOME_LIFETIME_FACTOR,
    )


@router.message(Command("setup"))
async def cmd_setup(message: Message, bot: Bot, user: User) -> None:
    """Публикует сообщение-приглашение, которое админ группы закрепляет."""
    settings = get_settings()
    if not settings.is_admin(user.telegram_id):
        await _reply_and_cleanup(message, bot, ru.ADMIN_ONLY)
        return
    if not settings.bot_username:
        await _reply_and_cleanup(message, bot, "Не задан BOT_USERNAME — deep link не построить.")
        return

    await message.answer(
        ru.GROUP_PINNED,
        reply_markup=inline.group_create_link(settings.deep_link("create")),
    )
    # Приглашение остаётся навсегда, а команда админа — нет.
    delete_later(
        bot, message.chat.id, [message.message_id], settings.business.group_cleanup_seconds
    )
    logger.info("Setup message posted in chat=%s by tg=%s", message.chat.id, user.telegram_id)


@router.message(Command("chatid"))
async def cmd_chat_id(message: Message, bot: Bot, user: User) -> None:
    """Помогает узнать MAIN_GROUP_ID при первичной настройке."""
    if not get_settings().is_admin(user.telegram_id):
        return
    await _reply_and_cleanup(message, bot, f"ID этого чата: <code>{message.chat.id}</code>")
