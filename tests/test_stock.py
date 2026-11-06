from __future__ import annotations

from decimal import Decimal

import pytest

from core.cart import make_cart_item
from core.errors import InsufficientStock
from core.stock import (
    aggregate_required,
    apply_ledger_entry,
    lock_products,
    recompute_stock,
    validate_available,
)


def product(product_id: int = 1, stock: float = 5, active: bool = True) -> dict:
    return {
        "product_id": product_id,
        "name": f"Product {product_id}",
        "stock_qty": Decimal(str(stock)),
        "is_active": active,
        "deleted_at": None,
    }


def test_aggregate_required_merges_duplicate_lines() -> None:
    cart = [
        make_cart_item(
            company_id=1,
            product_id=1,
            product_name="Milk",
            vendor_id=1,
            vendor_name="V",
            quantity=2,
            cost_price=1,
        ),
        make_cart_item(
            company_id=1,
            product_id=1,
            product_name="Milk",
            vendor_id=2,
            vendor_name="W",
            quantity=3,
            cost_price=1,
        ),
    ]
    assert aggregate_required(cart) == {1: Decimal("5.00")}
    assert aggregate_required([(1, 2), (1, 4), (2, 1)]) == {
        1: Decimal("6.00"),
        2: Decimal("1.00"),
    }


def test_validate_available_accepts_exact_stock() -> None:
    validate_available({1: product(stock=5)}, {1: Decimal("5")})


def test_validate_available_rejects_shortage() -> None:
    with pytest.raises(InsufficientStock):
        validate_available({1: product(stock=4)}, {1: Decimal("5")})


def test_validate_available_rejects_inactive_or_missing() -> None:
    with pytest.raises(InsufficientStock):
        validate_available({1: product(active=False)}, {1: Decimal("1")})
    with pytest.raises(InsufficientStock):
        validate_available({}, {1: Decimal("1")})


class FakeCursor:
    def __init__(self, update_rowcount: int = 1) -> None:
        self.update_rowcount = update_rowcount
        self.calls: list[tuple[str, tuple]] = []
        self.rowcount = 0

    def execute(self, sql: str, params: tuple = ()) -> None:
        self.calls.append((sql, params))
        if "UPDATE products" in sql:
            self.rowcount = self.update_rowcount

    def fetchone(self):
        return ("Milk", 2)


class LockCursor:
    def __init__(self) -> None:
        self.sql = ""
        self.params: tuple = ()

    def execute(self, sql: str, params: tuple = ()) -> None:
        self.sql, self.params = sql, params

    def fetchall(self):
        return [
            {
                "product_id": 1,
                "sku": "MILK-1",
                "name": "Milk",
                "stock_qty": 5,
                "selling_price": 68,
                "is_active": 1,
                "deleted_at": None,
            }
        ]


def test_lock_products_selects_price_and_locks_rows() -> None:
    cursor = LockCursor()
    rows = lock_products(cursor, 1, [1])
    assert rows[1]["selling_price"] == 68
    assert "selling_price" in cursor.sql
    assert "FOR UPDATE" in cursor.sql
    assert cursor.params == (1, 1)


def test_apply_ledger_entry_writes_ledger_and_balance() -> None:
    cursor = FakeCursor(update_rowcount=1)
    apply_ledger_entry(
        cursor,
        company_id=1,
        product_id=1,
        quantity_change=-3,
        transaction_type="SALE",
        reference_type="SALE",
        reference_id=9,
        actor_id=7,
    )
    assert len(cursor.calls) == 2
    assert "INSERT INTO inventory_ledger" in cursor.calls[0][0]
    assert "quantity_change" in cursor.calls[0][0]
    assert "UPDATE products" in cursor.calls[1][0]


def test_apply_ledger_entry_blocks_negative_stock() -> None:
    with pytest.raises(InsufficientStock):
        apply_ledger_entry(
            FakeCursor(update_rowcount=0),
            company_id=1,
            product_id=1,
            quantity_change=-3,
            transaction_type="SALE",
            reference_type="SALE",
            reference_id=9,
            actor_id=7,
        )


class RecomputeCursor:
    def __init__(self) -> None:
        self.computed_sql = ""
        self.updates: list[tuple] = []
        self.closed = False

    def execute(self, sql: str, params: tuple = ()) -> None:
        if sql.strip().startswith("SELECT"):
            self.computed_sql = sql
        else:
            self.updates.append(params)

    def fetchall(self):
        return [{"product_id": 1, "computed": 0}]

    def close(self) -> None:
        self.closed = True


class FakeConnection:
    def __init__(self, cursor: RecomputeCursor) -> None:
        self.cursor_obj = cursor
        self.committed = False

    def cursor(self, dictionary: bool = False) -> RecomputeCursor:
        return self.cursor_obj

    def commit(self) -> None:
        self.committed = True


def test_recompute_stock_clamps_negative_ledger_at_zero() -> None:
    cursor = RecomputeCursor()
    conn = FakeConnection(cursor)
    changed = recompute_stock(conn, 1, 1)  # type: ignore[arg-type]
    assert changed == 1
    assert "GREATEST" in cursor.computed_sql
    assert cursor.updates == [(0, 1, 1)]
    assert conn.committed
    assert cursor.closed
