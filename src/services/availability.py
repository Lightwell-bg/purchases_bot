"""Правила доступности закупки: можно ли присоединиться / менять заявку.

Чистые функции без базы — легко тестировать и переиспользовать
и в хендлерах, и в фоновом чекере дедлайнов.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from src.database.models import PurchaseStatus

# Статусы, при которых организатор ещё принимает заявки.
JOINABLE_STATUSES = frozenset({PurchaseStatus.OPEN})

# Статусы, в которых закупку показываем как «идёт», но заявки уже закрыты.
FINAL_STATUSES = frozenset({PurchaseStatus.CANCELLED, PurchaseStatus.COMPLETED})


class UnavailableReason(StrEnum):
    NOT_PUBLISHED = "NOT_PUBLISHED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


def is_expired(deadline: datetime, now: datetime) -> bool:
    return deadline <= now


def join_block_reason(
    status: PurchaseStatus,
    deadline: datetime,
    now: datetime,
) -> UnavailableReason | None:
    """Возвращает причину, по которой присоединиться нельзя, либо None."""
    if status == PurchaseStatus.CANCELLED:
        return UnavailableReason.CANCELLED
    if status == PurchaseStatus.DRAFT:
        return UnavailableReason.NOT_PUBLISHED
    if status not in JOINABLE_STATUSES:
        return UnavailableReason.CLOSED
    if is_expired(deadline, now):
        return UnavailableReason.EXPIRED
    return None


def can_join(status: PurchaseStatus, deadline: datetime, now: datetime) -> bool:
    return join_block_reason(status, deadline, now) is None


def can_modify_participation(status: PurchaseStatus, deadline: datetime, now: datetime) -> bool:
    """Менять и отзывать заявку можно ровно пока идёт сбор."""
    return can_join(status, deadline, now)


def can_manage(status: PurchaseStatus) -> bool:
    """Организатор может управлять закупкой, пока она не в финальном статусе."""
    return status not in FINAL_STATUSES
