"""Работа с согласиями на правила."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import RulesAcceptance, RulesAction


class RulesRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def has_accepted(self, user_id: int, action: RulesAction, version: str) -> bool:
        result = await self.session.execute(
            select(RulesAcceptance.id)
            .where(
                RulesAcceptance.user_id == user_id,
                RulesAcceptance.action == action,
                RulesAcceptance.rules_version == version,
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def accept(
        self,
        user_id: int,
        action: RulesAction,
        version: str,
        purchase_id: int | None = None,
    ) -> RulesAcceptance:
        acceptance = RulesAcceptance(
            user_id=user_id,
            action=action,
            rules_version=version,
            purchase_id=purchase_id,
        )
        self.session.add(acceptance)
        await self.session.flush()
        return acceptance
