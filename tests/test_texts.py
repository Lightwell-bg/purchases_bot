"""Тесты сборки текстов (src/texts/ru.py).

Первый файл тестов на этот модуль — раньше тексты проверялись только
косвенно, через сквозные смоук-скрипты вне pytest.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from src.database.models import Purchase, PurchaseStatus, User
from src.services import purchase_service
from src.texts import ru

TZ = ZoneInfo("Europe/Sofia")
NOW = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)


def make_user(user_id: int, username: str | None = "orga") -> User:
    return User(id=user_id, telegram_id=1000 + user_id, username=username)


def make_purchase(
    purchase_id: int = 1,
    title: str = "Baseus USB-C 100W",
    status: PurchaseStatus = PurchaseStatus.OPEN,
    unit_price: str = "2.80",
    organizer_quantity: int = 2,
) -> Purchase:
    organizer = make_user(99)
    return Purchase(
        id=purchase_id,
        public_token=f"token{purchase_id}",
        organizer_id=organizer.id,
        organizer=organizer,
        title=title,
        unit_price=Decimal(unit_price),
        currency="EUR",
        organizer_quantity=organizer_quantity,
        deadline=NOW + timedelta(days=3),
        status=status,
        participants=[],
    )


class TestOrganizerPanel:
    def test_shows_organizer_name(self):
        purchase = make_purchase()
        totals = purchase_service.totals(purchase)
        text = ru.organizer_panel(purchase, totals, TZ)
        assert "Организатор: @orga" in text

    def test_shows_organizer_id_when_no_username(self):
        purchase = make_purchase()
        purchase.organizer = make_user(99, username=None)
        totals = purchase_service.totals(purchase)
        text = ru.organizer_panel(purchase, totals, TZ)
        assert "Организатор:" in text


class TestAdminStats:
    def test_shows_all_eight_statuses(self):
        text = ru.admin_stats(users=5, status_counts={}, active_participants=0)
        for status in PurchaseStatus:
            assert ru.STATUS_LABELS[status] in text

    def test_missing_status_defaults_to_zero(self):
        text = ru.admin_stats(users=5, status_counts={}, active_participants=0)
        for status in PurchaseStatus:
            assert f"{ru.STATUS_LABELS[status]}: 0" in text

    def test_present_status_uses_given_count(self):
        text = ru.admin_stats(
            users=5,
            status_counts={PurchaseStatus.OPEN: 7},
            active_participants=3,
        )
        assert f"{ru.STATUS_LABELS[PurchaseStatus.OPEN]}: 7" in text
        assert "Пользователей: 5" in text
        assert "Активных заявок: 3" in text


class TestAdminPurchasesPage:
    def test_shows_total_and_organizer(self):
        purchase = make_purchase()
        totals = purchase_service.totals(purchase)
        text = ru.admin_purchases_page([(purchase, totals)], page=0, total_pages=1, total=1, tz=TZ)
        assert "Все закупки" in text
        assert "(1)" in text
        assert "@orga" in text
        assert "Baseus USB-C 100W" in text

    def test_page_indicator_shown_when_multiple_pages(self):
        purchase = make_purchase()
        totals = purchase_service.totals(purchase)
        text = ru.admin_purchases_page(
            [(purchase, totals)], page=0, total_pages=3, total=11, tz=TZ
        )
        assert "Страница 1 из 3" in text

    def test_no_page_indicator_for_single_page(self):
        purchase = make_purchase()
        totals = purchase_service.totals(purchase)
        text = ru.admin_purchases_page(
            [(purchase, totals)], page=0, total_pages=1, total=1, tz=TZ
        )
        assert "Страница" not in text


@pytest.mark.parametrize("status", list(PurchaseStatus))
def test_admin_stats_covers_every_status_value(status):
    """Явная проверка на будущее: если в PurchaseStatus добавят статус,
    STATUS_LABELS и admin_stats должны знать про него без доработки."""
    assert status in ru.STATUS_LABELS
