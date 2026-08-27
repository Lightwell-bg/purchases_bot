"""Тесты бизнес-правил закупки на ORM-объектах без базы."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from src.database.models import Participant, ParticipantStatus, Purchase, PurchaseStatus, User
from src.services import purchase_service

NOW = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)


def make_user(user_id: int) -> User:
    return User(id=user_id, telegram_id=1000 + user_id, username=f"user{user_id}")


def make_participant(user_id: int, quantity: int, active: bool = True) -> Participant:
    return Participant(
        id=user_id,
        purchase_id=1,
        user_id=user_id,
        user=make_user(user_id),
        quantity=quantity,
        status=ParticipantStatus.ACTIVE if active else ParticipantStatus.CANCELLED,
    )


def make_purchase(
    unit_price: str = "2.80",
    organizer_quantity: int = 2,
    participants: list[Participant] | None = None,
) -> Purchase:
    organizer = make_user(99)
    return Purchase(
        id=1,
        public_token="token",
        organizer_id=organizer.id,
        organizer=organizer,
        title="Baseus USB-C 100W",
        unit_price=Decimal(unit_price),
        currency="EUR",
        organizer_quantity=organizer_quantity,
        deadline=NOW + timedelta(days=3),
        status=PurchaseStatus.OPEN,
        participants=participants or [],
    )


class TestTotals:
    def test_counts_organizer_and_participants(self):
        purchase = make_purchase(participants=[make_participant(1, 3), make_participant(2, 1)])
        totals = purchase_service.totals(purchase)
        assert totals.total_quantity == 6
        assert totals.total_value == Decimal("16.80")
        assert totals.participants_count == 3

    def test_ignores_cancelled_participants(self):
        purchase = make_purchase(
            organizer_quantity=0,
            participants=[make_participant(1, 3), make_participant(2, 5, active=False)],
        )
        totals = purchase_service.totals(purchase)
        assert totals.total_quantity == 3
        assert totals.participants_count == 1


class TestParticipantLimit:
    def test_new_participant_within_limit(self):
        purchase = make_purchase(unit_price="10", organizer_quantity=1)
        check = purchase_service.check_participant_limit(purchase, user_id=1, quantity=5)
        assert check.allowed is True
        assert check.projected_total == Decimal("60.00")

    def test_new_participant_over_limit(self):
        purchase = make_purchase(
            unit_price="10", organizer_quantity=0, participants=[make_participant(1, 14)]
        )
        check = purchase_service.check_participant_limit(purchase, user_id=2, quantity=2)
        assert check.allowed is False
        assert check.projected_total == Decimal("160.00")
        assert check.max_quantity == 1

    def test_existing_participant_contribution_is_excluded(self):
        """Участник с 14 шт. должен мочь уменьшить заявку, а не упереться в лимит."""
        purchase = make_purchase(
            unit_price="10", organizer_quantity=0, participants=[make_participant(1, 14)]
        )
        check = purchase_service.check_participant_limit(purchase, user_id=1, quantity=15)
        assert check.allowed is True
        assert check.projected_total == Decimal("150.00")

    def test_exact_limit_allowed(self):
        purchase = make_purchase(unit_price="10", organizer_quantity=0)
        check = purchase_service.check_participant_limit(purchase, user_id=1, quantity=15)
        assert check.allowed is True


class TestOrganizerLimit:
    def test_organizer_quantity_limited_by_participants(self):
        purchase = make_purchase(
            unit_price="10", organizer_quantity=1, participants=[make_participant(1, 14)]
        )
        check = purchase_service.check_organizer_quantity_limit(purchase, quantity=2)
        assert check.allowed is False
        assert check.max_quantity == 1

    def test_draft_limit_uses_empty_purchase(self):
        check = purchase_service.check_draft_limit(Decimal("10"), 16)
        assert check.allowed is False
        assert check.max_quantity == 15


class TestOwnership:
    def test_organizer_detected(self):
        purchase = make_purchase()
        assert purchase_service.is_organizer(purchase, make_user(99)) is True

    def test_other_user_is_not_organizer(self):
        purchase = make_purchase()
        assert purchase_service.is_organizer(purchase, make_user(1)) is False


@pytest.mark.parametrize(("price", "quantity"), [("0.01", 15000), ("150", 1)])
def test_limit_boundary_is_inclusive(price, quantity):
    check = purchase_service.check_draft_limit(Decimal(price), quantity)
    assert check.allowed is True
    assert check.projected_total == Decimal("150.00")
