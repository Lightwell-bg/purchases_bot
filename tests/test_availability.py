"""Тесты правил доступности закупки."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.database.models import PurchaseStatus
from src.services.availability import (
    UnavailableReason,
    can_join,
    can_manage,
    can_modify_participation,
    is_expired,
    join_block_reason,
)

NOW = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
FUTURE = NOW + timedelta(days=3)
PAST = NOW - timedelta(minutes=1)


class TestExpiry:
    def test_future_deadline_is_not_expired(self):
        assert is_expired(FUTURE, NOW) is False

    def test_past_deadline_is_expired(self):
        assert is_expired(PAST, NOW) is True

    def test_exact_deadline_is_expired(self):
        assert is_expired(NOW, NOW) is True


class TestJoinBlockReason:
    def test_open_and_in_time_is_joinable(self):
        assert join_block_reason(PurchaseStatus.OPEN, FUTURE, NOW) is None
        assert can_join(PurchaseStatus.OPEN, FUTURE, NOW) is True

    def test_expired_open_purchase(self):
        assert join_block_reason(PurchaseStatus.OPEN, PAST, NOW) is UnavailableReason.EXPIRED

    def test_closed_purchase(self):
        assert join_block_reason(PurchaseStatus.CLOSED, FUTURE, NOW) is UnavailableReason.CLOSED

    def test_cancelled_purchase(self):
        reason = join_block_reason(PurchaseStatus.CANCELLED, FUTURE, NOW)
        assert reason is UnavailableReason.CANCELLED

    def test_draft_is_not_published(self):
        reason = join_block_reason(PurchaseStatus.DRAFT, FUTURE, NOW)
        assert reason is UnavailableReason.NOT_PUBLISHED

    @pytest.mark.parametrize(
        "status",
        [
            PurchaseStatus.ORDERED,
            PurchaseStatus.SHIPPED,
            PurchaseStatus.RECEIVED,
            PurchaseStatus.COMPLETED,
        ],
    )
    def test_later_statuses_are_closed_for_joining(self, status):
        assert join_block_reason(status, FUTURE, NOW) is UnavailableReason.CLOSED

    def test_cancelled_wins_over_expired(self):
        reason = join_block_reason(PurchaseStatus.CANCELLED, PAST, NOW)
        assert reason is UnavailableReason.CANCELLED


class TestModification:
    def test_can_modify_while_open(self):
        assert can_modify_participation(PurchaseStatus.OPEN, FUTURE, NOW) is True

    def test_cannot_modify_after_close(self):
        assert can_modify_participation(PurchaseStatus.CLOSED, FUTURE, NOW) is False

    def test_cannot_modify_after_deadline(self):
        assert can_modify_participation(PurchaseStatus.OPEN, PAST, NOW) is False


class TestManage:
    def test_open_is_manageable(self):
        assert can_manage(PurchaseStatus.OPEN) is True

    def test_closed_is_manageable(self):
        assert can_manage(PurchaseStatus.CLOSED) is True

    def test_cancelled_is_final(self):
        assert can_manage(PurchaseStatus.CANCELLED) is False
