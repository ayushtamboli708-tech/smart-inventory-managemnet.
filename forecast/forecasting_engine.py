"""SARIMA demand forecasting and reorder suggestions.

Training window: up to ``FORECAST_HISTORY_DAYS`` (90 by default) of daily
sales. Accuracy is measured on the last ``FORECAST_HOLDOUT_DAYS`` (14) days,
then the model is refitted on the full window for the 28-day forecast.
Every run stores MAPE and RMSE in ``forecast_runs`` and ``forecast_metrics``.
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Any, Callable, Iterable, Sequence

import holidays
import numpy as np
import pandas as pd
from statsmodels.tools.sm_exceptions import ConvergenceWarning
from statsmodels.tsa.statespace.sarimax import SARIMAX

from core.config import (
    DEFAULT_REORDER_THRESHOLD,
    FORECAST_HISTORY_DAYS,
    FORECAST_HOLDOUT_DAYS,
    FORECAST_HORIZON_DAYS,
    FORECAST_MIN_HISTORY_DAYS,
    MIN_ORDER_MULTIPLIER,
    SAFETY_STOCK_RATE,
)
from core.errors import ValidationError
from core.time import local_days_ago_utc, local_today, utc_now
from forecast.metrics import evaluate
from services.common import require_connection
from services.vendors import primary_vendor_for

logger = logging.getLogger("stockwise.forecast")

ProgressFn = Callable[[int, int, str], None]


@dataclass
class ProductForecast:
    product_id: int
    dates: list[date]
    predicted: list[float]
    lower: list[float]
    upper: list[float]
    mape: float | None
    rmse: float | None
    train_rows: int
    holdout_rows: int
    model_type: str = "SARIMA"
    used_fallback: bool = False
    week1_demand: float = 0.0
    month_demand: float = 0.0


@lru_cache(maxsize=16)
def _holiday_calendar(years: tuple[int, ...]) -> holidays.HolidayBase:
    return holidays.India(years=list(years))


def get_exogenous_vars(index: pd.DatetimeIndex) -> pd.DataFrame:
    years = tuple(sorted({int(year) for year in index.year}))
    calendar = _holiday_calendar(years)
    frame = pd.DataFrame(index=index)
    frame["is_weekend"] = (frame.index.dayofweek >= 5).astype(int)
    frame["is_holiday"] = [1 if day.date() in calendar else 0 for day in frame.index]
    return frame


def load_sales_history(
    conn: Any, company_id: int, product_id: int, days: int = FORECAST_HISTORY_DAYS
) -> pd.Series:
    conn = require_connection(conn)
    since = local_days_ago_utc(days)
    query = """
        SELECT DATE(s.sale_date) AS sale_day, SUM(si.quantity) AS qty
        FROM sale_items si
        JOIN sales s ON s.sale_id = si.sale_id AND s.company_id = si.company_id
        WHERE si.company_id = %s AND si.product_id = %s
          AND s.status = 'COMPLETED' AND s.sale_date >= %s
        GROUP BY DATE(s.sale_date)
        ORDER BY sale_day ASC
    """
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(query, (company_id, int(product_id), since))
        rows = cursor.fetchall()
    finally:
        cursor.close()
    if not rows:
        return pd.Series(dtype="float64", name="qty")
    frame = pd.DataFrame(rows)
    frame["sale_day"] = pd.to_datetime(frame["sale_day"])
    series = frame.set_index("sale_day")["qty"].astype(float)
    series = series.clip(lower=0)
    full_range = pd.date_range(series.index.min(), local_today(), freq="D")
    return series.reindex(full_range, fill_value=0.0).rename("qty")


def _fallback(values: Sequence[float], horizon: int) -> tuple[list[float], list[float], list[float]]:
    average = float(np.mean(values)) if len(values) else 0.0
    average = max(0.0, min(average, 999999.99))
    predicted = [average] * horizon
    return predicted, predicted, predicted


def _fit_sarima(model: Any) -> Any:
    """Fit a SARIMA model without flooding the log with convergence warnings.

    Sparse or intermittent retail series often hit ``ConvergenceWarning`` even
    when the fitted values are usable. The holdout metrics decide whether the
    result is trustworthy, so the warning is not actionable here.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ConvergenceWarning)
        return model.fit(disp=False)


def fit_product(
    series: pd.Series,
    *,
    horizon: int = FORECAST_HORIZON_DAYS,
    holdout: int = FORECAST_HOLDOUT_DAYS,
    min_history: int = FORECAST_MIN_HISTORY_DAYS,
) -> tuple[list[date], list[float], list[float], list[float], float | None, float | None, int, int, str, bool]:
    """Fit SARIMA, evaluate on a holdout, then refit for the future.

    Returns dates, predictions, lower bound, upper bound, MAPE, RMSE, train
    rows, holdout rows, model type, and whether the fallback was used.
    """
    future_dates = [
        local_today() + timedelta(days=offset) for offset in range(1, horizon + 1)
    ]
    values = [float(value) for value in series.tolist()]

    if len(values) < max(min_history, holdout + 1):
        predicted, lower, upper = _fallback(values, horizon)
        return (
            future_dates,
            predicted,
            lower,
            upper,
            None,
            None,
            len(values),
            0,
            "MEAN_FALLBACK",
            True,
        )

    train_values = values[:-holdout]
    holdout_values = values[-holdout:]
    train_index = series.index[:-holdout]
    holdout_index = series.index[-holdout:]

    try:
        train_exog = get_exogenous_vars(train_index)
        train_series = pd.Series(train_values, index=train_index, name="qty")
        model = SARIMAX(
            train_series,
            exog=train_exog,
            order=(1, 1, 1),
            seasonal_order=(1, 1, 0, 7),
            enforce_stationarity=False,
            enforce_invertibility=False,
        )
        results = _fit_sarima(model)
        holdout_exog = get_exogenous_vars(holdout_index)
        holdout_pred = results.get_forecast(steps=holdout, exog=holdout_exog)
        scores = evaluate(holdout_values, list(holdout_pred.predicted_mean))

        full_exog = get_exogenous_vars(series.index)
        full_series = pd.Series(values, index=series.index, name="qty")
        full_model = SARIMAX(
            full_series,
            exog=full_exog,
            order=(1, 1, 1),
            seasonal_order=(1, 1, 0, 7),
            enforce_stationarity=False,
            enforce_invertibility=False,
        )
        full_results = _fit_sarima(full_model)
        future_index = pd.DatetimeIndex(future_dates)
        future_exog = get_exogenous_vars(future_index)
        forecast = full_results.get_forecast(steps=horizon, exog=future_exog)
        mean = np.asarray(forecast.predicted_mean, dtype=float)
        conf = np.asarray(forecast.conf_int(), dtype=float)

        predicted = _clean(mean)
        lower = _clean(conf[:, 0] if conf.ndim == 2 else mean)
        upper = _clean(conf[:, 1] if conf.ndim == 2 else mean)
        for i in range(len(lower)):
            lower[i] = min(lower[i], predicted[i])
            upper[i] = max(upper[i], predicted[i])
        return (
            future_dates,
            predicted,
            lower,
            upper,
            scores["mape"],
            scores["rmse"],
            len(train_values),
            len(holdout_values),
            "SARIMA",
            False,
        )
    except Exception as exc:  # noqa: BLE001 - fall back rather than fail the run
        logger.warning("SARIMA failed, using mean fallback: %s", exc)
        predicted, lower, upper = _fallback(values, horizon)
        return (
            future_dates,
            predicted,
            lower,
            upper,
            None,
            None,
            len(values),
            0,
            "MEAN_FALLBACK",
            True,
        )


def _clean(values: Iterable[float]) -> list[float]:
    result: list[float] = []
    for value in values:
        number = float(value)
        if not np.isfinite(number):
            number = 0.0
        result.append(max(0.0, min(number, 999999.99)))
    return result


def calculate_reorder_quantity(
    *,
    week1_demand: float,
    month_demand: float,
    available_stock: float,
    reorder_threshold: float,
) -> int:
    safety_stock = max(0.0, week1_demand) * SAFETY_STOCK_RATE
    trigger = max(week1_demand + safety_stock, reorder_threshold)
    if available_stock > trigger:
        return 0
    target = month_demand + safety_stock
    raw = max(target - available_stock, reorder_threshold * MIN_ORDER_MULTIPLIER)
    return int(np.ceil(max(0.0, raw)))


def start_run(conn: Any, company_id: int, actor_id: int, trigger: str) -> int:
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO forecast_runs
                (company_id, started_at, status, trigger_source, created_by)
            VALUES (%s, %s, 'RUNNING', %s, %s)
            """,
            (company_id, utc_now(), trigger, actor_id),
        )
        run_id = int(cursor.lastrowid)
        conn.commit()
        return run_id
    finally:
        cursor.close()


def finish_run(
    conn: Any,
    company_id: int,
    run_id: int,
    *,
    status: str,
    processed: int,
    failed: int,
    mapes: list[float],
    rmses: list[float],
    error: str | None = None,
) -> None:
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE forecast_runs
            SET finished_at = %s, status = %s, products_processed = %s,
                products_failed = %s, mape = %s, rmse = %s, error_message = %s
            WHERE company_id = %s AND run_id = %s
            """,
            (
                utc_now(),
                status,
                processed,
                failed,
                (sum(mapes) / len(mapes)) if mapes else None,
                (sum(rmses) / len(rmses)) if rmses else None,
                error,
                company_id,
                run_id,
            ),
        )
        conn.commit()
    finally:
        cursor.close()


def store_product_forecast(
    conn: Any, company_id: int, run_id: int, forecast: ProductForecast
) -> None:
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT product_id, COALESCE(reorder_threshold, %s) AS reorder_threshold,
                   stock_qty
            FROM products
            WHERE company_id = %s AND product_id = %s
            """,
            (DEFAULT_REORDER_THRESHOLD, company_id, forecast.product_id),
        )
        product = cursor.fetchone()
        if not product:
            return
        vendor = primary_vendor_for(conn, company_id, forecast.product_id)
        vendor_id = int(vendor["vendor_id"]) if vendor else None

        rows = [
            (
                company_id,
                forecast.product_id,
                run_id,
                day,
                forecast.week1_demand / 7 if forecast.week1_demand else 0,
                forecast.predicted[index],
                forecast.lower[index],
                forecast.upper[index],
                forecast.model_type,
                utc_now(),
            )
            for index, day in enumerate(forecast.dates)
        ]
        cursor.executemany(
            """
            INSERT INTO forecasts
                (company_id, product_id, run_id, forecast_date,
                 avg_daily_demand, predicted_demand, lower_bound, upper_bound,
                 model_type, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                predicted_demand = VALUES(predicted_demand),
                lower_bound = VALUES(lower_bound),
                upper_bound = VALUES(upper_bound),
                avg_daily_demand = VALUES(avg_daily_demand)
            """,
            rows,
        )
        cursor.execute(
            """
            INSERT INTO forecast_metrics
                (company_id, run_id, product_id, train_rows, holdout_rows,
                 mape, rmse, model_type, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                train_rows = VALUES(train_rows), holdout_rows = VALUES(holdout_rows),
                mape = VALUES(mape), rmse = VALUES(rmse),
                model_type = VALUES(model_type)
            """,
            (
                company_id,
                run_id,
                forecast.product_id,
                forecast.train_rows,
                forecast.holdout_rows,
                forecast.mape,
                forecast.rmse,
                forecast.model_type,
                utc_now(),
            ),
        )

        cursor.execute(
            "UPDATE reorder_suggestions SET status = 'SUPERSEDED' "
            "WHERE company_id = %s AND product_id = %s AND status = 'PENDING'",
            (company_id, forecast.product_id),
        )
        reorder_qty = calculate_reorder_quantity(
            week1_demand=forecast.week1_demand,
            month_demand=forecast.month_demand,
            available_stock=float(product["stock_qty"]),
            reorder_threshold=float(product["reorder_threshold"]),
        )
        if reorder_qty > 0:
            cursor.execute(
                """
                INSERT INTO reorder_suggestions
                    (company_id, product_id, vendor_id, recommended_quantity,
                     generated_date, status, forecast_run_id)
                VALUES (%s, %s, %s, %s, %s, 'PENDING', %s)
                """,
                (
                    company_id,
                    forecast.product_id,
                    vendor_id,
                    reorder_qty,
                    utc_now(),
                    run_id,
                ),
            )
        conn.commit()
    finally:
        cursor.close()


def run_full_analysis(
    conn: Any,
    company_id: int,
    actor_id: int,
    *,
    progress: ProgressFn | None = None,
    trigger: str = "manual",
) -> dict[str, Any]:
    conn = require_connection(conn)
    run_id = start_run(conn, company_id, actor_id, trigger)
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT product_id, name FROM products "
            "WHERE company_id = %s AND is_active = 1 AND deleted_at IS NULL "
            "ORDER BY product_id",
            (company_id,),
        )
        products = list(cursor.fetchall())
    finally:
        cursor.close()

    processed = 0
    failed = 0
    mapes: list[float] = []
    rmses: list[float] = []
    total = len(products)
    for index, product in enumerate(products, start=1):
        product_id = int(product["product_id"])
        try:
            series = load_sales_history(conn, company_id, product_id)
            (
                dates,
                predicted,
                lower,
                upper,
                mape_value,
                rmse_value,
                train_rows,
                holdout_rows,
                model_type,
                used_fallback,
            ) = fit_product(series)
            week1 = float(sum(predicted[:7]))
            month = float(sum(predicted))
            forecast = ProductForecast(
                product_id=product_id,
                dates=dates,
                predicted=predicted,
                lower=lower,
                upper=upper,
                mape=mape_value,
                rmse=rmse_value,
                train_rows=train_rows,
                holdout_rows=holdout_rows,
                model_type=model_type,
                used_fallback=used_fallback,
                week1_demand=week1,
                month_demand=month,
            )
            store_product_forecast(conn, company_id, run_id, forecast)
            processed += 1
            if mape_value is not None:
                mapes.append(mape_value)
            if rmse_value is not None:
                rmses.append(rmse_value)
        except Exception as exc:  # noqa: BLE001 - one product must not kill the run
            failed += 1
            conn.rollback()
            logger.exception("Forecast failed for product %s: %s", product_id, exc)
        if progress:
            progress(index, total, str(product["name"]))

    finish_run(
        conn,
        company_id,
        run_id,
        status="COMPLETED" if failed == 0 else "PARTIAL",
        processed=processed,
        failed=failed,
        mapes=mapes,
        rmses=rmses,
    )
    return {
        "run_id": run_id,
        "processed": processed,
        "failed": failed,
        "mape": (sum(mapes) / len(mapes)) if mapes else None,
        "rmse": (sum(rmses) / len(rmses)) if rmses else None,
        "history_days": FORECAST_HISTORY_DAYS,
        "holdout_days": FORECAST_HOLDOUT_DAYS,
    }


def latest_run(conn: Any | None, company_id: int) -> dict | None:
    conn = require_connection(conn)
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT run_id, started_at, finished_at, status, products_processed,
                   products_failed, mape, rmse, trigger_source, error_message
            FROM forecast_runs
            WHERE company_id = %s
            ORDER BY run_id DESC
            LIMIT 1
            """,
            (company_id,),
        )
        return cursor.fetchone()
    finally:
        cursor.close()


def product_forecast(
    conn: Any | None, company_id: int, product_id: int
) -> list[dict]:
    conn = require_connection(conn)
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT f.forecast_date, f.predicted_demand, f.lower_bound,
                   f.upper_bound
            FROM forecasts f
            WHERE f.company_id = %s AND f.product_id = %s AND f.run_id = (
                SELECT MAX(r.run_id) FROM forecast_runs r
                WHERE r.company_id = %s AND r.status IN ('COMPLETED', 'PARTIAL')
            )
            ORDER BY f.forecast_date ASC
            """,
            (company_id, int(product_id), company_id),
        )
        return list(cursor.fetchall())
    finally:
        cursor.close()


def pending_reorder_suggestions(conn: Any | None, company_id: int) -> list[dict]:
    conn = require_connection(conn)
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT rs.id AS suggestion_id, rs.product_id, p.name, p.sku,
                   p.selling_price, p.stock_qty,
                   rs.recommended_quantity, rs.vendor_id,
                   v.name AS vendor_name
            FROM reorder_suggestions rs
            JOIN products p ON p.product_id = rs.product_id
              AND p.company_id = rs.company_id
            LEFT JOIN vendors v ON v.vendor_id = rs.vendor_id
              AND v.company_id = rs.company_id
            WHERE rs.company_id = %s AND rs.status = 'PENDING'
              AND p.is_active = 1 AND p.deleted_at IS NULL
            ORDER BY rs.recommended_quantity DESC, p.name ASC
            """,
            (company_id,),
        )
        return list(cursor.fetchall())
    finally:
        cursor.close()


def run_from_script(company_id: int, actor_id: int) -> dict[str, Any]:
    """CLI entry point used by scripts/retrain_forecasts.py."""
    import db

    with db.connection() as conn:
        if conn is None:
            raise ValidationError("Database connection is not available.")
        return run_full_analysis(conn, company_id, actor_id, trigger="scheduled")
