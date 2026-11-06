from __future__ import annotations

from decimal import Decimal

import pytest

from core.cart import (
    CartItem,
    add_item,
    cart_total,
    group_by_vendor,
    make_cart_item,
    normalize_cart,
)
from core.errors import CartError, ValidationError


def item(**overrides) -> CartItem:
    values = {
        "company_id": 1,
        "product_id": 10,
        "product_name": "Milk",
        "vendor_id": 2,
        "vendor_name": "Northwind",
        "quantity": 3,
        "cost_price": "40.50",
    }
    values.update(overrides)
    return make_cart_item(**values)


def test_item_total_is_decimal_and_rounded() -> None:
    cart_item = item(quantity=3, cost_price="40.505")
    assert cart_item.cost_price == Decimal("40.51")
    assert cart_item.total == Decimal("121.53")


def test_item_requires_vendor() -> None:
    with pytest.raises(CartError):
        item(vendor_id=0, vendor_name="")
    with pytest.raises(CartError):
        item(vendor_name="")


def test_quantity_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        item(quantity=0)


def test_add_item_merges_same_product_vendor_and_price() -> None:
    cart = [item()]
    add_item(cart, item(quantity=2))
    assert len(cart) == 1
    assert cart[0].quantity == 5
    assert cart[0].total == Decimal("202.50")


def test_add_item_keeps_different_vendors_separate() -> None:
    cart = [item()]
    add_item(cart, item(vendor_id=3, vendor_name="Sunrise"))
    assert len(cart) == 2


def test_normalize_cart_rejects_legacy_missing_vendor() -> None:
    with pytest.raises(CartError, match="missing a vendor"):
        normalize_cart([{"product_id": 1, "name": "Milk", "quantity": 1, "cost_price": 10}], 1)


def test_normalize_cart_rejects_wrong_company() -> None:
    with pytest.raises(CartError, match="another company"):
        normalize_cart([item().to_dict()], 2)


def test_cart_total_and_grouping() -> None:
    cart = [item(), item(vendor_id=3, vendor_name="Sunrise", cost_price="20")]
    assert cart_total(cart) == Decimal("181.50")
    groups = group_by_vendor(cart)
    assert set(groups) == {2, 3}
