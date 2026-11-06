"""Vendor service with full create/read/update/archive support."""

from __future__ import annotations

from typing import Any

from core.auth import User, require_owner
from core.errors import ValidationError
from core.time import utc_now
from services.common import log_audit, require_connection


def list_vendors(
    conn: Any | None, company_id: int, *, include_inactive: bool = False
) -> list[dict]:
    conn = require_connection(conn)
    cursor = conn.cursor(dictionary=True)
    try:
        where = "company_id = %s AND deleted_at IS NULL"
        if not include_inactive:
            where += " AND is_active = 1"
        cursor.execute(
            f"""
            SELECT vendor_id, name, contact, address, lead_time_days, is_active
            FROM vendors
            WHERE {where}
            ORDER BY name ASC
            """,
            (company_id,),
        )
        return list(cursor.fetchall())
    finally:
        cursor.close()


def get_vendor(conn: Any | None, company_id: int, vendor_id: int) -> dict | None:
    conn = require_connection(conn)
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT * FROM vendors WHERE company_id = %s AND vendor_id = %s",
            (company_id, vendor_id),
        )
        return cursor.fetchone()
    finally:
        cursor.close()


def create_vendor(
    conn: Any,
    company_id: int,
    actor: User,
    *,
    name: str,
    contact: str = "",
    address: str = "",
    lead_time_days: int = 0,
) -> int:
    require_owner(actor)
    if not name or not name.strip():
        raise ValidationError("Vendor name is required.")
    cursor = conn.cursor()
    try:
        now = utc_now()
        cursor.execute(
            """
            INSERT INTO vendors
                (company_id, name, contact, address, lead_time_days, is_active,
                 created_by, updated_by, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, 1, %s, %s, %s, %s)
            """,
            (
                company_id,
                name.strip(),
                contact.strip(),
                address.strip(),
                int(lead_time_days),
                actor.user_id,
                actor.user_id,
                now,
                now,
            ),
        )
        vendor_id = int(cursor.lastrowid)
        log_audit(
            conn,
            company_id=company_id,
            actor_id=actor.user_id,
            action="vendor.create",
            entity="vendor",
            entity_id=vendor_id,
            details={"name": name.strip()},
        )
        return vendor_id
    finally:
        cursor.close()


def update_vendor(
    conn: Any,
    company_id: int,
    actor: User,
    vendor_id: int,
    *,
    name: str,
    contact: str = "",
    address: str = "",
    lead_time_days: int = 0,
    is_active: bool = True,
) -> None:
    require_owner(actor)
    if not name or not name.strip():
        raise ValidationError("Vendor name is required.")
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE vendors
            SET name = %s, contact = %s, address = %s, lead_time_days = %s,
                is_active = %s, updated_at = %s, updated_by = %s
            WHERE company_id = %s AND vendor_id = %s AND deleted_at IS NULL
            """,
            (
                name.strip(),
                contact.strip(),
                address.strip(),
                int(lead_time_days),
                1 if is_active else 0,
                utc_now(),
                actor.user_id,
                company_id,
                vendor_id,
            ),
        )
        if cursor.rowcount != 1:
            raise ValidationError("Vendor not found.")
        log_audit(
            conn,
            company_id=company_id,
            actor_id=actor.user_id,
            action="vendor.update",
            entity="vendor",
            entity_id=vendor_id,
        )
    finally:
        cursor.close()


def archive_vendor(conn: Any, company_id: int, actor: User, vendor_id: int) -> None:
    require_owner(actor)
    cursor = conn.cursor()
    try:
        now = utc_now()
        cursor.execute(
            """
            UPDATE vendors
            SET is_active = 0, deleted_at = %s, updated_at = %s, updated_by = %s
            WHERE company_id = %s AND vendor_id = %s AND deleted_at IS NULL
            """,
            (now, now, actor.user_id, company_id, vendor_id),
        )
        if cursor.rowcount != 1:
            raise ValidationError("Vendor not found or already archived.")
        log_audit(
            conn,
            company_id=company_id,
            actor_id=actor.user_id,
            action="vendor.archive",
            entity="vendor",
            entity_id=vendor_id,
        )
    finally:
        cursor.close()


def primary_vendor_for(
    conn: Any | None, company_id: int, product_id: int
) -> dict | None:
    conn = require_connection(conn)
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT v.vendor_id, v.name, pv.cost_price
            FROM product_vendors pv
            JOIN vendors v
              ON v.vendor_id = pv.vendor_id AND v.company_id = pv.company_id
            WHERE pv.company_id = %s AND pv.product_id = %s
              AND v.is_active = 1 AND v.deleted_at IS NULL
            ORDER BY pv.is_primary DESC, pv.cost_price ASC
            LIMIT 1
            """,
            (company_id, product_id),
        )
        return cursor.fetchone()
    finally:
        cursor.close()


def set_product_vendor(
    conn: Any,
    company_id: int,
    actor: User,
    product_id: int,
    vendor_id: int,
    *,
    cost_price: Any = 0,
    is_primary: bool = False,
) -> None:
    require_owner(actor)
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO product_vendors
                (company_id, product_id, vendor_id, cost_price, is_primary, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                cost_price = VALUES(cost_price), is_primary = VALUES(is_primary)
            """,
            (
                company_id,
                product_id,
                vendor_id,
                cost_price,
                1 if is_primary else 0,
                utc_now(),
            ),
        )
    finally:
        cursor.close()
