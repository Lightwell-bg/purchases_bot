"""Сборка роутеров.

Порядок важен: команды и групповые хендлеры идут раньше сценариев с FSM,
заглушка — последней.
"""

from __future__ import annotations

from aiogram import Dispatcher

from src.handlers import (
    admin,
    create_purchase,
    errors,
    fallback,
    group,
    join_purchase,
    manage_purchase,
    my_purchases,
    participation,
    rules,
    start,
)


def register_routers(dp: Dispatcher) -> None:
    dp.include_router(errors.router)
    dp.include_router(start.router)
    dp.include_router(group.router)
    dp.include_router(admin.router)
    dp.include_router(my_purchases.router)
    dp.include_router(rules.router)
    dp.include_router(create_purchase.router)
    dp.include_router(join_purchase.router)
    dp.include_router(participation.router)
    dp.include_router(manage_purchase.router)
    dp.include_router(fallback.router)
