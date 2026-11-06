from __future__ import annotations

import pandas as pd

from forecast.forecasting_engine import calculate_reorder_quantity, fit_product


def test_reorder_quantity_triggers_below_target() -> None:
    quantity = calculate_reorder_quantity(
        week1_demand=70,
        month_demand=280,
        available_stock=10,
        reorder_threshold=20,
    )
    assert quantity == 284


def test_reorder_quantity_respects_minimum_order() -> None:
    quantity = calculate_reorder_quantity(
        week1_demand=0,
        month_demand=0,
        available_stock=5,
        reorder_threshold=20,
    )
    assert quantity == 40


def test_reorder_quantity_is_zero_when_stock_is_healthy() -> None:
    quantity = calculate_reorder_quantity(
        week1_demand=70,
        month_demand=280,
        available_stock=100,
        reorder_threshold=20,
    )
    assert quantity == 0


def test_short_history_uses_mean_fallback() -> None:
    series = pd.Series(
        [1.0, 2.0, 3.0],
        index=pd.date_range("2026-10-01", periods=3, freq="D"),
    )
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
    ) = fit_product(series, horizon=7, holdout=14, min_history=14)
    assert len(dates) == 7
    assert predicted == [2.0] * 7
    assert lower == upper == predicted
    assert mape_value is None and rmse_value is None
    assert train_rows == 3
    assert holdout_rows == 0
    assert model_type == "MEAN_FALLBACK"
    assert used_fallback is True
