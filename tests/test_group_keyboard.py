"""Тесты постоянной reply-клавиатуры группы.

Регресс, который стоило закрыть: сообщение, устанавливающее клавиатуру,
удалялось через group_cleanup_seconds — и клавиатура пропадала вместе с ним
у всех участников. Явного unit-теста на "не удалять" здесь нет (это факт о
поведении Telegram, а не о нашем коде), но состав кнопок и признаки
персистентности проверить стоит.
"""

from __future__ import annotations

from src.handlers.group import (
    ACTIVE_BUTTON_TEXT,
    CREATE_BUTTON_TEXT,
    persistent_keyboard,
)


class TestPersistentKeyboard:
    def test_contains_both_buttons(self):
        markup = persistent_keyboard()
        texts = [button.text for row in markup.keyboard for button in row]
        assert texts == [CREATE_BUTTON_TEXT, ACTIVE_BUTTON_TEXT]

    def test_is_persistent_and_resized(self):
        markup = persistent_keyboard()
        assert markup.is_persistent is True
        assert markup.resize_keyboard is True
