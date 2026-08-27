"""CallbackData-фабрики.

Правило: в callback лежит минимум данных (что нажали и над чем),
все проверки прав и статусов делаются заново по базе.
"""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class MenuCB(CallbackData, prefix="m"):
    """Главное меню личного чата."""

    action: str  # main | create | my | active | rules


class ListCB(CallbackData, prefix="l"):
    """Постраничный список активных закупок."""

    action: str  # page
    page: int


class RulesCB(CallbackData, prefix="r"):
    """Экран правил. `scope` — куда вернуться после согласия."""

    action: str  # read | accept | cancel
    scope: str  # create | join | info
    token: str = ""  # public_token закупки для scope=join


class WizardCB(CallbackData, prefix="w"):
    """Мастер создания закупки."""

    action: str  # skip | cancel | currency | publish | edit | edit_field | back
    value: str = ""


class JoinCB(CallbackData, prefix="j"):
    """Присоединение к закупке (идентификация по публичному токену)."""

    action: str  # start | skip | confirm | edit | edit_field | cancel
    token: str
    value: str = ""


class PartCB(CallbackData, prefix="p"):
    """Управление собственной заявкой."""

    action: str  # view | edit | edit_field | leave | leave_confirm
    purchase_id: int
    value: str = ""


class ManageCB(CallbackData, prefix="g"):
    """Панель организатора."""

    action: str  # panel | participants | edit | edit_field | close | close_yes | cancel | cancel_yes
    purchase_id: int
    value: str = ""
