"""Работа с закупками."""

from __future__ import annotations

import secrets
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Participant, ParticipantStatus, Purchase, PurchaseStatus

TOKEN_BYTES = 9  # 12 символов base64url — непредсказуемо и влезает в callback_data


def generate_public_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


class PurchaseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, purchase: Purchase) -> Purchase:
        self.session.add(purchase)
        await self.session.flush()
        return purchase

    async def get(self, purchase_id: int) -> Purchase | None:
        # Через select(), чтобы гарантированно отработали selectin-загрузчики связей.
        result = await self.session.execute(select(Purchase).where(Purchase.id == purchase_id))
        return result.scalar_one_or_none()

    async def get_by_token(self, token: str) -> Purchase | None:
        result = await self.session.execute(
            select(Purchase).where(Purchase.public_token == token)
        )
        return result.scalar_one_or_none()

    async def new_token(self) -> str:
        """Генерирует токен, которого точно нет в базе."""
        for _ in range(10):
            token = generate_public_token()
            if await self.get_by_token(token) is None:
                return token
        raise RuntimeError("Не удалось сгенерировать уникальный public_token")

    async def list_organized(self, user_id: int, limit: int = 20) -> list[Purchase]:
        result = await self.session.execute(
            select(Purchase)
            .where(
                Purchase.organizer_id == user_id,
                Purchase.status != PurchaseStatus.DRAFT,
            )
            .order_by(Purchase.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_joined(self, user_id: int, limit: int = 20) -> list[Purchase]:
        result = await self.session.execute(
            select(Purchase)
            .join(Participant, Participant.purchase_id == Purchase.id)
            .where(
                Participant.user_id == user_id,
                Participant.status == ParticipantStatus.ACTIVE,
            )
            .order_by(Purchase.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().unique().all())

    async def list_expired_open(self, now: datetime) -> list[Purchase]:
        result = await self.session.execute(
            select(Purchase).where(
                Purchase.status == PurchaseStatus.OPEN,
                Purchase.deadline < now,
            )
        )
        return list(result.scalars().all())

    async def list_recent(self, limit: int = 10) -> list[Purchase]:
        result = await self.session.execute(
            select(Purchase)
            .where(Purchase.status != PurchaseStatus.DRAFT)
            .order_by(Purchase.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_by_status(self, status: PurchaseStatus) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(Purchase).where(Purchase.status == status)
        )
        return int(result.scalar_one())
