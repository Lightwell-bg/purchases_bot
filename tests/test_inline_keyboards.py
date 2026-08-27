"""Тесты клавиатуры объявления в группе.

Регресс, который стоило закрыть тестом: кнопка "Присоединиться" пропадала
при первой публикации (status ещё DRAFT в момент сборки клавиатуры), а кнопка
создания своей закупки терялась при отсутствии BOT_USERNAME.
"""

from __future__ import annotations

from src.keyboards.inline import announcement


def _button_texts(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


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
