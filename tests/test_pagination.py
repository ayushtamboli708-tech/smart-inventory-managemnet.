from __future__ import annotations

from core.pagination import clamp_offset, paginate


def test_paginate_splits_and_reports_bounds() -> None:
    result = paginate(list(range(25)), page=2, page_size=10)
    assert result.items == list(range(10, 20))
    assert result.total == 25
    assert result.pages == 3
    assert result.start == 11
    assert result.end == 20
    assert result.has_prev and result.has_next


def test_paginate_clamps_out_of_range_page() -> None:
    result = paginate(list(range(25)), page=99, page_size=10)
    assert result.page == 3
    assert result.items == list(range(20, 25))


def test_paginate_empty_dataset() -> None:
    result = paginate([], page=1, page_size=10)
    assert result.pages == 1
    assert result.total == 0
    assert result.start == 0
    assert not result.has_prev
    assert not result.has_next


def test_offset_and_page_size_are_clamped() -> None:
    limit, offset = clamp_offset(page=3, page_size=1000)
    assert limit == 100
    assert offset == 200
    limit, offset = clamp_offset(page=0, page_size=1)
    assert limit == 5
    assert offset == 0
