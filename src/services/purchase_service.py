"""Бизнес-логика закупок: создание, участие, пересчёты, смена статусов.

Хендлеры вызывают эти функции и не трогают ORM напрямую.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.database.models import (
    Participant,
    ParticipantStatus,
    Purchase,
    PurchaseStatus,
    User,
)
from src.database.repositories.participants import ParticipantRepository
from src.database.repositories.purchases import PurchaseRepository
from src.services.calculations import (
    LimitCheck,
    PurchaseTotals,
    calculate_total_value,
    calculate_totals,
    check_limit,
)

logger = logging.getLogger(__name__)


class PurchaseError(Exception):
    """Ошибка бизнес-правила, текст которой можно показать пользователю."""


@dataclass(frozen=True)
class JoinResult:
    participant: Participant
    created: bool


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def totals(purchase: Purchase) -> PurchaseTotals:
    """Все агрегаты закупки по текущим активным заявкам."""
    business = get_settings().business
    return calculate_totals(
        unit_price=purchase.unit_price,
        organizer_quantity=purchase.organizer_quantity,
        participant_quantities=[p.quantity for p in purchase.active_participants],
        customs_flat_fee=business.customs_flat_fee_eur,
        limit=business.purchase_limit_eur,
    )


def _value_without_user(purchase: Purchase, user_id: int | None) -> Decimal:
    """Сумма закупки без заявки конкретного пользователя.

    Нужна при изменении заявки: иначе собственный вклад учитывался бы дважды.
    """
    quantity = purchase.organizer_quantity + sum(
        p.quantity for p in purchase.active_participants if p.user_id != user_id
    )
    return calculate_total_value(purchase.unit_price, quantity)


def check_participant_limit(purchase: Purchase, user_id: int, quantity: int) -> LimitCheck:
    business = get_settings().business
    return check_limit(
        unit_price=purchase.unit_price,
        total_without_request=_value_without_user(purchase, user_id),
        requested_quantity=quantity,
        limit=business.purchase_limit_eur,
    )


def check_organizer_quantity_limit(purchase: Purchase, quantity: int) -> LimitCheck:
    """Количество организатора тоже обязано влезать в лимит."""
    business = get_settings().business
    participants_value = calculate_total_value(
        purchase.unit_price, sum(p.quantity for p in purchase.active_participants)
    )
    return check_limit(
        unit_price=purchase.unit_price,
        total_without_request=participants_value,
        requested_quantity=quantity,
        limit=business.purchase_limit_eur,
    )


def check_draft_limit(unit_price: Decimal, quantity: int) -> LimitCheck:
    """Проверка на этапе мастера, когда закупки в базе ещё нет."""
    business = get_settings().business
    return check_limit(
        unit_price=unit_price,
        total_without_request=Decimal("0"),
        requested_quantity=quantity,
        limit=business.purchase_limit_eur,
    )


async def create_purchase(
    session: AsyncSession,
    organizer: User,
    data: Mapping[str, Any],
) -> Purchase:
    """Создаёт черновик закупки. Публикацией занимается telegram_service."""
    repo = PurchaseRepository(session)
    purchase = Purchase(
        public_token=await repo.new_token(),
        organizer_id=organizer.id,
        organizer=organizer,
        title=data["title"],
        product_url=data.get("product_url"),
        description=data.get("description"),
        variant_description=data.get("variant_description"),
        unit_price=data["unit_price"],
        currency=data["currency"],
        organizer_quantity=data["organizer_quantity"],
        deadline=data["deadline"],
        pickup_location=data.get("pickup_location"),
        photo_file_id=data.get("photo_file_id"),
        status=PurchaseStatus.DRAFT,
        # Инициализируем коллекцию явно: иначе после flush обращение к ней
        # вызовет ленивую загрузку, недопустимую в async-контексте.
        participants=[],
    )
    await repo.add(purchase)
    logger.info(
        "Purchase draft created id=%s organizer_tg=%s", purchase.id, organizer.telegram_id
    )
    return purchase


async def join_purchase(
    session: AsyncSession,
    purchase: Purchase,
    user: User,
    quantity: int,
    variant: str | None,
    comment: str | None,
) -> JoinResult:
    """Добавляет или восстанавливает заявку участника с проверкой лимита."""
    check = check_participant_limit(purchase, user.id, quantity)
    if not check.allowed:
        raise PurchaseError("limit")

    repo = ParticipantRepository(session)
    participant = await repo.get_for_user(purchase.id, user.id)
    created = participant is None

    if participant is None:
        participant = Participant(
            purchase_id=purchase.id,
            user_id=user.id,
            user=user,
            quantity=quantity,
            variant=variant,
            comment=comment,
            status=ParticipantStatus.ACTIVE,
        )
        purchase.participants.append(participant)
        await session.flush()
    else:
        participant.quantity = quantity
        participant.variant = variant
        participant.comment = comment
        participant.status = ParticipantStatus.ACTIVE
        await session.flush()

    logger.info(
        "Participant joined purchase=%s user_tg=%s qty=%s new=%s",
        purchase.id,
        user.telegram_id,
        quantity,
        created,
    )
    return JoinResult(participant=participant, created=created)


async def update_participation(
    session: AsyncSession,
    purchase: Purchase,
    participant: Participant,
    *,
    quantity: int | None = None,
    variant: str | None = None,
    comment: str | None = None,
) -> Participant:
    """Меняет одно поле заявки. Количество проверяется по лимиту."""
    if quantity is not None:
        check = check_participant_limit(purchase, participant.user_id, quantity)
        if not check.allowed:
            raise PurchaseError("limit")
        participant.quantity = quantity
    if variant is not None:
        participant.variant = variant or None
    if comment is not None:
        participant.comment = comment or None

    await session.flush()
    logger.info(
        "Participation updated purchase=%s participant=%s", purchase.id, participant.id
    )
    return participant


async def leave_purchase(
    session: AsyncSession,
    purchase: Purchase,
    participant: Participant,
) -> None:
    """Мягкий отказ: строку не удаляем, чтобы сохранить историю согласий."""
    participant.status = ParticipantStatus.CANCELLED
    await session.flush()
    logger.info("Participant left purchase=%s participant=%s", purchase.id, participant.id)


async def close_purchase(session: AsyncSession, purchase: Purchase) -> bool:
    """Переводит закупку в CLOSED. False — если она уже была не открыта."""
    if purchase.status != PurchaseStatus.OPEN:
        return False
    purchase.status = PurchaseStatus.CLOSED
    await session.flush()
    logger.info("Purchase closed id=%s", purchase.id)
    return True


async def cancel_purchase(session: AsyncSession, purchase: Purchase) -> bool:
    if purchase.status in (PurchaseStatus.CANCELLED, PurchaseStatus.COMPLETED):
        return False
    purchase.status = PurchaseStatus.CANCELLED
    await session.flush()
    logger.info("Purchase cancelled id=%s", purchase.id)
    return True


async def participant_telegram_ids(session: AsyncSession, purchase: Purchase) -> list[int]:
    """Кому рассылать уведомления по закупке (без организатора)."""
    repo = ParticipantRepository(session)
    participants = await repo.list_active(purchase.id)
    return [p.user.telegram_id for p in participants]


def is_organizer(purchase: Purchase, user: User) -> bool:
    return purchase.organizer_id == user.id
