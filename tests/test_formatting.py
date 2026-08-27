"""Тесты форматирования сообщений."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from src.utils.formatting import (
    MAX_CAPTION_LENGTH,
    esc,
    fit_html,
    fmt_amount,
    fmt_datetime,
    fmt_money,
    group_message_link,
    link,
    plural_ru,
    truncate,
)

TZ = ZoneInfo("Europe/Sofia")


class TestMoney:
    def test_comma_decimal_separator(self):
        assert fmt_amount(Decimal("2.8")) == "2,80"

    def test_euro_symbol_before_amount(self):
        assert fmt_money(Decimal("2.80"), "EUR") == "€2,80"

    def test_letter_code_after_amount(self):
        assert fmt_money(Decimal("2.80"), "BGN") == "2,80 лв."

    def test_unknown_currency_falls_back_to_code(self):
        assert fmt_money(Decimal("5"), "czk") == "5,00 CZK"


class TestEscaping:
    def test_escapes_html(self):
        assert esc("<b>hack</b> & co") == "&lt;b&gt;hack&lt;/b&gt; &amp; co"

    def test_none_is_empty(self):
        assert esc(None) == ""

    def test_link_escapes_label(self):
        assert link("https://e.com", "<x>") == '<a href="https://e.com">&lt;x&gt;</a>'

    def test_link_without_url_is_empty(self):
        assert link(None, "text") == ""


class TestTruncate:
    def test_short_text_untouched(self):
        assert truncate("abc", 10) == "abc"

    def test_long_text_gets_ellipsis(self):
        assert truncate("abcdef", 4) == "abc…"

    def test_none_is_empty(self):
        assert truncate(None, 10) == ""


class TestFitHtml:
    def test_short_text_untouched(self):
        assert fit_html("line1\nline2", 100) == "line1\nline2"

    def test_long_text_is_cut_by_lines(self):
        text = "\n".join(f"line {i}" for i in range(500))
        result = fit_html(text, MAX_CAPTION_LENGTH)
        assert len(result) <= MAX_CAPTION_LENGTH
        assert result.endswith("…")

    def test_does_not_break_html_tags(self):
        text = "\n".join(["<b>bold line</b>"] * 200)
        result = fit_html(text, 100)
        assert result.count("<b>") == result.count("</b>")


class TestDatetime:
    def test_converts_to_local_timezone(self):
        moment = datetime(2026, 8, 30, 20, 59, tzinfo=timezone.utc)
        assert fmt_datetime(moment, TZ) == "30.08.2026 23:59"

    def test_date_only(self):
        moment = datetime(2026, 8, 30, 20, 59, tzinfo=timezone.utc)
        assert fmt_datetime(moment, TZ, with_time=False) == "30.08.2026"


class TestGroupLink:
    def test_supergroup_link(self):
        assert group_message_link(-1001234567890, 42) == "https://t.me/c/1234567890/42"

    def test_plain_group_has_no_link(self):
        assert group_message_link(-123456, 42) is None

    def test_missing_ids(self):
        assert group_message_link(None, None) is None


@pytest.mark.parametrize(
    ("number", "expected"),
    [(1, "участник"), (2, "участника"), (5, "участников"), (11, "участников"), (21, "участник")],
)
def test_plural(number, expected):
    assert plural_ru(number, "участник", "участника", "участников") == expected
