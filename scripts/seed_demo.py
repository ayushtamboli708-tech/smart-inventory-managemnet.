"""Load the demo catalog and generate 120 days of sales for local use."""

from __future__ import annotations

import random
import sys
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import mysql.connector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import db  # noqa: E402
from core.time import local_date_to_utc, local_today  # noqa: E402


def run_sql_file(conn, path: Path) -> None:
    lines = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if not line.strip().startswith("--")
    ]
    cursor = conn.cursor()
    try:
        for statement in "\n".join(lines).split(";"):
            if statement.strip():
                cursor.execute(statement)
        conn.commit()
    finally:
        cursor.close()


def generate_sales(conn, days: int = 120) -> int:
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT COUNT(*) AS total FROM sales WHERE company_id = 1")
        if int((cursor.fetchone() or {}).get("total") or 0) > 0:
            print("Sales already exist; generation skipped.")
            return 0

        cursor.execute(
            """
            SELECT product_id, sku, name, selling_price
            FROM products
            WHERE company_id = 1 AND deleted_at IS NULL
            ORDER BY product_id
            """
        )
        products = list(cursor.fetchall())
        if not products:
            print("No products found. Run seed.sql first.")
            return 0

        bases = [3.0, 1.8, 1.2, 4.0, 0.6]
        rng = random.Random(42)
        created = 0
        today = local_today()
        for offset in range(days, 0, -1):
            day = today - timedelta(days=offset)
            weekday_factor = 1.25 if day.weekday() >= 5 else 1.0
            trend = 1.0 + (days - offset) / days * 0.25
            for index, product in enumerate(products):
                base = bases[index % len(bases)]
                qty = round(base * weekday_factor * trend + rng.uniform(-1.0, 1.5))
                qty = max(0, qty)
                if qty == 0:
                    continue
                price = Decimal(str(product["selling_price"]))
                total = (price * qty).quantize(Decimal("0.01"))
                when = local_date_to_utc(day, at_hour=13 + (index % 6))
                cursor.execute(
                    """
                    INSERT INTO sales
                        (company_id, sale_date, total_amount, status, created_by,
                         created_at, updated_at, updated_by)
                    VALUES (1, %s, %s, 'COMPLETED', 2, %s, %s, 2)
                    """,
                    (when, total, when, when),
                )
                sale_id = int(cursor.lastrowid)
                cursor.execute(
                    """
                    INSERT INTO sale_items
                        (company_id, sale_id, product_id, quantity, unit_price, line_total)
                    VALUES (1, %s, %s, %s, %s, %s)
                    """,
                    (sale_id, product["product_id"], qty, price, total),
                )
                cursor.execute(
                    """
                    INSERT INTO inventory_ledger
                        (company_id, product_id, transaction_type, reference_type,
                         reference_id, quantity_change, occurred_at, created_by)
                    VALUES (1, %s, 'SALE', 'SALE', %s, %s, %s, 2)
                    """,
                    (product["product_id"], sale_id, -qty, when),
                )
                cursor.execute(
                    "UPDATE products SET stock_qty = stock_qty - %s WHERE product_id = %s AND company_id = 1",
                    (qty, product["product_id"]),
                )
                created += 1
            if offset % 20 == 0:
                conn.commit()
        conn.commit()
        print(f"Generated {created} demo sales across {days} days.")
        return created
    finally:
        cursor.close()


def main() -> int:
    config = db.get_db_config()
    conn = mysql.connector.connect(**config, autocommit=False)
    try:
        run_sql_file(conn, ROOT / "seed.sql")
        generate_sales(conn, days=120)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
