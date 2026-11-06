"""Purchase-order service."""

from __future__ import annotations

from typing import Any, Iterable

from core.auth import User
from core.cart import cart_total, group_by_vendor, normalize_cart
from core.errors import ValidationError
from core.stock import apply_ledger_entry
from core.time import local_date_to_utc, utc_now
from services.common import fetch_page, log_audit, require_connection

VALID_STATUSES = {"PENDING", "RECEIVED"}


def list_purchases(
    conn: Any | None,
    company_id: int,
    *,
    search: str = "",
    vendor: str = "All",
    status: str = "All",
    page: int = 1,
    page_size: int | None = None,
) -> tuple[list[dict], int]:
    conn = require_connection(conn)
    where = ["p.company_id = %s"]
    params: list[Any] = [company_id]
    if search:
        term = search.strip()
        raw_id = term.upper().replace("PO-", "").strip()
        if raw_id.isdigit():
            where.append("p.purchase_id = %s")
            params.append(int(raw_id))
        else:
            where.append("v.name LIKE %s")
            params.append(f"%{term}%")
    if vendor != "All":
        where.append("v.name = %s")
        params.append(vendor)
    if status != "All":
        where.append("p.status = %s")
        params.append(status)
    clause = " AND ".join(where)
    return fetch_page(
        conn,
        count_sql=(
            "SELECT COUNT(*) AS total FROM purchases p "
            "LEFT JOIN vendors v ON v.vendor_id = p.vendor_id "
            "AND v.company_id = p.company_id "
            f"WHERE {clause}"
        ),
        count_params=params,
        data_sql=f"""
            SELECT p.purchase_id, p.purchase_date, p.total_amount, p.status,
                   v.name AS vendor_name, COUNT(pi.id) AS items_count
            FROM purchases p
            LEFT JOIN vendors v ON v.vendor_id = p.vendor_id
              AND v.company_id = p.company_id
            LEFT JOIN purchase_items pi ON pi.purchase_id = p.purchase_id
              AND pi.company_id = p.company_id
            WHERE {clause}
            GROUP BY p.purchase_id, p.purchase_date, p.total_amount, p.status,
                     v.name
            ORDER BY p.purchase_id DESC
        """,
        data_params=params,
        page=page,
        page_size=page_size,
    )


def purchase_summary(conn: Any | None, company_id: int) -> dict[str, float]:
    conn = require_connection(conn)
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT COALESCE(SUM(CASE WHEN status = 'PENDING' THEN total_amount ELSE 0 END), 0) AS pending_value,
                   COALESCE(SUM(CASE WHEN status = 'RECEIVED' THEN total_amount ELSE 0 END), 0) AS received_value,
                   COALESCE(SUM(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END), 0) AS pending_count
            FROM purchases
            WHERE company_id = %s
            """,
            (company_id,),
        )
        row = cursor.fetchone() or {}
        return {
            "pending_value": float(row.get("pending_value") or 0),
            "received_value": float(row.get("received_value") or 0),
            "pending_count": int(row.get("pending_count") or 0),
        }
    finally:
        cursor.close()


def create_purchase_orders(
    conn: Any,
    company_id: int,
    actor: User,
    raw_items: Iterable[Any],
    *,
    purchase_date,
    status: str,
) -> list[int]:
    if status not in VALID_STATUSES:
        raise ValidationError("New purchase orders must be PENDING or RECEIVED.")
    items = normalize_cart(raw_items, company_id)
    if not items:
        raise ValidationError("The purchase cart is empty.")
    when = local_date_to_utc(purchase_date)
    now = utc_now()
    groups = group_by_vendor(items)
    cursor = conn.cursor()

    purchase_ids: list[int] = []
    try:
        for vendor_id, vendor_items in groups.items():
            total = cart_total(vendor_items)
            cursor.execute(
                """
                INSERT INTO purchases
                    (company_id, vendor_id, purchase_date, total_amount, status,
                     created_by, created_at, updated_at, updated_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    company_id,
                    vendor_id,
                    when,
                    total,
                    status,
                    actor.user_id,
                    now,
                    now,
                    actor.user_id,
                ),
            )
            purchase_id = int(cursor.lastrowid)
            purchase_ids.append(purchase_id)

            rows = [
                (
                    company_id,
                    purchase_id,
                    item.product_id,
                    item.quantity,
                    item.cost_price,
                    item.total,
                )
                for item in vendor_items
            ]
            cursor.executemany(
                """
                INSERT INTO purchase_items
                    (company_id, purchase_id, product_id, quantity,
                     cost_price, line_total)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                rows,
            )

            if status == "RECEIVED":
                for item in vendor_items:
                    apply_ledger_entry(
                        cursor,
                        company_id=company_id,
                        product_id=item.product_id,
                        quantity_change=item.quantity,
                        transaction_type="PURCHASE",
                        reference_type="PURCHASE",
                        reference_id=purchase_id,
                        actor_id=actor.user_id,
                        occurred_at=when,
                    )

        _mark_suggestions_ordered(
            cursor, company_id, actor.user_id, [item.product_id for item in items]
        )
        log_audit(
            conn,
            company_id=company_id,
            actor_id=actor.user_id,
            action="purchase.create",
            entity="purchase",
            entity_id=",".join(str(pid) for pid in purchase_ids),
            details={
                "orders": len(purchase_ids),
                "units": sum(item.quantity for item in items),
                "status": status,
            },
        )
        return purchase_ids
    finally:
        cursor.close()


def mark_received(conn: Any, company_id: int, actor: User, purchase_id: int) -> None:
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT purchase_id, status FROM purchases
            WHERE company_id = %s AND purchase_id = %s
            FOR UPDATE
            """,
            (company_id, int(purchase_id)),
        )
        purchase = cursor.fetchone()
        if not purchase:
            raise ValidationError("Purchase order not found.")
        if purchase["status"] != "PENDING":
            raise ValidationError("Only pending purchase orders can be received.")

        cursor.execute(
            "SELECT product_id, quantity FROM purchase_items "
            "WHERE company_id = %s AND purchase_id = %s",
            (company_id, int(purchase_id)),
        )
        items = cursor.fetchall()
        if not items:
            raise ValidationError("This purchase order has no items.")

        now = utc_now()
        for item in items:
            apply_ledger_entry(
                cursor,
                company_id=company_id,
                product_id=int(item["product_id"]),
                quantity_change=int(item["quantity"]),
                transaction_type="PURCHASE",
                reference_type="PURCHASE",
                reference_id=int(purchase_id),
                actor_id=actor.user_id,
                occurred_at=now,
            )
        cursor.execute(
            """
            UPDATE purchases
            SET status = 'RECEIVED', updated_at = %s, updated_by = %s
            WHERE company_id = %s AND purchase_id = %s
            """,
            (now, actor.user_id, company_id, int(purchase_id)),
        )
        log_audit(
            conn,
            company_id=company_id,
            actor_id=actor.user_id,
            action="purchase.receive",
            entity="purchase",
            entity_id=purchase_id,
        )
    finally:
        cursor.close()


def cancel_purchase(conn: Any, company_id: int, actor: User, purchase_id: int) -> None:
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT purchase_id, status FROM purchases
            WHERE company_id = %s AND purchase_id = %s
            FOR UPDATE
            """,
            (company_id, int(purchase_id)),
        )
        purchase = cursor.fetchone()
        if not purchase:
            raise ValidationError("Purchase order not found.")
        if purchase["status"] != "PENDING":
            raise ValidationError("Only pending purchase orders can be cancelled.")
        cursor.execute(
            "SELECT product_id FROM purchase_items "
            "WHERE company_id = %s AND purchase_id = %s",
            (company_id, int(purchase_id)),
        )
        product_ids = [int(row["product_id"]) for row in cursor.fetchall()]
        cursor.execute(
            """
            UPDATE purchases
            SET status = 'CANCELLED', updated_at = %s, updated_by = %s
            WHERE company_id = %s AND purchase_id = %s
            """,
            (utc_now(), actor.user_id, company_id, int(purchase_id)),
        )
        if product_ids:
            placeholders = ", ".join(["%s"] * len(product_ids))
            cursor.execute(
                f"""
                UPDATE reorder_suggestions
                SET status = 'PENDING', status_updated_at = %s,
                    status_updated_by = %s
                WHERE company_id = %s AND status = 'ORDERED'
                  AND product_id IN ({placeholders})
                """,
                (utc_now(), actor.user_id, company_id, *product_ids),
            )
        log_audit(
            conn,
            company_id=company_id,
            actor_id=actor.user_id,
            action="purchase.cancel",
            entity="purchase",
            entity_id=purchase_id,
        )
    finally:
        cursor.close()


def _mark_suggestions_ordered(
    cursor: Any, company_id: int, actor_id: int, product_ids: list[int]
) -> None:
    if not product_ids:
        return
    placeholders = ", ".join(["%s"] * len(product_ids))
    cursor.execute(
        f"""
        UPDATE reorder_suggestions
        SET status = 'ORDERED', status_updated_at = %s, status_updated_by = %s
        WHERE company_id = %s AND status = 'PENDING'
          AND product_id IN ({placeholders})
        """,
        (utc_now(), actor_id, company_id, *product_ids),
    )
