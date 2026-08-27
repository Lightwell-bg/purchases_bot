"""Хендлеры для группового чата.

Бот рассчитан на Privacy Mode и не разбирает произвольный текст — реагирует
только на свои команды, служебные события о новых участниках, свои сообщения
и точное совпадение с текстом кнопки постоянной reply-клавиатуры (см.
persistent_keyboard). Последнее технически возможно потому, что бот состоит
администратором группы — права администратора уже нужны для редактирования и
удаления объявлений, и Telegram при этом доставляет боту вообще все сообщения
чата вне зависимости от Privacy Mode. Мы всё равно не читаем и не обрабатываем
ничего, кроме этого одного точного совпадения.

Служебная переписка (команды и ответы на них) удаляется через
GROUP_CLEANUP_SECONDS, чтобы не засорять ленту группы. В группе постоянно
живёт только закреплённое приглашение, объявления о закупках и сама
reply-клавиатура (она не «сообщение», а состояние поля ввода).
"""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

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

# Reply-клавиатура (не inline!): Telegram показывает её всем участникам
# группы рядом с полем ввода, независимо от того, какое сообщение они видят.
ACTIVE_BUTTON_TEXT = "📋 Активные закупки"


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


def persistent_keyboard() -> ReplyKeyboardMarkup:
    """Кнопка быстрого доступа к списку закупок у поля ввода.

    В отличие от inline-кнопок под конкретным сообщением, reply-клавиатура
    остаётся видна всем участникам группы независимо от того, какое
    сообщение они сейчас смотрят — ровно то, что нужно для «всегда под
    рукой». Держится, пока не будет заменена новой клавиатурой; удаление
    сообщения, которым она установлена, на неё не влияет.
    """
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=ACTIVE_BUTTON_TEXT)]],
        resize_keyboard=True,
        is_persistent=True,
    )


async def _arm_persistent_keyboard(message: Message, bot: Bot) -> None:
    """Устанавливает reply-клавиатуру отдельным сообщением.

    Нужно отдельное сообщение там, где основное уже занято inline-кнопками
    (у сообщения может быть только один тип reply_markup).
    """
    sent = await message.answer(ru.GROUP_KEYBOARD_ARMED, reply_markup=persistent_keyboard())
    delete_later(
        bot, message.chat.id, [sent.message_id], get_settings().business.group_cleanup_seconds
    )


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
        # Добавили самого бота — подсказываем администратору следующий шаг
        # и сразу же ставим постоянную клавиатуру.
        await _reply_and_cleanup(
            message,
            bot,
            ru.GROUP_BOT_ADDED,
            persistent_keyboard(),
            lifetime_factor=WELCOME_LIFETIME_FACTOR,
        )
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
    # Пинned-сообщение уже занято inline-кнопкой — клавиатуру ставим отдельным сообщением.
    await _arm_persistent_keyboard(message, bot)
    logger.info("Setup message posted in chat=%s by tg=%s", message.chat.id, user.telegram_id)


async def _show_active_purchases(message: Message, bot: Bot, session: AsyncSession) -> None:
    from src.handlers.active_purchases import render_active_purchases_page

    text, keyboard = await render_active_purchases_page(session, 0)
    await _reply_and_cleanup(message, bot, text, keyboard)


@router.message(Command("active"))
async def cmd_active(message: Message, bot: Bot, session: AsyncSession) -> None:
    await _show_active_purchases(message, bot, session)


@router.message(F.text == ACTIVE_BUTTON_TEXT)
async def group_active_button(message: Message, bot: Bot, session: AsyncSession) -> None:
    """Нажатие reply-кнопки — обычное текстовое сообщение от пользователя.

    Бот получает его несмотря на Privacy Mode: администраторы группы видят
    все сообщения, а права администратора боту уже нужны для редактирования
    и удаления объявлений.
    """
    await _show_active_purchases(message, bot, session)


@router.message(Command("chatid"))
async def cmd_chat_id(message: Message, bot: Bot, user: User) -> None:
    """Помогает узнать MAIN_GROUP_ID при первичной настройке."""
    if not get_settings().is_admin(user.telegram_id):
        return
    await _reply_and_cleanup(message, bot, f"ID этого чата: <code>{message.chat.id}</code>")
