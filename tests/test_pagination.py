"""Тесты постраничной разбивки."""

from __future__ import annotations

from src.utils.pagination import paginate


class TestPaginate:
    def test_empty_list_has_one_page(self):
        assert paginate(0, 0, 5) == (0, 1)

    def test_exact_multiple(self):
        assert paginate(10, 0, 5) == (0, 2)

    def test_remainder_rounds_up(self):
        assert paginate(11, 0, 5) == (0, 3)

    def test_negative_page_clamped_to_zero(self):
        assert paginate(11, -3, 5) == (0, 3)

    def test_page_beyond_range_clamped_to_last(self):
        assert paginate(11, 99, 5) == (2, 3)

    def test_single_item(self):
        assert paginate(1, 0, 5) == (0, 1)
