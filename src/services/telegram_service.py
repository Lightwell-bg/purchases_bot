"""Всё общение с Telegram API, кроме самих хендлеров.

Здесь же — единая обработка «ожидаемых» ошибок Telegram: заблокированный бот,
удалённое сообщение, флуд-лимит. Наружу они не пробрасываются, чтобы
не ронять обработку апдейта.
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from aiogram.types import InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.database.models import Purchase, PurchaseStatus
from src.keyboards import inline
from src.services import purchase_service
from src.texts import ru

logger = logging.getLogger(__name__)

# Пауза между сообщениями при массовой рассылке — бережём лимиты Telegram.
BROADCAST_DELAY = 0.05

NOT_MODIFIED = "message is not modified"
MESSAGE_GONE = ("message to edit not found", "message can't be edited", "MESSAGE_ID_INVALID")


def announcement_keyboard(purchase: Purchase) -> InlineKeyboardMarkup:
    settings = get_settings()
    joinable = purchase.status == PurchaseStatus.OPEN
    return inline.announcement(
        join_link=settings.deep_link(f"join_{purchase.public_token}"),
        rules_link=settings.deep_link("rules"),
        joinable=joinable,
    )


async def publish_purchase(bot: Bot, session: AsyncSession, purchase: Purchase) -> bool:
    """Публикует объявление в группе и переводит закупку в OPEN."""
    settings = get_settings()
    if not settings.main_group_id:
        logger.error("MAIN_GROUP_ID is not configured, cannot publish purchase %s", purchase.id)
        return False

    text = ru.group_announcement(purchase, purchase_service.totals(purchase), settings.tz)
    keyboard = announcement_keyboard(purchase)

    try:
        if purchase.photo_file_id:
            message = await bot.send_photo(
                chat_id=settings.main_group_id,
                photo=purchase.photo_file_id,
                caption=text,
                reply_markup=keyboard,
            )
        else:
            message = await bot.send_message(
                chat_id=settings.main_group_id,
                text=text,
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        logger.error("Failed to publish purchase %s: %s", purchase.id, exc)
        return False

    purchase.group_chat_id = message.chat.id
    purchase.group_message_id = message.message_id
    purchase.status = PurchaseStatus.OPEN
    await session.flush()

    logger.info(
        "Purchase published id=%s chat=%s message=%s",
        purchase.id,
        message.chat.id,
        message.message_id,
    )
    return True


async def refresh_announcement(bot: Bot, session: AsyncSession, purchase: Purchase) -> bool:
    """Перерисовывает объявление в группе после любого изменения закупки."""
    if not purchase.group_chat_id or not purchase.group_message_id:
        return False

    settings = get_settings()
    text = ru.group_announcement(purchase, purchase_service.totals(purchase), settings.tz)
    keyboard = announcement_keyboard(purchase)

    try:
        if purchase.photo_file_id:
            await bot.edit_message_caption(
                chat_id=purchase.group_chat_id,
                message_id=purchase.group_message_id,
                caption=text,
                reply_markup=keyboard,
            )
        else:
            await bot.edit_message_text(
                chat_id=purchase.group_chat_id,
                message_id=purchase.group_message_id,
                text=text,
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
        return True
    except TelegramRetryAfter as exc:
        logger.warning("Flood limit while refreshing purchase %s: retry after %s", purchase.id, exc.retry_after)
        return False
    except TelegramBadRequest as exc:
        message = str(exc)
        if NOT_MODIFIED in message:
            return True
        if any(marker in message for marker in MESSAGE_GONE):
            logger.warning("Group message for purchase %s is gone, detaching", purchase.id)
            purchase.group_message_id = None
            await session.flush()
            return False
        logger.error("Failed to refresh purchase %s: %s", purchase.id, message)
        return False
    except TelegramForbiddenError as exc:
        logger.error("Bot lost access to group for purchase %s: %s", purchase.id, exc)
        return False


async def notify_users(bot: Bot, telegram_ids: list[int], text: str) -> int:
    """Личная рассылка. Возвращает число доставленных сообщений."""
    delivered = 0
    for telegram_id in telegram_ids:
        try:
            await bot.send_message(telegram_id, text, disable_web_page_preview=True)
            delivered += 1
        except TelegramForbiddenError:
            logger.info("User %s blocked the bot, notification skipped", telegram_id)
        except TelegramRetryAfter as exc:
            logger.warning("Flood limit on broadcast, sleeping %s s", exc.retry_after)
            await asyncio.sleep(exc.retry_after)
        except TelegramBadRequest as exc:
            logger.warning("Cannot notify user %s: %s", telegram_id, exc)
        await asyncio.sleep(BROADCAST_DELAY)
    return delivered


async def send_purchase_card(
    message: Message,
    purchase: Purchase,
    text: str,
    keyboard: InlineKeyboardMarkup | None = None,
) -> None:
    """Карточка закупки в личке: с фото, если оно есть."""
    if purchase.photo_file_id:
        await message.answer_photo(
            photo=purchase.photo_file_id, caption=text, reply_markup=keyboard
        )
    else:
        await message.answer(text, reply_markup=keyboard, disable_web_page_preview=True)
