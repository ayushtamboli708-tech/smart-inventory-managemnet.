"""Shared configuration constants.

Magic numbers that used to be scattered across pages live here so thresholds
can be changed in one place. Environment overrides cover deployment-specific
values.
"""

from __future__ import annotations

import os

DEFAULT_COMPANY_ID = int(os.getenv("STOCKWISE_COMPANY_ID", "1"))
DEFAULT_REORDER_THRESHOLD = int(os.getenv("STOCKWISE_REORDER_THRESHOLD", "10"))
DEFAULT_PAGE_SIZE = int(os.getenv("STOCKWISE_PAGE_SIZE", "15"))

# Forecasting window. The model trains on at most this many days of history and
# evaluates on the last FORECAST_HOLDOUT_DAYS days before refitting.
FORECAST_HISTORY_DAYS = int(os.getenv("STOCKWISE_FORECAST_HISTORY_DAYS", "90"))
FORECAST_HOLDOUT_DAYS = int(os.getenv("STOCKWISE_FORECAST_HOLDOUT_DAYS", "14"))
FORECAST_HORIZON_DAYS = int(os.getenv("STOCKWISE_FORECAST_HORIZON_DAYS", "28"))
FORECAST_MIN_HISTORY_DAYS = int(os.getenv("STOCKWISE_FORECAST_MIN_HISTORY_DAYS", "14"))

# Reorder heuristics.
SAFETY_STOCK_RATE = float(os.getenv("STOCKWISE_SAFETY_STOCK_RATE", "0.20"))
MIN_ORDER_MULTIPLIER = float(os.getenv("STOCKWISE_MIN_ORDER_MULTIPLIER", "2"))
OVERSTOCK_MULTIPLIER = float(os.getenv("STOCKWISE_OVERSTOCK_MULTIPLIER", "5"))
OVERSTOCK_MIN_UNITS = float(os.getenv("STOCKWISE_OVERSTOCK_MIN_UNITS", "50"))

CURRENCY_SYMBOL = os.getenv("STOCKWISE_CURRENCY", "₹")
TIMEZONE = os.getenv("STOCKWISE_TIMEZONE", "Asia/Kolkata")

STAFF_PIN_KEY = "staff"


def page_size(value: int | None = None) -> int:
    """Clamp page size to a sane range."""
    size = value or DEFAULT_PAGE_SIZE
    return max(5, min(100, int(size)))
