"""FSM-состояния.

FSM живёт только на время активного диалога: как только шаг завершён,
всё значимое уходит в базу.
"""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class CreatePurchase(StatesGroup):
    """Мастер создания закупки."""

    title = State()
    product_url = State()
    photo = State()
    unit_price = State()
    currency = State()
    variants = State()
    organizer_quantity = State()
    deadline = State()
    pickup = State()
    comment = State()
    preview = State()


class EditPurchase(StatesGroup):
    """Правка опубликованной закупки организатором."""

    waiting_value = State()


class JoinPurchase(StatesGroup):
    """Форма присоединения."""

    quantity = State()
    variant = State()
    comment = State()
    preview = State()


class EditParticipation(StatesGroup):
    """Правка собственной заявки."""

    waiting_value = State()
