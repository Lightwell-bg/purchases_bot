"""Тесты клавиатуры объявления в группе.

Регресс, который стоило закрыть тестом: кнопка "Присоединиться" пропадала
при первой публикации (status ещё DRAFT в момент сборки клавиатуры), а кнопка
создания своей закупки терялась при отсутствии BOT_USERNAME.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from src.database.models import Purchase, PurchaseStatus, User
from src.keyboards.callbacks import ManageCB
from src.keyboards.inline import BTN_BACK_TO_MENU, admin_purchases_list, announcement, main_menu

NOW = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)


def _button_texts(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


def _make_purchase(purchase_id: int, title: str = "Товар") -> Purchase:
    organizer = User(id=99, telegram_id=1099, username="orga")
    return Purchase(
        id=purchase_id,
        public_token=f"token{purchase_id}",
        organizer_id=organizer.id,
        organizer=organizer,
        title=title,
        unit_price=Decimal("1.00"),
        currency="EUR",
        organizer_quantity=1,
        deadline=NOW + timedelta(days=3),
        status=PurchaseStatus.OPEN,
        participants=[],
    )


class TestAnnouncementKeyboard:
    def test_open_purchase_has_join_button(self):
        markup = announcement("join-url", "rules-url", joinable=True)
        assert "🛒 Присоединиться" in _button_texts(markup)

    def test_closed_purchase_has_no_join_button(self):
        markup = announcement("join-url", "rules-url", joinable=False)
        assert "🛒 Присоединиться" not in _button_texts(markup)

    def test_rules_button_always_present(self):
        for joinable in (True, False):
            markup = announcement("join-url", "rules-url", joinable=joinable)
            assert "📜 Правила" in _button_texts(markup)

    def test_create_button_present_when_link_given(self):
        markup = announcement("join-url", "rules-url", joinable=True, create_link="create-url")
        texts = _button_texts(markup)
        assert "➕ Создать свою закупку" in texts

    def test_create_button_absent_without_link(self):
        markup = announcement("join-url", "rules-url", joinable=True, create_link=None)
        assert "➕ Создать свою закупку" not in _button_texts(markup)

    def test_create_button_url_is_correct(self):
        markup = announcement("join-url", "rules-url", joinable=True, create_link="create-url")
        button = next(
            b for row in markup.inline_keyboard for b in row if b.text == "➕ Создать свою закупку"
        )
        assert button.url == "create-url"


class TestMainMenuKeyboard:
    def test_regular_user_has_no_admin_buttons(self):
        texts = _button_texts(main_menu(is_admin=False))
        assert "📊 Статистика" not in texts
        assert "🗂 Все закупки" not in texts

    def test_admin_sees_admin_buttons(self):
        texts = _button_texts(main_menu(is_admin=True))
        assert "📊 Статистика" in texts
        assert "🗂 Все закупки" in texts

    def test_default_is_not_admin(self):
        assert "📊 Статистика" not in _button_texts(main_menu())


class TestAdminPurchasesListKeyboard:
    def test_one_button_per_purchase(self):
        purchases = [_make_purchase(1), _make_purchase(2), _make_purchase(3)]
        markup = admin_purchases_list(purchases, page=0, total_pages=1)
        panel_buttons = [
            b
            for row in markup.inline_keyboard
            for b in row
            if b.callback_data and b.callback_data.startswith("g:")
        ]
        assert len(panel_buttons) == 3

    def test_panel_callback_data_is_manage_panel(self):
        markup = admin_purchases_list([_make_purchase(42)], page=0, total_pages=1)
        button = markup.inline_keyboard[0][0]
        assert button.callback_data == ManageCB(action="panel", purchase_id=42).pack()

    def test_first_page_has_no_back_nav(self):
        markup = admin_purchases_list([_make_purchase(1)], page=0, total_pages=3)
        assert "◀️ Назад" not in _button_texts(markup)
        assert "▶️ Далее" in _button_texts(markup)

    def test_last_page_has_no_forward_nav(self):
        markup = admin_purchases_list([_make_purchase(1)], page=2, total_pages=3)
        assert "▶️ Далее" not in _button_texts(markup)
        assert "◀️ Назад" in _button_texts(markup)

    def test_single_page_has_no_nav(self):
        markup = admin_purchases_list([_make_purchase(1)], page=0, total_pages=1)
        texts = _button_texts(markup)
        assert "◀️ Назад" not in texts
        assert "▶️ Далее" not in texts

    def test_back_to_menu_always_present(self):
        markup = admin_purchases_list([_make_purchase(1)], page=0, total_pages=1)
        assert BTN_BACK_TO_MENU in _button_texts(markup)
