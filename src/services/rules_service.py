"""Согласие с правилами.

Согласие привязано к версии: подняли RULES_VERSION — все обязаны принять заново.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.database.models import RulesAction, User
from src.database.repositories.rules import RulesRepository

logger = logging.getLogger(__name__)


async def has_accepted(session: AsyncSession, user: User, action: RulesAction) -> bool:
    version = get_settings().rules_version
    return await RulesRepository(session).has_accepted(user.id, action, version)


async def accept(
    session: AsyncSession,
    user: User,
    action: RulesAction,
    purchase_id: int | None = None,
) -> None:
    version = get_settings().rules_version
    await RulesRepository(session).accept(user.id, action, version, purchase_id)
    logger.info(
        "Rules accepted user_tg=%s action=%s version=%s", user.telegram_id, action, version
    )


def current_version() -> str:
    return get_settings().rules_version
