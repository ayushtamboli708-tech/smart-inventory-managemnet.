"""Reusable Streamlit presentation helpers."""

from __future__ import annotations

import html
import logging
from decimal import Decimal
from typing import Any, Mapping

import pandas as pd
import streamlit as st

from core.config import DEFAULT_PAGE_SIZE, page_size as clamp_page_size
from core.errors import StockwiseError
from core.pagination import paginate


def page_header(title: str, subtitle: str | None = None) -> None:
    sub = (
        f"<div class='page-sub'>{html.escape(subtitle)}</div>" if subtitle else ""
    )
    st.markdown(
        f"<div class='page-header'>{html.escape(title)}{sub}</div>",
        unsafe_allow_html=True,
    )


def money(value: Any) -> str:
    try:
        return f"₹{Decimal(str(value or 0)):,.2f}"
    except Exception:  # noqa: BLE001
        return "₹0.00"


def flash(kind: str, message: str) -> None:
    st.session_state.flash = (kind, message)


def show_flash() -> None:
    payload = st.session_state.pop("flash", None)
    if not payload:
        return
    kind, message = payload
    if kind == "success":
        st.success(message)
    elif kind == "warning":
        st.warning(message)
    else:
        st.error(message)


def handle_error(exc: Exception) -> None:
    if isinstance(exc, StockwiseError):
        st.error(str(exc))
    else:
        logging.getLogger("stockwise.ui").exception("Unhandled UI error")
        st.error("Something went wrong. Please try again.")


def _client_pagination_state(key: str) -> tuple[int, int]:
    current = int(st.session_state.get(f"ui_page_{key}", 1) or 1)
    return current, clamp_page_size(st.session_state.get(f"ui_size_{key}", DEFAULT_PAGE_SIZE))


def pagination_controls(
    key: str,
    *,
    page: int,
    pages: int,
    total: int,
    start: int,
    end: int,
) -> None:
    left, middle, right = st.columns([1, 3, 1])
    with left:
        if st.button("← Previous", key=f"prev_{key}", disabled=page <= 1, width="stretch"):
            st.session_state[f"ui_page_{key}"] = page - 1
            st.rerun()
    with middle:
        st.markdown(
            f"<div style='text-align:center; color:#6B7280; padding-top:8px;'>"
            f"Showing {start}-{end} of {total} · page {page} of {pages}</div>",
            unsafe_allow_html=True,
        )
    with right:
        if st.button("Next →", key=f"next_{key}", disabled=page >= pages, width="stretch"):
            st.session_state[f"ui_page_{key}"] = page + 1
            st.rerun()


def data_table(
    df: pd.DataFrame,
    *,
    key: str,
    page_size: int | None = DEFAULT_PAGE_SIZE,
    column_config: Mapping[str, Any] | None = None,
    empty_message: str = "No records found.",
    height: int | None = None,
) -> None:
    """Render a paginated native dataframe (no hand-built HTML tables)."""
    if df is None or df.empty:
        st.info(empty_message)
        return
    # Streamlit rejects an explicit height=None; only pass the option when set.
    size_kwargs = {"height": height} if height is not None else {}
    if not page_size:
        st.dataframe(
            df,
            width="stretch",
            hide_index=True,
            column_config=column_config,
            **size_kwargs,
        )
        return

    page, size = _client_pagination_state(key)
    result = paginate(df.to_dict("records"), page, size)
    view = pd.DataFrame(result.items)
    st.dataframe(
        view,
        width="stretch",
        hide_index=True,
        column_config=column_config,
        **size_kwargs,
    )
    pagination_controls(
        key,
        page=result.page,
        pages=result.pages,
        total=result.total,
        start=result.start,
        end=result.end,
    )


def server_page(key: str) -> int:
    return int(st.session_state.get(f"ui_page_{key}", 1) or 1)


def server_pagination(
    key: str, *, page: int, total: int, page_size: int
) -> None:
    pages = max(1, (total + page_size - 1) // page_size)
    if page > pages:
        # A filter change can leave the stored page beyond the result set.
        st.session_state[f"ui_page_{key}"] = pages
        st.rerun()
    start = 0 if total == 0 else (page - 1) * page_size + 1
    end = min(page * page_size, total)
    pagination_controls(
        key, page=min(page, pages), pages=pages, total=total, start=start, end=end
    )


def kpi_card(title: str, value: Any, accent: str = "#2563EB") -> None:
    st.markdown(
        f"""
        <div class="dashboard-card" style="border-left: 4px solid {accent};">
            <div class="kpi-label">{title}</div>
            <div class="kpi-num">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def empty_state(message: str) -> None:
    st.markdown(
        f"<div class='dashboard-card' style='text-align:center; color:#6B7280; "
        f"padding:40px;'>{message}</div>",
        unsafe_allow_html=True,
    )
