"""Денежные расчёты закупки.

Модуль намеренно не знает ни про базу, ни про Telegram: на вход —
числа, на выход — числа. Всё считается в Decimal, float не используется.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from typing import Iterable

CENT = Decimal("0.01")


def money(value: Decimal | int | str) -> Decimal:
    """Округляет сумму до копеек (банковское округление тут не нужно)."""
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class PurchaseTotals:
    """Агрегированные показатели одной закупки."""

    participants_count: int
    total_quantity: int
    total_value: Decimal
    limit: Decimal
    estimated_customs_fee: Decimal
    estimated_fee_per_item: Decimal

    @property
    def remaining_value(self) -> Decimal:
        """Сколько ещё можно добрать по деньгам до лимита."""
        return money(max(self.limit - self.total_value, Decimal("0")))

    @property
    def limit_reached(self) -> bool:
        return self.total_value >= self.limit


@dataclass(frozen=True)
class LimitCheck:
    """Результат проверки лимита перед добавлением/изменением заявки."""

    allowed: bool
    current_total: Decimal
    added_value: Decimal
    projected_total: Decimal
    limit: Decimal
    max_quantity: int


def calculate_total_quantity(organizer_quantity: int, quantities: Iterable[int]) -> int:
    """Организатор берёт товар наравне с остальными, поэтому входит в сумму."""
    return int(organizer_quantity) + sum(int(q) for q in quantities)


def calculate_total_value(unit_price: Decimal, total_quantity: int) -> Decimal:
    return money(Decimal(unit_price) * Decimal(total_quantity))


def estimated_fee_per_item(customs_flat_fee: Decimal, total_quantity: int) -> Decimal:
    """Ориентировочная доля таможенного сбора на единицу товара."""
    if total_quantity <= 0:
        return money(0)
    return money(Decimal(customs_flat_fee) / Decimal(total_quantity))


def calculate_totals(
    unit_price: Decimal,
    organizer_quantity: int,
    participant_quantities: Iterable[int],
    customs_flat_fee: Decimal,
    limit: Decimal,
) -> PurchaseTotals:
    """Считает всё, что показывается в объявлении и в панели организатора."""
    quantities = [int(q) for q in participant_quantities]
    total_quantity = calculate_total_quantity(organizer_quantity, quantities)
    total_value = calculate_total_value(unit_price, total_quantity)

    # Организатор считается участником, только если сам что-то берёт.
    participants_count = len(quantities) + (1 if organizer_quantity > 0 else 0)

    customs_fee = money(customs_flat_fee) if total_quantity > 0 else money(0)

    return PurchaseTotals(
        participants_count=participants_count,
        total_quantity=total_quantity,
        total_value=total_value,
        limit=money(limit),
        estimated_customs_fee=customs_fee,
        estimated_fee_per_item=estimated_fee_per_item(customs_flat_fee, total_quantity),
    )


def max_additional_quantity(unit_price: Decimal, current_total: Decimal, limit: Decimal) -> int:
    """Сколько ещё единиц влезает в лимит при текущей сумме закупки."""
    price = Decimal(unit_price)
    if price <= 0:
        return 0
    remaining = Decimal(limit) - Decimal(current_total)
    if remaining <= 0:
        return 0
    return int((remaining / price).to_integral_value(rounding=ROUND_DOWN))


def check_limit(
    unit_price: Decimal,
    total_without_request: Decimal,
    requested_quantity: int,
    limit: Decimal,
) -> LimitCheck:
    """Проверяет, влезает ли заявка в лимит.

    `total_without_request` — сумма закупки без учёта проверяемой заявки.
    При редактировании существующей заявки её текущий вклад нужно вычесть,
    иначе пользователь не сможет даже уменьшить количество.
    """
    price = Decimal(unit_price)
    current = money(total_without_request)
    added = calculate_total_value(price, requested_quantity)
    projected = money(current + added)
    limit_value = money(limit)

    return LimitCheck(
        allowed=projected <= limit_value,
        current_total=current,
        added_value=added,
        projected_total=projected,
        limit=limit_value,
        max_quantity=max_additional_quantity(price, current, limit_value),
    )
