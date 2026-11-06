"""Small pagination helpers shared by services and the Streamlit UI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Sequence, TypeVar

from core.config import page_size as clamp_page_size

T = TypeVar("T")


@dataclass(frozen=True)
class Page(Generic[T]):
    items: Sequence[T]
    page: int
    page_size: int
    total: int

    @property
    def pages(self) -> int:
        if self.total <= 0:
            return 1
        return (self.total + self.page_size - 1) // self.page_size

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.pages

    @property
    def start(self) -> int:
        if self.total == 0:
            return 0
        return (self.page - 1) * self.page_size + 1

    @property
    def end(self) -> int:
        return min(self.page * self.page_size, self.total)


def paginate(items: Sequence[T], page: int = 1, page_size: int | None = None) -> Page[T]:
    size = clamp_page_size(page_size)
    total = len(items)
    pages = max(1, (total + size - 1) // size)
    current = max(1, min(int(page), pages))
    start = (current - 1) * size
    return Page(items=items[start : start + size], page=current, page_size=size, total=total)


def clamp_offset(page: int, page_size: int | None = None) -> tuple[int, int]:
    """Return ``(limit, offset)`` for server-side pagination."""
    size = clamp_page_size(page_size)
    current = max(1, int(page))
    return size, (current - 1) * size
