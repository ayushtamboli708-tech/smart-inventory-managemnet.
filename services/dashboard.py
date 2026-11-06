"""Dashboard aggregate queries.

All data for the landing page is fetched through the single scoped connection.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from core.config import DEFAULT_REORDER_THRESHOLD, OVERSTOCK_MIN_UNITS, OVERSTOCK_MULTIPLIER
from core.time import local_days_ago_utc, utc_now, local_today
from services.common import require_connection


def _numeric(frame: pd.DataFrame, *columns: str) -> pd.DataFrame:
    for column in columns:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce").astype(float)
    return frame


def get_dashboard_summary(conn: Any | None, company_id: int) -> dict[str, Any]:
    conn = require_connection(conn)
    data: dict[str, Any] = {
        "kpi": {"active": 0, "all": 0, "low": 0, "out": 0, "reorder": 0, "overstock": 0},
        "health": {"score": 100, "qty_hand": 0, "po_value": 0},
        "top_selling": pd.DataFrame(columns=["Product", "Sales"]),
        "alerts": pd.DataFrame(),
        "forecast_preview": pd.DataFrame(columns=["Day", "Expected Sales"]),
        "revenue_trend": pd.DataFrame(columns=["Day", "Revenue"]),
        "recent_sales": [],
        "last_forecast": None,
    }
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT COUNT(*) AS total, SUM(is_active = 1) AS active FROM products "
            "WHERE company_id = %s AND deleted_at IS NULL",
            (company_id,),
        )
        counts = cursor.fetchone() or {}
        data["kpi"]["all"] = int(counts.get("total") or 0)
        data["kpi"]["active"] = int(counts.get("active") or 0)

        cursor.execute(
            """
            SELECT product_id, name, sku, stock_qty,
                   COALESCE(reorder_threshold, %s) AS reorder_threshold,
                   selling_price
            FROM products
            WHERE company_id = %s AND is_active = 1 AND deleted_at IS NULL
            ORDER BY stock_qty ASC
            """,
            (DEFAULT_REORDER_THRESHOLD, company_id),
        )
        stock_rows = cursor.fetchall()
        out_stock = [row for row in stock_rows if float(row["stock_qty"]) <= 0]
        low_stock = [
            row
            for row in stock_rows
            if 0 < float(row["stock_qty"]) <= float(row["reorder_threshold"])
        ]
        overstock = [
            row
            for row in stock_rows
            if float(row["stock_qty"]) > float(row["reorder_threshold"]) * OVERSTOCK_MULTIPLIER
            and float(row["stock_qty"]) > OVERSTOCK_MIN_UNITS
        ]
        data["kpi"]["out"] = len(out_stock)
        data["kpi"]["low"] = len(low_stock)
        data["kpi"]["reorder"] = len(out_stock) + len(low_stock)
        data["kpi"]["overstock"] = len(overstock)

        active = data["kpi"]["active"]
        data["health"]["score"] = (
            int(((active - data["kpi"]["reorder"]) / active) * 100) if active else 100
        )
        data["health"]["qty_hand"] = float(sum(float(row["stock_qty"]) for row in stock_rows))

        alerts = pd.DataFrame(stock_rows).head(5) if stock_rows else pd.DataFrame()
        data["alerts"] = alerts

        cursor.execute(
            "SELECT COALESCE(SUM(total_amount), 0) AS total FROM purchases "
            "WHERE company_id = %s AND status = 'PENDING'",
            (company_id,),
        )
        data["health"]["po_value"] = float((cursor.fetchone() or {}).get("total") or 0)

        cursor.execute(
            """
            SELECT p.name AS Product, SUM(si.quantity) AS Sales
            FROM sale_items si
            JOIN sales s ON s.sale_id = si.sale_id AND s.company_id = si.company_id
            JOIN products p ON p.product_id = si.product_id AND p.company_id = si.company_id
            WHERE si.company_id = %s AND s.status = 'COMPLETED'
            GROUP BY p.product_id, p.name
            ORDER BY Sales DESC
            LIMIT 5
            """,
            (company_id,),
        )
        top_selling = cursor.fetchall()
        if top_selling:
            data["top_selling"] = _numeric(pd.DataFrame(top_selling), "Sales")

        cursor.execute(
            """
            SELECT f.forecast_date AS Day, SUM(f.predicted_demand) AS `Expected Sales`
            FROM forecasts f
            WHERE f.company_id = %s AND f.run_id = (
                SELECT MAX(r.run_id) FROM forecast_runs r
                WHERE r.company_id = %s AND r.status IN ('COMPLETED', 'PARTIAL')
            )
            GROUP BY f.forecast_date
            ORDER BY f.forecast_date ASC
            LIMIT 7
            """,
            (company_id, company_id),
        )
        forecast_rows = cursor.fetchall()
        if forecast_rows:
            data["forecast_preview"] = _numeric(
                pd.DataFrame(forecast_rows), "Expected Sales"
            )

        cursor.execute(
            """
            SELECT r.run_id, r.started_at, r.finished_at, r.mape, r.rmse,
                   r.products_processed, r.products_failed
            FROM forecast_runs r
            WHERE r.company_id = %s
            ORDER BY r.run_id DESC
            LIMIT 1
            """,
            (company_id,),
        )
        data["last_forecast"] = cursor.fetchone()

        since = local_days_ago_utc(30)
        cursor.execute(
            """
            SELECT DATE(sale_date) AS Day, SUM(total_amount) AS Revenue
            FROM sales
            WHERE company_id = %s AND status = 'COMPLETED' AND sale_date >= %s
            GROUP BY DATE(sale_date)
            ORDER BY Day ASC
            """,
            (company_id, since),
        )
        revenue_rows = cursor.fetchall()
        if revenue_rows:
            data["revenue_trend"] = _numeric(pd.DataFrame(revenue_rows), "Revenue")

        cursor.execute(
            """
            SELECT sale_id, sale_date, total_amount, status
            FROM sales
            WHERE company_id = %s
            ORDER BY sale_id DESC
            LIMIT 5
            """,
            (company_id,),
        )
        data["recent_sales"] = cursor.fetchall()
    finally:
        cursor.close()
    return data


def top_selling(conn: Any | None, company_id: int, period: str = "All Time") -> pd.DataFrame:
    conn = require_connection(conn)
    cursor = conn.cursor(dictionary=True)
    try:
        where = "si.company_id = %s AND s.status = 'COMPLETED'"
        params: list[Any] = [company_id]
        if period == "This Month":
            where += " AND s.sale_date >= %s"
            params.append(local_days_ago_utc(30))
        cursor.execute(
            f"""
            SELECT p.name AS Product, SUM(si.quantity) AS Sales
            FROM sale_items si
            JOIN sales s ON s.sale_id = si.sale_id AND s.company_id = si.company_id
            JOIN products p ON p.product_id = si.product_id
              AND p.company_id = si.company_id
            WHERE {where}
            GROUP BY p.product_id, p.name
            ORDER BY Sales DESC
            LIMIT 5
            """,
            tuple(params),
        )
        rows = cursor.fetchall()
        return (
            _numeric(pd.DataFrame(rows), "Sales")
            if rows
            else pd.DataFrame(columns=["Product", "Sales"])
        )
    finally:
        cursor.close()


def inventory_snapshot(conn: Any | None, company_id: int) -> list[dict]:
    conn = require_connection(conn)
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT name, sku, category, stock_qty, reorder_threshold, selling_price
            FROM products
            WHERE company_id = %s AND is_active = 1 AND deleted_at IS NULL
            ORDER BY stock_qty ASC
            """,
            (company_id,),
        )
        return list(cursor.fetchall())
    finally:
        cursor.close()


def data_freshness() -> str:
    return utc_now().strftime("%Y-%m-%d %H:%M UTC")


def local_date_label() -> str:
    return local_today().strftime("%d %b %Y")
