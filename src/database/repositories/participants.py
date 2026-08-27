"""Работа с участниками закупки."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Participant, ParticipantStatus


class ParticipantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, participant_id: int) -> Participant | None:
        result = await self.session.execute(
            select(Participant).where(Participant.id == participant_id)
        )
        return result.scalar_one_or_none()

    async def get_for_user(self, purchase_id: int, user_id: int) -> Participant | None:
        """Любая запись участия, включая отменённую (constraint уникален по паре)."""
        result = await self.session.execute(
            select(Participant).where(
                Participant.purchase_id == purchase_id,
                Participant.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_active(self, purchase_id: int) -> list[Participant]:
        result = await self.session.execute(
            select(Participant)
            .where(
                Participant.purchase_id == purchase_id,
                Participant.status == ParticipantStatus.ACTIVE,
            )
            .order_by(Participant.created_at)
        )
        return list(result.scalars().all())

    async def add(self, participant: Participant) -> Participant:
        self.session.add(participant)
        await self.session.flush()
        return participant

    async def count_active(self) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(Participant)
            .where(Participant.status == ParticipantStatus.ACTIVE)
        )
        return int(result.scalar_one())
