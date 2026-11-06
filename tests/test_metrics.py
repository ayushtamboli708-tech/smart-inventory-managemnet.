from __future__ import annotations

import pytest

from forecast.metrics import evaluate, mape, rmse


def test_mape_ignores_zero_actuals() -> None:
    value = mape([0, 10, 20], [5, 11, 18])
    assert value == pytest.approx(10.0, abs=0.0001)


def test_mape_returns_none_without_nonzero_actuals() -> None:
    assert mape([0, 0], [1, 2]) is None


def test_rmse_matches_manual_calculation() -> None:
    assert rmse([1, 2, 3], [1, 2, 5]) == pytest.approx(1.1547, abs=0.0001)


def test_evaluate_returns_both_metrics() -> None:
    result = evaluate([10, 20], [12, 18])
    assert result["mape"] == pytest.approx(15.0)
    assert result["rmse"] == pytest.approx(2.0)


def test_evaluate_rejects_length_mismatch() -> None:
    with pytest.raises(ValueError):
        evaluate([1], [1, 2])
