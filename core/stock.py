"""Inventory helpers: locking, validation, and materialized balance updates.

``products.stock_qty`` is the materialized balance. Every movement also writes
an ``inventory_ledger`` row, so the ledger remains the audit trail and can be
used to rebuild the balance with ``recompute_stock``.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Any, Iterable, Mapping

from core.cart import CartItem
from core.errors import InsufficientStock, ValidationError
from core.time import utc_now


def decimal_qty(value: Any) -> Decimal:
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except Exception as exc:  # noqa: BLE001 - normalize driver types
        raise ValidationError(f"Invalid quantity: {value!r}") from exc


def aggregate_required(items: Iterable[CartItem | tuple[int, Any]]) -> dict[int, Decimal]:
    """Aggregate demand per product id."""
    totals: dict[int, Decimal] = defaultdict(lambda: Decimal("0.00"))
    for item in items:
        if isinstance(item, CartItem):
            product_id, qty = item.product_id, item.quantity
        else:
            product_id, qty = item
        totals[int(product_id)] += decimal_qty(qty)
    return dict(totals)


def lock_products(cursor: Any, company_id: int, product_ids: Iterable[int]) -> dict[int, dict]:
    """Lock product rows and return them keyed by id."""
    ids = sorted({int(pid) for pid in product_ids})
    if not ids:
        return {}
    placeholders = ", ".join(["%s"] * len(ids))
    cursor.execute(
        f"""
        SELECT product_id, sku, name, stock_qty, selling_price, is_active, deleted_at
        FROM products
        WHERE company_id = %s AND product_id IN ({placeholders})
        FOR UPDATE
        """,
        (company_id, *ids),
    )
    return {int(row["product_id"]): row for row in cursor.fetchall()}


def validate_available(
    products: Mapping[int, Mapping[str, Any]], required: Mapping[int, Decimal]
) -> None:
    for product_id, needed in required.items():
        row = products.get(product_id)
        if not row or row.get("deleted_at") is not None or not row.get("is_active", 1):
            raise InsufficientStock(f"product #{product_id}", 0, float(needed))
        available = decimal_qty(row.get("stock_qty", 0))
        if available < needed:
            raise InsufficientStock(str(row.get("name", product_id)), float(available), float(needed))


def apply_ledger_entry(
    cursor: Any,
    *,
    company_id: int,
    product_id: int,
    quantity_change: Any,
    transaction_type: str,
    reference_type: str,
    reference_id: int,
    actor_id: int,
    reason: str | None = None,
    occurred_at: datetime | None = None,
) -> None:
    """Insert a ledger row and update the materialized balance atomically.

    The conditional update refuses to drive stock negative, so even a caller
    that forgot to validate cannot silently oversell.
    """
    delta = decimal_qty(quantity_change)
    if delta == 0:
        raise ValidationError("A stock movement must be non-zero.")
    when = occurred_at or utc_now()
    cursor.execute(
        """
        INSERT INTO inventory_ledger
            (company_id, product_id, transaction_type, reference_type,
             reference_id, quantity_change, reason, occurred_at, created_by)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            company_id,
            product_id,
            transaction_type,
            reference_type,
            reference_id,
            delta,
            reason,
            when,
            actor_id,
        ),
    )
    cursor.execute(
        """
        UPDATE products
        SET stock_qty = stock_qty + %s,
            updated_at = %s,
            updated_by = %s
        WHERE company_id = %s AND product_id = %s AND stock_qty + %s >= 0
        """,
        (delta, when, actor_id, company_id, product_id, delta),
    )
    if cursor.rowcount != 1:
        cursor.execute(
            "SELECT name, stock_qty FROM products WHERE company_id = %s AND product_id = %s",
            (company_id, product_id),
        )
        row = cursor.fetchone()
        name = row[0] if row else f"product #{product_id}"
        available = row[1] if row else 0
        raise InsufficientStock(str(name), float(available), float(-delta))


def recompute_stock(conn: Any, company_id: int, product_id: int | None = None) -> int:
    """Rebuild materialized balances from the ledger. Returns rows changed.

    The balance is clamped at zero: a legacy ledger can sum to a negative value
    when opening rows are missing, but stock itself is never negative. The
    ledger is left untouched as the audit trail.
    """
    cursor = conn.cursor(dictionary=True)
    try:
        params: list[Any] = [company_id]
        where = "WHERE company_id = %s"
        if product_id is not None:
            where += " AND product_id = %s"
            params.append(int(product_id))
        cursor.execute(
            f"""
            SELECT p.product_id,
                   GREATEST(COALESCE(SUM(il.quantity_change), 0), 0) AS computed
            FROM products p
            LEFT JOIN inventory_ledger il
              ON il.product_id = p.product_id AND il.company_id = p.company_id
            {where}
            GROUP BY p.product_id
            """,
            tuple(params),
        )
        rows = cursor.fetchall()
        for row in rows:
            cursor.execute(
                "UPDATE products SET stock_qty = %s WHERE company_id = %s AND product_id = %s",
                (row["computed"], company_id, row["product_id"]),
            )
        conn.commit()
        return len(rows)
    finally:
        cursor.close()
