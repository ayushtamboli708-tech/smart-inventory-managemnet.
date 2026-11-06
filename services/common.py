"""Shared service helpers."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Iterable, Mapping, Sequence

from core.errors import DatabaseUnavailable
from core.pagination import clamp_offset
from core.time import utc_now


def require_connection(conn: Any | None) -> Any:
    if conn is None:
        raise DatabaseUnavailable("Database connection is not available.")
    return conn


def fetch_page(
    conn: Any,
    *,
    count_sql: str,
    count_params: Sequence[Any],
    data_sql: str,
    data_params: Sequence[Any],
    page: int,
    page_size: int | None,
) -> tuple[list[dict], int]:
    limit, offset = clamp_offset(page, page_size)
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(count_sql, tuple(count_params))
        total_row = cursor.fetchone() or {}
        total = int(next(iter(total_row.values()), 0) or 0)
        cursor.execute(data_sql + " LIMIT %s OFFSET %s", (*data_params, limit, offset))
        rows = cursor.fetchall()
    finally:
        cursor.close()
    return list(rows), total


def log_audit(
    conn: Any,
    *,
    company_id: int,
    actor_id: int | None,
    action: str,
    entity: str,
    entity_id: int | str | None = None,
    details: Mapping[str, Any] | None = None,
) -> None:
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO audit_logs
                (company_id, actor_id, action, entity, entity_id, details, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                company_id,
                actor_id,
                action,
                entity,
                str(entity_id) if entity_id is not None else None,
                json.dumps(details, default=str) if details else None,
                utc_now(),
            ),
        )
    finally:
        cursor.close()


def rows_to_dicts(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def to_decimal(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))
