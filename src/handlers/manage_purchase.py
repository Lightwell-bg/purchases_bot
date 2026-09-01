"""Панель организатора: участники, правки, закрытие и отмена закупки."""

from __future__ import annotations

import logging
from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.database.models import Purchase, PurchaseStatus, User
from src.database.repositories.participants import ParticipantRepository
from src.database.repositories.purchases import PurchaseRepository
from src.handlers.common import show_screen
from src.keyboards import inline
from src.keyboards.callbacks import ManageCB
from src.services import availability, purchase_service, telegram_service
from src.services.calculations import calculate_total_value
from src.states.purchase import EditPurchase
from src.texts import ru
from src.utils import parsing
from src.utils.formatting import fmt_money

logger = logging.getLogger(__name__)

router = Router(name="manage_purchase")
router.message.filter(F.chat.type == ChatType.PRIVATE)

# field -> (вопрос, можно ли очистить значение)
EDIT_PROMPTS: dict[str, tuple[str, bool]] = {
    "title": ("Новое название товара:", False),
    "url": ("Новая ссылка на товар:", True),
    "photo": ("Отправьте новое фото товара:", True),
    "price": ("Новая цена за единицу:", False),
    "variants": ("Новое описание допустимых вариантов:", True),
    "quantity": ("Сколько единиц берёте себе?", False),
    "deadline": ("Новая дата окончания сбора (30.08.2026 или 30.08.2026 18:00):", False),
    "pickup": ("Новое место получения:", False),
    "comment": ("Новый комментарий к закупке:", True),
}

FIELD_TO_COLUMN = {
    "title": "title",
    "url": "product_url",
    "photo": "photo_file_id",
    "price": "unit_price",
    "variants": "variant_description",
    "quantity": "organizer_quantity",
    "deadline": "deadline",
    "pickup": "pickup_location",
    "comment": "description",
}


async def _load_owned(
    session: AsyncSession,
    purchase_id: int,
    user: User,
) -> Purchase | None:
    """Закупка, если пользователь действительно её организатор или админ."""
    purchase = await PurchaseRepository(session).get(purchase_id)
    if purchase is None:
        return None
    if purchase.organizer_id == user.id or get_settings().is_admin(user.telegram_id):
        return purchase
    return None


async def show_panel(callback: CallbackQuery, purchase: Purchase) -> None:
    settings = get_settings()
    await show_screen(
        callback,
        ru.organizer_panel(purchase, purchase_service.totals(purchase), settings.tz),
        inline.organizer_panel(purchase),
    )


@router.callback_query(ManageCB.filter(F.action == "panel"))
async def panel(
    callback: CallbackQuery,
    callback_data: ManageCB,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    await state.clear()
    purchase = await _load_owned(session, callback_data.purchase_id, user)
    if purchase is None:
        await callback.answer(ru.NOT_YOUR_PURCHASE, show_alert=True)
        return
    await show_panel(callback, purchase)
    await callback.answer()


@router.callback_query(ManageCB.filter(F.action == "participants"))
async def participants(
    callback: CallbackQuery,
    callback_data: ManageCB,
    session: AsyncSession,
    user: User,
) -> None:
    purchase = await _load_owned(session, callback_data.purchase_id, user)
    if purchase is None:
        await callback.answer(ru.NOT_YOUR_PURCHASE, show_alert=True)
        return
    rows = await ParticipantRepository(session).list_active(purchase.id)
    await show_screen(
        callback, ru.participants_list(purchase, rows), inline.back_to_panel(purchase.id)
    )
    await callback.answer()


# --------------------------------------------------------------------------- #
# Правка полей
# --------------------------------------------------------------------------- #

@router.callback_query(ManageCB.filter(F.action == "edit"))
async def edit_menu(
    callback: CallbackQuery,
    callback_data: ManageCB,
    session: AsyncSession,
    user: User,
) -> None:
    purchase = await _load_owned(session, callback_data.purchase_id, user)
    if purchase is None:
        await callback.answer(ru.NOT_YOUR_PURCHASE, show_alert=True)
        return
    if purchase.status != PurchaseStatus.OPEN:
        await callback.answer("Менять можно только открытую закупку.", show_alert=True)
        return
    await show_screen(
        callback, ru.EDIT_FIELD_PROMPT, inline.manage_edit_fields(purchase.id)
    )
    await callback.answer()


@router.callback_query(ManageCB.filter(F.action == "edit_field"))
async def edit_field(
    callback: CallbackQuery,
    callback_data: ManageCB,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    field = callback_data.value
    if field not in EDIT_PROMPTS:
        await callback.answer()
        return
    purchase = await _load_owned(session, callback_data.purchase_id, user)
    if purchase is None:
        await callback.answer(ru.NOT_YOUR_PURCHASE, show_alert=True)
        return
    if purchase.status != PurchaseStatus.OPEN:
        await callback.answer("Менять можно только открытую закупку.", show_alert=True)
        return

    prompt, clearable = EDIT_PROMPTS[field]
    await state.set_state(EditPurchase.waiting_value)
    await state.update_data(purchase_id=purchase.id, field=field)
    await show_screen(callback, prompt, inline.manage_edit_cancel(purchase.id, clearable))
    await callback.answer()


@router.callback_query(ManageCB.filter(F.action == "clear_field"))
async def clear_field(
    callback: CallbackQuery,
    callback_data: ManageCB,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    bot: Bot,
) -> None:
    """Очистка необязательного поля (ссылка, фото, комментарий, варианты)."""
    data = await state.get_data()
    field = str(data.get("field", ""))
    purchase = await _load_owned(session, callback_data.purchase_id, user)
    if purchase is None or field not in EDIT_PROMPTS or not EDIT_PROMPTS[field][1]:
        await callback.answer(ru.OUTDATED_CALLBACK, show_alert=True)
        return
    if purchase.status != PurchaseStatus.OPEN:
        await callback.answer("Менять можно только открытую закупку.", show_alert=True)
        return

    setattr(purchase, FIELD_TO_COLUMN[field], None)
    await session.flush()
    await telegram_service.refresh_announcement(bot, session, purchase)
    await session.commit()

    await state.clear()
    await callback.answer("Поле очищено.")
    await show_panel(callback, purchase)


def _apply_value(purchase: Purchase, field: str, raw: str) -> None:
    """Проверяет и записывает новое значение поля. ValueError -> текст ошибки."""
    settings = get_settings()
    business = settings.business

    if field == "title":
        purchase.title = parsing.clean_text(raw, 200, "Название")
    elif field == "url":
        purchase.product_url = parsing.parse_url(raw)
    elif field == "variants":
        purchase.variant_description = parsing.clean_text(raw, 500, "Описание вариантов")
    elif field == "pickup":
        purchase.pickup_location = parsing.clean_text(raw, 200, "Место получения")
    elif field == "comment":
        purchase.description = parsing.clean_multiline(raw, 500)
    elif field == "deadline":
        purchase.deadline = parsing.parse_deadline(
            raw, settings.tz, purchase_service.utcnow(), business.max_deadline_days
        )
    elif field == "price":
        price = parsing.parse_price(raw)
        totals = purchase_service.totals(purchase)
        projected = calculate_total_value(price, totals.total_quantity)
        if projected > business.purchase_limit_eur:
            raise ValueError(
                "С такой ценой закупка превысит лимит "
                f"{fmt_money(business.purchase_limit_eur, purchase.currency)} "
                f"(вышло бы {fmt_money(projected, purchase.currency)}). "
                "Сначала уменьшите количество."
            )
        purchase.unit_price = price
    elif field == "quantity":
        quantity = parsing.parse_quantity(raw, 0, business.max_items_per_participant)
        check = purchase_service.check_organizer_quantity_limit(purchase, quantity)
        if not check.allowed:
            raise ValueError(
                f"Не влезает в лимит {fmt_money(check.limit, purchase.currency)}. "
                f"Максимум {check.max_quantity} шт."
            )
        purchase.organizer_quantity = quantity
    else:
        raise ValueError("Неизвестное поле.")


@router.message(EditPurchase.waiting_value, F.photo)
async def edit_photo(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    bot: Bot,
) -> None:
    """Смена фото требует переиздания объявления: тип сообщения меняется."""
    data = await state.get_data()
    if str(data.get("field")) != "photo":
        await message.answer(ru.NEED_TEXT)
        return

    purchase = await _load_owned(session, int(data.get("purchase_id", 0)), user)
    if purchase is None:
        await state.clear()
        await message.answer(ru.NOT_YOUR_PURCHASE, reply_markup=inline.main_menu())
        return
    if purchase.status != PurchaseStatus.OPEN:
        await state.clear()
        await message.answer("Менять можно только открытую закупку.")
        return

    photo = message.photo[-1] if message.photo else None
    if photo is None:
        await message.answer(ru.NEED_PHOTO)
        return

    had_photo = purchase.photo_file_id is not None
    purchase.photo_file_id = photo.file_id
    await session.flush()

    if had_photo:
        await telegram_service.refresh_announcement(bot, session, purchase)
    else:
        await _republish(bot, session, purchase)
    await session.commit()

    await state.clear()
    settings = get_settings()
    await message.answer(
        ru.organizer_panel(purchase, purchase_service.totals(purchase), settings.tz),
        reply_markup=inline.organizer_panel(purchase),
    )


async def _republish(bot: Bot, session: AsyncSession, purchase: Purchase) -> None:
    """Удаляет старое объявление и публикует новое (например, при добавлении фото)."""
    old_chat_id, old_message_id = purchase.group_chat_id, purchase.group_message_id
    purchase.group_message_id = None
    if await telegram_service.publish_purchase(bot, session, purchase) and old_message_id:
        try:
            await bot.delete_message(old_chat_id, old_message_id)
        except Exception as exc:  # noqa: BLE001 - удаление не критично
            logger.warning("Cannot delete old announcement %s: %s", old_message_id, exc)


@router.message(EditPurchase.waiting_value, F.text)
async def edit_value(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    bot: Bot,
) -> None:
    settings = get_settings()
    data = await state.get_data()
    field = str(data.get("field", ""))
    purchase = await _load_owned(session, int(data.get("purchase_id", 0)), user)

    if purchase is None or field not in EDIT_PROMPTS:
        await state.clear()
        await message.answer(ru.PURCHASE_NOT_FOUND, reply_markup=inline.main_menu())
        return
    if field == "photo":
        await message.answer(ru.NEED_PHOTO)
        return
    if purchase.status != PurchaseStatus.OPEN:
        await state.clear()
        await message.answer("Менять можно только открытую закупку.")
        return

    try:
        _apply_value(purchase, field, message.text or "")
    except ValueError as exc:
        await message.answer(f"⚠️ {exc}")
        return

    await session.flush()
    await telegram_service.refresh_announcement(bot, session, purchase)
    await session.commit()
    logger.info("Purchase %s field %s updated by tg=%s", purchase.id, field, user.telegram_id)

    await state.clear()
    await message.answer("✅ Изменения сохранены.")
    await message.answer(
        ru.organizer_panel(purchase, purchase_service.totals(purchase), settings.tz),
        reply_markup=inline.organizer_panel(purchase),
    )


@router.message(EditPurchase.waiting_value)
async def edit_wrong_type(message: Message) -> None:
    await message.answer(ru.NEED_TEXT)


# --------------------------------------------------------------------------- #
# Закрытие и отмена
# --------------------------------------------------------------------------- #

@router.callback_query(ManageCB.filter(F.action == "close"))
async def close_prompt(
    callback: CallbackQuery,
    callback_data: ManageCB,
    session: AsyncSession,
    user: User,
) -> None:
    purchase = await _load_owned(session, callback_data.purchase_id, user)
    if purchase is None:
        await callback.answer(ru.NOT_YOUR_PURCHASE, show_alert=True)
        return
    if purchase.status != PurchaseStatus.OPEN:
        await callback.answer("Сбор уже не открыт.", show_alert=True)
        return
    await show_screen(callback, ru.CLOSE_CONFIRM, inline.confirm_close(purchase.id))
    await callback.answer()


@router.callback_query(ManageCB.filter(F.action == "close_yes"))
async def close_purchase(
    callback: CallbackQuery,
    callback_data: ManageCB,
    session: AsyncSession,
    user: User,
    bot: Bot,
) -> None:
    purchase = await _load_owned(session, callback_data.purchase_id, user)
    if purchase is None:
        await callback.answer(ru.NOT_YOUR_PURCHASE, show_alert=True)
        return

    recipients = await purchase_service.participant_telegram_ids(session, purchase)
    if not await purchase_service.close_purchase(session, purchase):
        await callback.answer("Сбор уже не открыт.", show_alert=True)
        return

    await telegram_service.refresh_announcement(bot, session, purchase)
    await session.commit()

    delivered = await telegram_service.notify_users(bot, recipients, ru.notify_closed(purchase))
    logger.info("Purchase %s closed, notified %s/%s", purchase.id, delivered, len(recipients))

    await callback.answer(ru.PURCHASE_CLOSED)
    await show_panel(callback, purchase)


@router.callback_query(ManageCB.filter(F.action == "cancel"))
async def cancel_prompt(
    callback: CallbackQuery,
    callback_data: ManageCB,
    session: AsyncSession,
    user: User,
) -> None:
    purchase = await _load_owned(session, callback_data.purchase_id, user)
    if purchase is None:
        await callback.answer(ru.NOT_YOUR_PURCHASE, show_alert=True)
        return
    if not availability.can_manage(purchase.status):
        await callback.answer("Закупка уже завершена.", show_alert=True)
        return
    await show_screen(callback, ru.CANCEL_PURCHASE_CONFIRM, inline.confirm_cancel(purchase.id))
    await callback.answer()


@router.callback_query(ManageCB.filter(F.action == "cancel_yes"))
async def cancel_purchase(
    callback: CallbackQuery,
    callback_data: ManageCB,
    session: AsyncSession,
    user: User,
    bot: Bot,
) -> None:
    purchase = await _load_owned(session, callback_data.purchase_id, user)
    if purchase is None:
        await callback.answer(ru.NOT_YOUR_PURCHASE, show_alert=True)
        return

    recipients = await purchase_service.participant_telegram_ids(session, purchase)
    if not await purchase_service.cancel_purchase(session, purchase):
        await callback.answer("Закупка уже завершена.", show_alert=True)
        return

    await telegram_service.refresh_announcement(bot, session, purchase)
    await session.commit()

    await telegram_service.notify_users(bot, recipients, ru.notify_cancelled(purchase))
    await callback.answer(ru.PURCHASE_CANCELLED)
    await show_panel(callback, purchase)
