"""Фоновая задача: автозакрытие закупок с истёкшим дедлайном.

Обычная asyncio-задача внутри процесса бота — для MVP этого достаточно,
внешний планировщик не нужен.
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot

from src.config import get_settings
from src.database.db import get_session_factory
from src.database.repositories.purchases import PurchaseRepository
from src.services import purchase_service, telegram_service
from src.texts import ru

logger = logging.getLogger(__name__)


async def close_expired_purchases(bot: Bot) -> int:
    """Один проход проверки. Возвращает количество закрытых закупок."""
    settings = get_settings()
    now = purchase_service.utcnow()
    closed = 0

    session_factory = get_session_factory()
    async with session_factory() as session:
        expired = await PurchaseRepository(session).list_expired_open(now)
        for purchase in expired:
            if not await purchase_service.close_purchase(session, purchase):
                continue
            recipients = await purchase_service.participant_telegram_ids(session, purchase)
            recipients.append(purchase.organizer.telegram_id)
            await telegram_service.refresh_announcement(bot, session, purchase)
            await session.commit()

            text = ru.deadline_autoclosed(purchase, purchase.deadline, settings.tz)
            await telegram_service.notify_users(bot, recipients, text)
            closed += 1
            logger.info("Purchase %s auto-closed by deadline", purchase.id)

    return closed


async def run_deadline_checker(bot: Bot) -> None:
    """Бесконечный цикл проверки. Ошибки не должны валить задачу."""
    # Нижняя граница защищает от пустого/нулевого значения в .env.
    interval = max(get_settings().deadline_check_interval_seconds, 60)
    logger.info("Deadline checker started, interval=%s s", interval)
    while True:
        try:
            await close_expired_purchases(bot)
        except asyncio.CancelledError:
            logger.info("Deadline checker stopped")
            raise
        except Exception:
            logger.exception("Deadline checker iteration failed")
        await asyncio.sleep(interval)
