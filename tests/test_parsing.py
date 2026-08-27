"""Тесты разбора пользовательского ввода."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from src.utils.parsing import (
    clean_multiline,
    clean_text,
    parse_deadline,
    parse_price,
    parse_quantity,
    parse_url,
)

TZ = ZoneInfo("Europe/Sofia")
NOW = datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)


class TestPrice:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("2.80", Decimal("2.80")),
            ("2,80", Decimal("2.80")),
            ("€2,80", Decimal("2.80")),
            (" 2.8 ", Decimal("2.80")),
            ("2.805", Decimal("2.81")),
        ],
    )
    def test_valid(self, raw, expected):
        assert parse_price(raw) == expected

    @pytest.mark.parametrize("raw", ["", "бесплатно", "0", "-5", "1000000"])
    def test_invalid(self, raw):
        with pytest.raises(ValueError):
            parse_price(raw)


class TestQuantity:
    def test_valid(self):
        assert parse_quantity("3") == 3

    def test_zero_allowed_when_minimum_is_zero(self):
        assert parse_quantity("0", minimum=0) == 0

    @pytest.mark.parametrize("raw", ["0", "-1", "2.5", "две", ""])
    def test_invalid(self, raw):
        with pytest.raises(ValueError):
            parse_quantity(raw)

    def test_above_maximum(self):
        with pytest.raises(ValueError):
            parse_quantity("101", maximum=100)


class TestUrl:
    def test_valid(self):
        assert parse_url("https://example.com/item?id=1") == "https://example.com/item?id=1"

    @pytest.mark.parametrize("raw", ["example.com", "ftp://example.com", ""])
    def test_invalid(self, raw):
        with pytest.raises(ValueError):
            parse_url(raw)


class TestDeadline:
    def test_date_only_is_end_of_day(self):
        result = parse_deadline("30.08.2026", TZ, NOW)
        local = result.astimezone(TZ)
        assert (local.year, local.month, local.day) == (2026, 8, 30)
        assert (local.hour, local.minute) == (23, 59)

    def test_date_with_time(self):
        result = parse_deadline("30.08.2026 18:00", TZ, NOW)
        local = result.astimezone(TZ)
        assert (local.hour, local.minute) == (18, 0)

    def test_result_is_utc(self):
        assert parse_deadline("30.08.2026", TZ, NOW).tzinfo is timezone.utc

    def test_short_date_uses_current_year(self):
        result = parse_deadline("30.08", TZ, NOW).astimezone(TZ)
        assert result.year == 2026

    def test_short_date_in_the_past_rolls_to_next_year(self):
        result = parse_deadline("01.01", TZ, NOW).astimezone(TZ)
        assert result.year == 2027

    def test_past_date_rejected(self):
        with pytest.raises(ValueError):
            parse_deadline("01.01.2020", TZ, NOW)

    def test_too_far_rejected(self):
        with pytest.raises(ValueError):
            parse_deadline("01.01.2030", TZ, NOW, max_days=365)

    def test_garbage_rejected(self):
        with pytest.raises(ValueError):
            parse_deadline("завтра", TZ, NOW)


class TestText:
    def test_collapses_whitespace(self):
        assert clean_text("  Baseus   USB-C  ", 50) == "Baseus USB-C"

    def test_empty_rejected(self):
        with pytest.raises(ValueError):
            clean_text("   ", 50)

    def test_too_long_rejected(self):
        with pytest.raises(ValueError):
            clean_text("x" * 51, 50)

    def test_multiline_keeps_line_breaks(self):
        assert clean_multiline("a\n\n b ", 50) == "a\nb"
