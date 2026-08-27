"""Регистрация пользователя из апдейта."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User as TgUser

from src.database.repositories.users import UserRepository


class UserMiddleware(BaseMiddleware):
    """Кладёт в data актуальную запись User из нашей базы.

    Работает только для апдейтов с автором и только вместе с DbSessionMiddleware.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user: TgUser | None = data.get("event_from_user")
        session = data.get("session")

        if tg_user is not None and not tg_user.is_bot and session is not None:
            data["user"] = await UserRepository(session).upsert(
                telegram_id=tg_user.id,
                username=tg_user.username,
                first_name=tg_user.first_name,
                last_name=tg_user.last_name,
            )

        return await handler(event, data)
