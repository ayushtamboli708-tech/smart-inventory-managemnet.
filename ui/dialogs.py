"""Dialogs shared by dashboard, alerts, and the purchase page."""

from __future__ import annotations

from typing import Any

import streamlit as st

import db
from core.auth import require_owner, session_user
from core.cart import add_item, make_cart_item
from core.errors import StockwiseError
from services.vendors import create_vendor, list_vendors, update_vendor


def _company_id() -> int:
    return int(st.session_state.get("company_id", 1) or 1)


@st.dialog("Add to purchase cart")
def show_add_to_cart_dialog(
    product: dict[str, Any],
    *,
    default_qty: int = 1,
    default_cost: float | None = None,
    suggestion_id: int | None = None,
) -> None:
    st.markdown(f"### {product['name']}")
    st.caption(f"SKU: {product.get('sku', '—')}")

    company_id = _company_id()
    with db.connection() as conn:
        vendors = list_vendors(conn, company_id) if conn else []

    if not vendors:
        st.warning("Add a vendor before creating a purchase order.")
        if st.button("Close", width="stretch"):
            st.rerun()
        return

    vendor_labels = {f"{v['name']}": int(v["vendor_id"]) for v in vendors}
    selected = st.selectbox("Vendor", list(vendor_labels.keys()))
    quantity = st.number_input(
        "Order quantity", min_value=1, step=1, value=max(1, int(default_qty))
    )
    pricing = default_cost
    if pricing is None:
        pricing = float(product.get("cost_price") or float(product.get("selling_price", 0)) * 0.7)
    cost = st.number_input(
        "Unit cost (₹)", min_value=0.0, step=1.0, value=float(pricing)
    )

    if st.button("Add to Purchase Cart", type="primary", width="stretch"):
        try:
            item = make_cart_item(
                company_id=company_id,
                product_id=int(product["product_id"]),
                product_name=str(product["name"]),
                vendor_id=vendor_labels[selected],
                vendor_name=selected,
                quantity=int(quantity),
                cost_price=cost,
                source="suggestion" if suggestion_id else "manual",
                suggestion_id=suggestion_id,
            )
            cart = st.session_state.setdefault("current_purchase_items", [])
            add_item(cart, item)
            st.session_state.open_purchase_dialog = True
            st.session_state.nav_selection = "Purchases"
            st.rerun()
        except StockwiseError as exc:
            st.error(str(exc))


def show_vendor_dialog(vendor: dict[str, Any] | None = None) -> None:
    actor = require_owner(session_user(st))
    company_id = _company_id()
    editing = vendor is not None
    title = "Edit Vendor" if editing else "Add Vendor"
    st.markdown(f"### {title}")

    with st.form("vendor_form", clear_on_submit=not editing):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Vendor name*", value=vendor.get("name", "") if vendor else "")
            contact = st.text_input(
                "Contact (phone/email)", value=vendor.get("contact", "") if vendor else ""
            )
        with col2:
            lead_time = st.number_input(
                "Lead time (days)",
                min_value=0,
                step=1,
                value=int(vendor.get("lead_time_days", 0)) if vendor else 0,
            )
            address = st.text_input(
                "Address", value=vendor.get("address", "") if vendor else ""
            )
        active = st.checkbox(
            "Active", value=bool(vendor.get("is_active", True)) if vendor else True
        )

        if st.form_submit_button(
            "Save Vendor", type="primary", width="stretch"
        ):
            try:
                with db.transaction() as conn:
                    if conn is None:
                        st.error("Database is unavailable.")
                        return
                    if editing:
                        update_vendor(
                            conn,
                            company_id,
                            actor,
                            int(vendor["vendor_id"]),
                            name=name,
                            contact=contact,
                            address=address,
                            lead_time_days=int(lead_time),
                            is_active=active,
                        )
                    else:
                        create_vendor(
                            conn,
                            company_id,
                            actor,
                            name=name,
                            contact=contact,
                            address=address,
                            lead_time_days=int(lead_time),
                        )
                st.success(f"Vendor {'updated' if editing else 'created'}.")
                st.rerun()
            except StockwiseError as exc:
                st.error(str(exc))
