"""Тесты денежных расчётов."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.services.calculations import (
    calculate_total_quantity,
    calculate_total_value,
    calculate_totals,
    check_limit,
    estimated_fee_per_item,
    max_additional_quantity,
    money,
)

FEE = Decimal("3")
LIMIT = Decimal("150")


class TestTotalQuantity:
    def test_includes_organizer(self):
        assert calculate_total_quantity(2, [1, 3, 4]) == 10

    def test_no_participants(self):
        assert calculate_total_quantity(5, []) == 5

    def test_organizer_takes_nothing(self):
        assert calculate_total_quantity(0, [2, 2]) == 4


class TestTotalValue:
    def test_basic(self):
        assert calculate_total_value(Decimal("2.80"), 18) == Decimal("50.40")

    def test_zero_quantity(self):
        assert calculate_total_value(Decimal("2.80"), 0) == Decimal("0.00")

    def test_rounds_half_up_to_cents(self):
        # 0.125 * 3 = 0.375 -> 0.38, а не 0.37 как при банковском округлении
        assert calculate_total_value(Decimal("0.125"), 3) == Decimal("0.38")

    def test_no_float_artifacts(self):
        # 0.1 * 3 во float дало бы 0.30000000000000004
        assert calculate_total_value(Decimal("0.1"), 3) == Decimal("0.30")


class TestFeePerItem:
    def test_divides_flat_fee(self):
        assert estimated_fee_per_item(FEE, 18) == Decimal("0.17")

    def test_zero_quantity_does_not_divide(self):
        assert estimated_fee_per_item(FEE, 0) == Decimal("0.00")

    def test_negative_quantity_is_safe(self):
        assert estimated_fee_per_item(FEE, -5) == Decimal("0.00")

    def test_single_item_gets_whole_fee(self):
        assert estimated_fee_per_item(FEE, 1) == Decimal("3.00")


class TestTotals:
    def test_full_picture(self):
        totals = calculate_totals(Decimal("2.80"), 2, [1, 3, 4], FEE, LIMIT)
        assert totals.total_quantity == 10
        assert totals.total_value == Decimal("28.00")
        assert totals.participants_count == 4  # три участника + организатор
        assert totals.estimated_customs_fee == Decimal("3.00")
        assert totals.estimated_fee_per_item == Decimal("0.30")
        assert totals.remaining_value == Decimal("122.00")
        assert totals.limit_reached is False

    def test_organizer_not_counted_when_takes_nothing(self):
        totals = calculate_totals(Decimal("1.00"), 0, [2], FEE, LIMIT)
        assert totals.participants_count == 1

    def test_empty_purchase_has_no_fee(self):
        totals = calculate_totals(Decimal("2.80"), 0, [], FEE, LIMIT)
        assert totals.total_quantity == 0
        assert totals.total_value == Decimal("0.00")
        assert totals.estimated_customs_fee == Decimal("0.00")
        assert totals.estimated_fee_per_item == Decimal("0.00")

    def test_limit_reached_flag(self):
        totals = calculate_totals(Decimal("1.00"), 0, [150], FEE, LIMIT)
        assert totals.limit_reached is True
        assert totals.remaining_value == Decimal("0.00")


class TestMaxAdditionalQuantity:
    def test_rounds_down(self):
        # осталось 8.00, цена 2.80 -> влезает 2 шт.
        assert max_additional_quantity(Decimal("2.80"), Decimal("142.00"), LIMIT) == 2

    def test_exact_fit(self):
        assert max_additional_quantity(Decimal("10"), Decimal("100"), LIMIT) == 5

    def test_no_room_left(self):
        assert max_additional_quantity(Decimal("2.80"), Decimal("150.00"), LIMIT) == 0

    def test_over_limit_already(self):
        assert max_additional_quantity(Decimal("2.80"), Decimal("200.00"), LIMIT) == 0

    def test_zero_price_is_not_divided(self):
        assert max_additional_quantity(Decimal("0"), Decimal("0"), LIMIT) == 0


class TestLimitCheck:
    def test_allows_within_limit(self):
        check = check_limit(Decimal("2.80"), Decimal("40.00"), 2, LIMIT)
        assert check.allowed is True
        assert check.added_value == Decimal("5.60")
        assert check.projected_total == Decimal("45.60")

    def test_exactly_at_limit_is_allowed(self):
        check = check_limit(Decimal("10"), Decimal("140"), 1, LIMIT)
        assert check.allowed is True
        assert check.projected_total == LIMIT

    def test_blocks_over_limit(self):
        check = check_limit(Decimal("2.00"), Decimal("142.00"), 6, LIMIT)
        assert check.allowed is False
        assert check.projected_total == Decimal("154.00")
        assert check.max_quantity == 4

    def test_reports_zero_max_when_full(self):
        check = check_limit(Decimal("2.00"), LIMIT, 1, LIMIT)
        assert check.allowed is False
        assert check.max_quantity == 0

    def test_excluding_own_request_allows_decrease(self):
        # Участник уже взял 10 шт (100.00), уменьшает до 5 — сумма без него 50.00
        check = check_limit(Decimal("10"), Decimal("50.00"), 5, LIMIT)
        assert check.allowed is True


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2.805", Decimal("2.81")),
        ("2.804", Decimal("2.80")),
        ("2.795", Decimal("2.80")),
        ("0.005", Decimal("0.01")),
        ("10", Decimal("10.00")),
    ],
)
def test_money_rounding(raw, expected):
    assert money(Decimal(raw)) == expected
