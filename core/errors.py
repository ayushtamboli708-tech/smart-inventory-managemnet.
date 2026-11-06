"""Domain exceptions.

Services raise these instead of leaking raw driver errors to the UI. The UI
layer maps them to short, actionable messages while the logger keeps the
technical detail.
"""

from __future__ import annotations


class StockwiseError(Exception):
    """Base class for expected application errors."""


class ValidationError(StockwiseError):
    """User input is invalid."""


class PermissionDenied(StockwiseError):
    """The current user lacks the required role."""


class CartError(ValidationError):
    """The purchase cart is malformed or incomplete."""


class InsufficientStock(StockwiseError):
    """A sale or adjustment would drive stock below zero."""

    def __init__(self, product_name: str, available: float, requested: float):
        self.product_name = product_name
        self.available = available
        self.requested = requested
        super().__init__(
            f"Not enough stock for {product_name}: "
            f"{available:g} available, {requested:g} requested."
        )


class DatabaseUnavailable(StockwiseError):
    """The database connection could not be established."""
