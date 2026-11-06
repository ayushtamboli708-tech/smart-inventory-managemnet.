"""Sales service: stock-checked checkout, refunds, and reporting."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable, Mapping

from core.auth import User, require_owner
from core.errors import ValidationError
from core.stock import apply_ledger_entry, lock_products, validate_available
from core.time import local_day_bounds_utc, local_days_ago_utc, local_today, utc_now
from services.common import fetch_page, log_audit, require_connection


def _filters(company_id: int, search: str, date_filter: str) -> tuple[str, list[Any]]:
    where = ["s.company_id = %s"]
    params: list[Any] = [company_id]
    if search:
        term = search.strip()
        raw_id = term.upper().replace("SALE-", "").strip()
        if raw_id.isdigit():
            where.append("s.sale_id = %s")
            params.append(int(raw_id))
        else:
            where.append(
                "EXISTS (SELECT 1 FROM sale_items si2 "
                "JOIN products p2 ON p2.product_id = si2.product_id "
                "AND p2.company_id = si2.company_id "
                "WHERE si2.sale_id = s.sale_id AND si2.company_id = s.company_id "
                "AND p2.name LIKE %s)"
            )
            params.append(f"%{term}%")
    if date_filter == "Today":
        start, end = local_day_bounds_utc(local_today())
        where.append("s.sale_date >= %s AND s.sale_date < %s")
        params.extend([start, end])
    elif date_filter == "Last 7 Days":
        where.append("s.sale_date >= %s")
        params.append(local_days_ago_utc(7))
    return " AND ".join(where), params


def list_sales(
    conn: Any | None,
    company_id: int,
    *,
    search: str = "",
    date_filter: str = "All Time",
    page: int = 1,
    page_size: int | None = None,
) -> tuple[list[dict], int]:
    conn = require_connection(conn)
    clause, params = _filters(company_id, search, date_filter)
    return fetch_page(
        conn,
        count_sql=f"SELECT COUNT(*) AS total FROM sales s WHERE {clause}",
        count_params=params,
        data_sql=f"""
            SELECT s.sale_id, s.sale_date, s.total_amount, s.status,
                   COUNT(si.id) AS items_count,
                   COALESCE(SUM(si.quantity), 0) AS units_count
            FROM sales s
            LEFT JOIN sale_items si
              ON si.sale_id = s.sale_id AND si.company_id = s.company_id
            WHERE {clause}
            GROUP BY s.sale_id, s.sale_date, s.total_amount, s.status
            ORDER BY s.sale_id DESC
        """,
        data_params=params,
        page=page,
        page_size=page_size,
    )


def export_sales_rows(
    conn: Any | None,
    company_id: int,
    *,
    search: str = "",
    date_filter: str = "All Time",
    limit: int = 10000,
) -> list[dict]:
    conn = require_connection(conn)
    clause, params = _filters(company_id, search, date_filter)
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            f"""
            SELECT s.sale_id, s.sale_date, s.total_amount, s.status,
                   COUNT(si.id) AS items_count,
                   COALESCE(SUM(si.quantity), 0) AS units_count
            FROM sales s
            LEFT JOIN sale_items si
              ON si.sale_id = s.sale_id AND si.company_id = s.company_id
            WHERE {clause}
            GROUP BY s.sale_id, s.sale_date, s.total_amount, s.status
            ORDER BY s.sale_id DESC
            LIMIT %s
            """,
            (*params, int(limit)),
        )
        return list(cursor.fetchall())
    finally:
        cursor.close()


def sales_summary(
    conn: Any | None, company_id: int, *, search: str = "", date_filter: str = "All Time"
) -> dict[str, float]:
    conn = require_connection(conn)
    clause, params = _filters(company_id, search, date_filter)
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            f"""
            SELECT COALESCE(SUM(s.total_amount), 0) AS revenue,
                   COUNT(*) AS transactions
            FROM sales s
            WHERE {clause} AND s.status = 'COMPLETED'
            """,
            tuple(params),
        )
        row = cursor.fetchone() or {}
        return {
            "revenue": float(row.get("revenue") or 0),
            "transactions": int(row.get("transactions") or 0),
        }
    finally:
        cursor.close()


def get_sale_items(conn: Any | None, company_id: int, sale_id: int) -> list[dict]:
    conn = require_connection(conn)
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT si.id, si.product_id, p.name, p.sku, si.quantity,
                   si.unit_price, si.line_total
            FROM sale_items si
            JOIN products p ON p.product_id = si.product_id
              AND p.company_id = si.company_id
            WHERE si.company_id = %s AND si.sale_id = %s
            ORDER BY si.id
            """,
            (company_id, int(sale_id)),
        )
        return list(cursor.fetchall())
    finally:
        cursor.close()


def complete_sale(
    conn: Any,
    company_id: int,
    actor: User,
    items: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Create a sale and decrement stock inside the caller's transaction.

    Quantities are aggregated per product, product rows are locked, and the
    price is always read from the catalog rather than trusted from the browser.
    """
    lines: dict[int, int] = {}
    for item in items:
        try:
            product_id = int(item["product_id"])
            qty = int(item["quantity"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationError("Every sale line needs a product and a quantity.") from exc
        if qty <= 0:
            raise ValidationError("Sale quantity must be greater than zero.")
        lines[product_id] = lines.get(product_id, 0) + qty
    if not lines:
        raise ValidationError("The sale cart is empty.")

    cursor = conn.cursor(dictionary=True)
    try:
        products = lock_products(cursor, company_id, lines.keys())
        required = {pid: Decimal(qty) for pid, qty in lines.items()}
        validate_available(products, required)

        total = sum(
            (Decimal(str(products[pid]["selling_price"])) * qty for pid, qty in lines.items()),
            Decimal("0.00"),
        ).quantize(Decimal("0.01"))
        now = utc_now()
        cursor.execute(
            """
            INSERT INTO sales
                (company_id, sale_date, total_amount, status, created_by,
                 created_at, updated_at, updated_by)
            VALUES (%s, %s, %s, 'COMPLETED', %s, %s, %s, %s)
            """,
            (company_id, now, total, actor.user_id, now, now, actor.user_id),
        )
        sale_id = int(cursor.lastrowid)

        sale_rows = []
        for product_id, qty in lines.items():
            unit_price = Decimal(str(products[product_id]["selling_price"]))
            sale_rows.append(
                (
                    company_id,
                    sale_id,
                    product_id,
                    qty,
                    unit_price,
                    (unit_price * qty).quantize(Decimal("0.01")),
                )
            )
        cursor.executemany(
            """
            INSERT INTO sale_items
                (company_id, sale_id, product_id, quantity, unit_price, line_total)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            sale_rows,
        )

        for product_id, qty in lines.items():
            apply_ledger_entry(
                cursor,
                company_id=company_id,
                product_id=product_id,
                quantity_change=-qty,
                transaction_type="SALE",
                reference_type="SALE",
                reference_id=sale_id,
                actor_id=actor.user_id,
                occurred_at=now,
            )

        log_audit(
            conn,
            company_id=company_id,
            actor_id=actor.user_id,
            action="sale.complete",
            entity="sale",
            entity_id=sale_id,
            details={"total": str(total), "units": sum(lines.values())},
        )
        return {"sale_id": sale_id, "total": total, "units": sum(lines.values())}
    finally:
        cursor.close()


def refund_sale(conn: Any, company_id: int, actor: User, sale_id: int) -> None:
    """Full refund: restore stock and mark the sale REFUNDED."""
    require_owner(actor)
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT sale_id, status FROM sales
            WHERE company_id = %s AND sale_id = %s
            FOR UPDATE
            """,
            (company_id, int(sale_id)),
        )
        sale = cursor.fetchone()
        if not sale:
            raise ValidationError("Sale not found.")
        if sale["status"] != "COMPLETED":
            raise ValidationError("Only completed sales can be refunded.")

        cursor.execute(
            "SELECT product_id, quantity FROM sale_items "
            "WHERE company_id = %s AND sale_id = %s",
            (company_id, int(sale_id)),
        )
        lines = cursor.fetchall()
        if not lines:
            raise ValidationError("This sale has no line items.")

        now = utc_now()
        for line in lines:
            apply_ledger_entry(
                cursor,
                company_id=company_id,
                product_id=int(line["product_id"]),
                quantity_change=int(line["quantity"]),
                transaction_type="REFUND",
                reference_type="SALE",
                reference_id=int(sale_id),
                actor_id=actor.user_id,
                reason="Full refund",
                occurred_at=now,
            )

        cursor.execute(
            """
            UPDATE sales
            SET status = 'REFUNDED', updated_at = %s, updated_by = %s
            WHERE company_id = %s AND sale_id = %s
            """,
            (now, actor.user_id, company_id, int(sale_id)),
        )
        log_audit(
            conn,
            company_id=company_id,
            actor_id=actor.user_id,
            action="sale.refund",
            entity="sale",
            entity_id=sale_id,
        )
    finally:
        cursor.close()
