"""Catalog (product) service."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from core.auth import User, require_owner
from core.cart import money
from core.config import DEFAULT_REORDER_THRESHOLD
from core.errors import ValidationError
from core.stock import apply_ledger_entry, lock_products
from core.time import utc_now
from services.common import fetch_page, log_audit, require_connection


def list_products(
    conn: Any | None,
    company_id: int,
    *,
    search: str = "",
    category: str = "All Categories",
    status: str = "All Statuses",
    page: int = 1,
    page_size: int | None = None,
) -> tuple[list[dict], int]:
    conn = require_connection(conn)
    where = ["p.company_id = %s"]
    params: list[Any] = [company_id]
    if search:
        where.append("(p.name LIKE %s OR p.sku LIKE %s)")
        like = f"%{search}%"
        params.extend([like, like])
    if category and category != "All Categories":
        where.append("p.category = %s")
        params.append(category)
    if status == "Active":
        where.append("p.is_active = 1 AND p.deleted_at IS NULL")
    elif status == "Inactive":
        where.append("p.is_active = 0 AND p.deleted_at IS NULL")
    elif status == "Archived":
        where.append("p.deleted_at IS NOT NULL")
    else:
        where.append("p.deleted_at IS NULL")
    clause = " AND ".join(where)
    return fetch_page(
        conn,
        count_sql=f"SELECT COUNT(*) AS total FROM products p WHERE {clause}",
        count_params=params,
        data_sql=f"""
            SELECT p.product_id, p.sku, p.name, p.category, p.unit,
                   p.selling_price, p.reorder_threshold, p.stock_qty,
                   p.is_active, p.deleted_at
            FROM products p
            WHERE {clause}
            ORDER BY p.product_id DESC
        """,
        data_params=params,
        page=page,
        page_size=page_size,
    )


def list_categories(conn: Any | None, company_id: int) -> list[str]:
    conn = require_connection(conn)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT DISTINCT category FROM products WHERE company_id = %s "
            "AND deleted_at IS NULL AND category IS NOT NULL ORDER BY category",
            (company_id,),
        )
        return [row[0] for row in cursor.fetchall()]
    finally:
        cursor.close()


def get_product(conn: Any | None, company_id: int, product_id: int) -> dict | None:
    conn = require_connection(conn)
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT * FROM products WHERE company_id = %s AND product_id = %s",
            (company_id, product_id),
        )
        return cursor.fetchone()
    finally:
        cursor.close()


def create_product(
    conn: Any,
    company_id: int,
    actor: User,
    *,
    sku: str,
    name: str,
    category: str,
    unit: str,
    selling_price: Any,
    reorder_threshold: int,
    is_active: bool = True,
    opening_stock: int = 0,
) -> int:
    require_owner(actor)
    sku, name = sku.strip(), name.strip()
    if not sku or not name:
        raise ValidationError("SKU and product name are required.")
    price = money(selling_price)
    if price < 0:
        raise ValidationError("Selling price cannot be negative.")
    if int(reorder_threshold) < 0:
        raise ValidationError("Reorder threshold cannot be negative.")
    if int(opening_stock) < 0:
        raise ValidationError("Opening stock cannot be negative.")

    cursor = conn.cursor()
    try:
        now = utc_now()
        cursor.execute(
            """
            INSERT INTO products
                (company_id, sku, name, category, unit, selling_price,
                 reorder_threshold, stock_qty, is_active, created_by,
                 updated_by, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 0, %s, %s, %s, %s, %s)
            """,
            (
                company_id,
                sku,
                name,
                category,
                unit,
                price,
                int(reorder_threshold),
                1 if is_active else 0,
                actor.user_id,
                actor.user_id,
                now,
                now,
            ),
        )
        product_id = int(cursor.lastrowid)
        if opening_stock:
            apply_ledger_entry(
                cursor,
                company_id=company_id,
                product_id=product_id,
                quantity_change=int(opening_stock),
                transaction_type="ADJUSTMENT",
                reference_type="PRODUCT",
                reference_id=product_id,
                actor_id=actor.user_id,
                reason="Opening stock",
                occurred_at=now,
            )
        log_audit(
            conn,
            company_id=company_id,
            actor_id=actor.user_id,
            action="product.create",
            entity="product",
            entity_id=product_id,
            details={"sku": sku, "opening_stock": opening_stock},
        )
        return product_id
    finally:
        cursor.close()


def update_product(
    conn: Any,
    company_id: int,
    actor: User,
    product_id: int,
    *,
    name: str,
    category: str,
    unit: str,
    selling_price: Any,
    reorder_threshold: int,
    is_active: bool,
) -> None:
    require_owner(actor)
    if not name.strip():
        raise ValidationError("Product name is required.")
    price = money(selling_price)
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE products
            SET name = %s, category = %s, unit = %s, selling_price = %s,
                reorder_threshold = %s, is_active = %s, updated_at = %s,
                updated_by = %s
            WHERE company_id = %s AND product_id = %s AND deleted_at IS NULL
            """,
            (
                name.strip(),
                category,
                unit,
                price,
                int(reorder_threshold),
                1 if is_active else 0,
                utc_now(),
                actor.user_id,
                company_id,
                product_id,
            ),
        )
        if cursor.rowcount != 1:
            raise ValidationError("Product not found.")
        log_audit(
            conn,
            company_id=company_id,
            actor_id=actor.user_id,
            action="product.update",
            entity="product",
            entity_id=product_id,
        )
    finally:
        cursor.close()


def archive_product(conn: Any, company_id: int, actor: User, product_id: int) -> None:
    """Soft delete. History and ledger rows are never removed."""
    require_owner(actor)
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE products
            SET is_active = 0, deleted_at = %s, updated_at = %s, updated_by = %s
            WHERE company_id = %s AND product_id = %s AND deleted_at IS NULL
            """,
            (utc_now(), utc_now(), actor.user_id, company_id, product_id),
        )
        if cursor.rowcount != 1:
            raise ValidationError("Product not found or already archived.")
        log_audit(
            conn,
            company_id=company_id,
            actor_id=actor.user_id,
            action="product.archive",
            entity="product",
            entity_id=product_id,
        )
    finally:
        cursor.close()


def set_active(conn: Any, company_id: int, actor: User, product_id: int, active: bool) -> None:
    require_owner(actor)
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE products
            SET is_active = %s, updated_at = %s, updated_by = %s
            WHERE company_id = %s AND product_id = %s AND deleted_at IS NULL
            """,
            (1 if active else 0, utc_now(), actor.user_id, company_id, product_id),
        )
        if cursor.rowcount != 1:
            raise ValidationError("Product not found.")
    finally:
        cursor.close()


def adjust_stock(
    conn: Any,
    company_id: int,
    actor: User,
    *,
    product_id: int,
    quantity_change: int,
    reason: str,
) -> None:
    require_owner(actor)
    if int(quantity_change) == 0:
        raise ValidationError("Adjustment quantity must be non-zero.")
    if not reason or not reason.strip():
        raise ValidationError("A reason is required for stock adjustments.")
    cursor = conn.cursor(dictionary=True)
    try:
        products = lock_products(cursor, company_id, [product_id])
        if product_id not in products:
            raise ValidationError("Product not found.")
        now = utc_now()
        apply_ledger_entry(
            cursor,
            company_id=company_id,
            product_id=product_id,
            quantity_change=int(quantity_change),
            transaction_type="ADJUSTMENT",
            reference_type="MANUAL",
            reference_id=0,
            actor_id=actor.user_id,
            reason=reason.strip(),
            occurred_at=now,
        )
        log_audit(
            conn,
            company_id=company_id,
            actor_id=actor.user_id,
            action="stock.adjust",
            entity="product",
            entity_id=product_id,
            details={"quantity_change": quantity_change, "reason": reason.strip()},
        )
    finally:
        cursor.close()


def bulk_create_products(
    conn: Any, company_id: int, actor: User, rows: Iterable[Mapping[str, Any]]
) -> tuple[int, int]:
    require_owner(actor)
    records: list[tuple] = []
    for index, row in enumerate(rows, start=1):
        try:
            sku = str(row["SKU"]).strip()
            name = str(row["Name"]).strip()
            category = str(row["Category"]).strip()
            unit = str(row["Unit"]).strip()
            price = money(row["Price"])
            reorder = int(float(row.get("Reorder_Pt", DEFAULT_REORDER_THRESHOLD)))
            if not sku or not name:
                raise ValueError("SKU and Name are required")
        except Exception as exc:  # noqa: BLE001 - report the row number
            raise ValidationError(f"Row {index}: {exc}") from exc
        now = utc_now()
        records.append(
            (
                company_id,
                sku,
                name,
                category,
                unit,
                price,
                reorder,
                actor.user_id,
                actor.user_id,
                now,
                now,
            )
        )
    if not records:
        raise ValidationError("The CSV file has no data rows.")

    cursor = conn.cursor()
    try:
        cursor.executemany(
            """
            INSERT INTO products
                (company_id, sku, name, category, unit, selling_price,
                 reorder_threshold, stock_qty, is_active, created_by,
                 updated_by, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 0, 1, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                name = VALUES(name), category = VALUES(category),
                unit = VALUES(unit), selling_price = VALUES(selling_price),
                reorder_threshold = VALUES(reorder_threshold),
                is_active = 1, deleted_at = NULL,
                updated_at = VALUES(updated_at), updated_by = VALUES(updated_by)
            """,
            records,
        )
        affected = int(cursor.rowcount)
        log_audit(
            conn,
            company_id=company_id,
            actor_id=actor.user_id,
            action="product.bulk_import",
            entity="product",
            details={"rows": len(records), "affected": affected},
        )
        return len(records), affected
    finally:
        cursor.close()


def list_active_products(
    conn: Any | None, company_id: int, limit: int = 500
) -> list[dict]:
    conn = require_connection(conn)
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT product_id, sku, name, category, selling_price, stock_qty,
                   reorder_threshold
            FROM products
            WHERE company_id = %s AND is_active = 1 AND deleted_at IS NULL
            ORDER BY name
            LIMIT %s
            """,
            (company_id, int(limit)),
        )
        return list(cursor.fetchall())
    finally:
        cursor.close()


def search_products(
    conn: Any | None, company_id: int, term: str, limit: int = 5
) -> list[dict]:
    conn = require_connection(conn)
    cursor = conn.cursor(dictionary=True)
    try:
        like = f"%{term}%"
        cursor.execute(
            """
            SELECT product_id, name, sku, category, selling_price, stock_qty,
                   reorder_threshold
            FROM products
            WHERE company_id = %s AND deleted_at IS NULL
              AND (name LIKE %s OR sku LIKE %s)
            ORDER BY name
            LIMIT %s
            """,
            (company_id, like, like, int(limit)),
        )
        return list(cursor.fetchall())
    finally:
        cursor.close()


def low_stock_rows(conn: Any | None, company_id: int, include_out: bool = True) -> list[dict]:
    conn = require_connection(conn)
    cursor = conn.cursor(dictionary=True)
    try:
        operator = "<= " if include_out else "< "
        cursor.execute(
            f"""
            SELECT name, sku, category, stock_qty, reorder_threshold
            FROM products
            WHERE company_id = %s AND is_active = 1 AND deleted_at IS NULL
              AND stock_qty {operator} reorder_threshold
            ORDER BY stock_qty ASC
            """,
            (company_id,),
        )
        return list(cursor.fetchall())
    finally:
        cursor.close()
