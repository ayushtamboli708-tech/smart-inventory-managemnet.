"""Forecast accuracy metrics (pure functions, unit-testable without a DB)."""

from __future__ import annotations

import math
from typing import Iterable, Sequence


def mape(actual: Iterable[float], predicted: Iterable[float]) -> float | None:
    """Mean absolute percentage error, ignoring zero actuals.

    Returns ``None`` when no non-zero actual value exists, because MAPE is
    undefined in that case.
    """
    pairs = [(float(a), float(p)) for a, p in zip(actual, predicted)]
    usable = [(a, p) for a, p in pairs if a != 0]
    if not usable:
        return None
    value = sum(abs((a - p) / a) for a, p in usable) / len(usable) * 100
    return round(value, 4)


def rmse(actual: Iterable[float], predicted: Iterable[float]) -> float | None:
    pairs = [(float(a), float(p)) for a, p in zip(actual, predicted)]
    if not pairs:
        return None
    value = math.sqrt(sum((a - p) ** 2 for a, p in pairs) / len(pairs))
    return round(value, 4)


def evaluate(actual: Sequence[float], predicted: Sequence[float]) -> dict[str, float | None]:
    if len(actual) != len(predicted):
        raise ValueError("actual and predicted must have the same length")
    return {"mape": mape(actual, predicted), "rmse": rmse(actual, predicted)}
