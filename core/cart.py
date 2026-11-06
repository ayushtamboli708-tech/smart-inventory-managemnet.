"""Purchase-cart domain model.

Every entry point (manual purchase, dashboard forecast, alert suggestion) uses
the same constructor. This removes the old mismatch where some callers forgot
``vendor_id`` and the save path crashed with a KeyError.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Iterable, Mapping

from core.errors import CartError, ValidationError


def money(value: Any) -> Decimal:
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError(f"Invalid money value: {value!r}") from exc


def quantity(value: Any) -> int:
    try:
        qty = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"Invalid quantity: {value!r}") from exc
    if qty <= 0:
        raise ValidationError("Quantity must be greater than zero.")
    return qty


@dataclass
class CartItem:
    company_id: int
    product_id: int
    vendor_id: int
    vendor_name: str
    name: str
    quantity: int
    cost_price: Decimal
    source: str = "manual"
    suggestion_id: int | None = None

    def __post_init__(self) -> None:
        self.quantity = quantity(self.quantity)
        self.cost_price = money(self.cost_price)
        if self.cost_price < 0:
            raise ValidationError("Cost price cannot be negative.")
        if not self.vendor_id:
            raise CartError("A vendor is required before adding an item.")
        if not self.vendor_name:
            raise CartError("A vendor name is required before adding an item.")

    @property
    def total(self) -> Decimal:
        return (self.cost_price * self.quantity).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "company_id": self.company_id,
            "product_id": self.product_id,
            "vendor_id": self.vendor_id,
            "vendor_name": self.vendor_name,
            "name": self.name,
            "quantity": self.quantity,
            "cost_price": str(self.cost_price),
            "total": str(self.total),
            "source": self.source,
            "suggestion_id": self.suggestion_id,
        }

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "CartItem":
        cost = data.get("cost_price", data.get("unit_cost", data.get("price", 0)))
        return cls(
            company_id=int(data.get("company_id", 1)),
            product_id=int(data["product_id"]),
            vendor_id=int(data.get("vendor_id", 0) or 0),
            vendor_name=str(data.get("vendor_name", "") or ""),
            name=str(data.get("name", "") or ""),
            quantity=data.get("quantity", 0),
            cost_price=cost,
            source=str(data.get("source", "manual")),
            suggestion_id=data.get("suggestion_id"),
        )


def make_cart_item(
    *,
    company_id: int,
    product_id: int,
    product_name: str,
    vendor_id: int,
    vendor_name: str,
    quantity: int,
    cost_price: Any,
    source: str = "manual",
    suggestion_id: int | None = None,
) -> CartItem:
    return CartItem(
        company_id=int(company_id),
        product_id=int(product_id),
        vendor_id=int(vendor_id),
        vendor_name=vendor_name,
        name=product_name,
        quantity=quantity,
        cost_price=money(cost_price),
        source=source,
        suggestion_id=suggestion_id,
    )


def add_item(items: list[CartItem], item: CartItem) -> list[CartItem]:
    """Merge the same product+vendor instead of creating duplicate lines."""
    for existing in items:
        if (
            existing.product_id == item.product_id
            and existing.vendor_id == item.vendor_id
            and existing.cost_price == item.cost_price
        ):
            existing.quantity += item.quantity
            return items
    items.append(item)
    return items


def cart_total(items: Iterable[CartItem]) -> Decimal:
    return sum((item.total for item in items), Decimal("0.00")).quantize(Decimal("0.01"))


def normalize_cart(raw_items: Iterable[Any], company_id: int) -> list[CartItem]:
    """Convert session data into validated cart items with a clear error."""
    result: list[CartItem] = []
    for index, raw in enumerate(raw_items, start=1):
        try:
            item = raw if isinstance(raw, CartItem) else CartItem.from_mapping(raw)
        except CartError as exc:
            raise CartError(
                f"Cart line {index} is missing a vendor. Remove it and add the "
                f"item again. ({exc})"
            ) from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise CartError(
                f"Cart line {index} is malformed. Remove it and try again."
            ) from exc
        if item.company_id != int(company_id):
            raise CartError("Cart contains an item from another company.")
        result.append(item)
    return result


def group_by_vendor(items: Iterable[CartItem]) -> dict[int, list[CartItem]]:
    groups: dict[int, list[CartItem]] = {}
    for item in items:
        groups.setdefault(item.vendor_id, []).append(item)
    return groups
