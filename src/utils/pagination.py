"""Постраничная разбивка списков."""

from __future__ import annotations


def paginate(total: int, page: int, page_size: int) -> tuple[int, int]:
    """Возвращает (скорректированный номер страницы, всего страниц).

    Номер страницы всегда попадает в допустимый диапазон [0, total_pages - 1],
    даже если запросили отрицательную страницу или страницу за пределами списка.
    Пустой список считается одной (пустой) страницей.
    """
    total_pages = max((total + page_size - 1) // page_size, 1)
    page = max(0, min(page, total_pages - 1))
    return page, total_pages
