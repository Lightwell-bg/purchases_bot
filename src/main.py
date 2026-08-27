"""Точка входа: миграции, запуск long polling и фоновой задачи."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramNetworkError, TelegramUnauthorizedError

from src.bot import create_bot, create_dispatcher
from src.config import BASE_DIR, get_settings
from src.database.db import dispose_engine
from src.logging_setup import setup_logging
from src.services.deadline_checker import close_expired_purchases, run_deadline_checker

logger = logging.getLogger(__name__)


def run_migrations() -> None:
    """Прогоняет alembic upgrade head синхронно, до старта polling."""
    from alembic import command
    from alembic.config import Config

    config = Config(str(BASE_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BASE_DIR / "migrations"))
    command.upgrade(config, "head")
    logger.info("Database migrations applied")


async def on_startup(bot: Bot) -> asyncio.Task:
    me = await bot.get_me()
    logger.info("Bot started as @%s (id=%s)", me.username, me.id)

    settings = get_settings()
    if settings.bot_username and settings.bot_username.lower() != (me.username or "").lower():
        logger.warning(
            "BOT_USERNAME=%s не совпадает с @%s — deep links будут нерабочими",
            settings.bot_username,
            me.username,
        )
    if not settings.bot_username:
        logger.warning("BOT_USERNAME не задан — deep links работать не будут")
    if not settings.main_group_id:
        logger.warning("MAIN_GROUP_ID не задан — публикация в группу недоступна")

    closed = await close_expired_purchases(bot)
    if closed:
        logger.info("Closed %s expired purchases on startup", closed)

    return asyncio.create_task(run_deadline_checker(bot), name="deadline-checker")


async def main() -> None:
    setup_logging()
    settings = get_settings()
    logger.info("Starting purchases bot, log level=%s", settings.log_level)

    if settings.run_migrations_on_start:
        await asyncio.to_thread(run_migrations)

    bot: Bot = create_bot()
    dp: Dispatcher = create_dispatcher()

    background: asyncio.Task | None = None
    try:
        background = await on_startup(bot)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except TelegramUnauthorizedError:
        # Самая частая ошибка первого запуска — не показываем стектрейс.
        logger.error("Telegram отклонил токен. Проверьте BOT_TOKEN в .env")
    except TelegramNetworkError as exc:
        logger.error("Нет связи с Telegram API: %s", exc)
    finally:
        if background is not None:
            background.cancel()
            try:
                await background
            except asyncio.CancelledError:
                pass
        await bot.session.close()
        await dispose_engine()
        logger.info("Bot stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.getLogger(__name__).info("Interrupted by user")
