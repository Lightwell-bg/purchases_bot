"""Заглушка для сообщений, которые не подошли ни одному сценарию."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.types import Message

from src.keyboards import inline
from src.texts import ru

router = Router(name="fallback")
router.message.filter(F.chat.type == ChatType.PRIVATE)


@router.message()
async def unknown_message(message: Message) -> None:
    await message.answer(ru.UNKNOWN_COMMAND, reply_markup=inline.main_menu())
