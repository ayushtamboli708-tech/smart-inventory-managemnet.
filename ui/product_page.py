"""Catalog management page (owner writes, staff read-only)."""

from __future__ import annotations

import time

import pandas as pd
import streamlit as st

import db
from core.auth import can, require_owner, session_user
from core.config import DEFAULT_PAGE_SIZE
from core.errors import StockwiseError
from services.catalog import (
    adjust_stock,
    archive_product,
    bulk_create_products,
    create_product,
    get_product,
    list_categories,
    list_products,
    set_active,
    update_product,
)
from ui.components import (
    handle_error,
    money,
    page_header,
    server_page,
    server_pagination,
)

CATEGORIES = [
    "Dairy",
    "Bakery",
    "Beverages",
    "Electronics",
    "Apparel",
    "Other",
    "Vegetables",
    "Snacks",
    "Grocery",
    "Personal Care",
]
UNITS = ["Pc", "Ltr", "Kg", "Box", "Dozen"]


def _company_id() -> int:
    return int(st.session_state.get("company_id", 1) or 1)


def _form(actor, company_id: int) -> None:
    require_owner(actor)
    is_edit = st.session_state.get("edit_product_data") is not None
    product = st.session_state.get("edit_product_data") or {}

    with st.container(border=True):
        st.markdown(f"### {'Edit product' if is_edit else 'New product'}")
        with st.form("product_form"):
            left, right = st.columns(2)
            with left:
                sku = st.text_input(
                    "SKU*", value=product.get("sku", ""), disabled=is_edit
                )
                name = st.text_input("Product name*", value=product.get("name", ""))
                category_value = product.get("category", "Other")
                category_index = (
                    CATEGORIES.index(category_value)
                    if category_value in CATEGORIES
                    else 0
                )
                category = st.selectbox("Category", CATEGORIES, index=category_index)
                unit_value = product.get("unit", "Pc")
                unit = st.selectbox(
                    "Unit",
                    UNITS,
                    index=UNITS.index(unit_value) if unit_value in UNITS else 0,
                )
            with right:
                price = st.number_input(
                    "Selling price (₹)",
                    min_value=0.0,
                    value=float(product.get("selling_price", 0.0)),
                )
                reorder = st.number_input(
                    "Reorder threshold",
                    min_value=0,
                    value=int(product.get("reorder_threshold", 10)),
                )
                active = st.checkbox(
                    "Active", value=bool(product.get("is_active", True))
                )
                opening_stock = (
                    0
                    if is_edit
                    else st.number_input("Opening stock", min_value=0, value=0, step=1)
                )

            submitted = st.form_submit_button(
                "Save product", type="primary", width="stretch"
            )
        if submitted:
            try:
                with db.transaction() as conn:
                    if conn is None:
                        st.error("Database is unavailable.")
                        return
                    if is_edit:
                        update_product(
                            conn,
                            company_id,
                            actor,
                            int(product["product_id"]),
                            name=name,
                            category=category,
                            unit=unit,
                            selling_price=price,
                            reorder_threshold=int(reorder),
                            is_active=active,
                        )
                    else:
                        create_product(
                            conn,
                            company_id,
                            actor,
                            sku=sku,
                            name=name,
                            category=category,
                            unit=unit,
                            selling_price=price,
                            reorder_threshold=int(reorder),
                            is_active=active,
                            opening_stock=int(opening_stock),
                        )
                st.session_state.show_product_form = False
                st.session_state.edit_product_data = None
                st.success("Product saved.")
                time.sleep(0.3)
                st.rerun()
            except StockwiseError as exc:
                handle_error(exc)
            except Exception as exc:  # noqa: BLE001
                handle_error(exc)

        if st.button("Cancel"):
            st.session_state.show_product_form = False
            st.session_state.edit_product_data = None
            st.rerun()


def _bulk_upload(actor, company_id: int) -> None:
    require_owner(actor)
    with st.expander("Bulk upload products (CSV)"):
        st.caption(
            "Required columns: SKU, Name, Category, Unit, Price, Reorder_Pt. "
            "Existing SKUs are updated, not duplicated."
        )
        uploaded = st.file_uploader("Choose a CSV file", type="csv")
        if uploaded is None:
            return
        try:
            frame = pd.read_csv(uploaded)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Could not read the CSV: {exc}")
            return
        st.dataframe(frame.head(5), width="stretch", hide_index=True)
        if st.button("Process batch", type="primary"):
            try:
                with db.transaction() as conn:
                    if conn is None:
                        st.error("Database is unavailable.")
                        return
                    attempted, affected = bulk_create_products(
                        conn, company_id, actor, frame.to_dict("records")
                    )
                st.success(f"Processed {attempted} rows ({affected} insert/update operations).")
                time.sleep(0.4)
                st.rerun()
            except StockwiseError as exc:
                handle_error(exc)


def show_product_page() -> None:
    actor = session_user(st)
    company_id = _company_id()
    if actor is None:
        st.error("Please sign in.")
        return

    st.session_state.setdefault("show_product_form", False)
    st.session_state.setdefault("edit_product_data", None)

    page_header("Products", "Manage the catalog, stock adjustments, and archival")
    heading, action = st.columns([4, 1])
    with heading:
        if st.session_state.show_product_form:
            st.caption("Editing catalog data")
    with action:
        if can(actor, "Owner") and st.button(
            "New product", type="primary", width="stretch"
        ):
            st.session_state.show_product_form = True
            st.session_state.edit_product_data = None
            st.rerun()

    if st.session_state.show_product_form and can(actor, "Owner"):
        _form(actor, company_id)
        st.write("---")

    if not st.session_state.show_product_form and can(actor, "Owner"):
        _bulk_upload(actor, company_id)
        st.write("---")

    filter_cols = st.columns([2, 1, 1])
    with filter_cols[0]:
        search = st.text_input(
            "Search",
            placeholder="Search by product name or SKU...",
            label_visibility="collapsed",
        )
    with db.connection() as conn:
        categories = list_categories(conn, company_id) if conn else []
    with filter_cols[1]:
        category = st.selectbox(
            "Category",
            ["All Categories", *categories],
            label_visibility="collapsed",
        )
    with filter_cols[2]:
        status = st.selectbox(
            "Status",
            ["All Statuses", "Active", "Inactive", "Archived"],
            label_visibility="collapsed",
        )

    page = server_page("products")
    with db.connection() as conn:
        if conn is None:
            st.error("Database is unavailable.")
            return
        rows, total = list_products(
            conn,
            company_id,
            search=search,
            category=category,
            status=status,
            page=page,
            page_size=DEFAULT_PAGE_SIZE,
        )

    if not rows:
        st.info("No products found matching your filters.")
        server_pagination(
            "products", page=page, total=total, page_size=DEFAULT_PAGE_SIZE
        )
        return

    frame = pd.DataFrame(rows)
    display = frame.copy()
    display["selling_price"] = display["selling_price"].apply(money)
    display["status_label"] = display.apply(
        lambda row: "Archived"
        if pd.notna(row.get("deleted_at"))
        else ("Active" if row["is_active"] else "Inactive"),
        axis=1,
    )
    display = display.rename(
        columns={
            "sku": "SKU",
            "name": "Name",
            "category": "Category",
            "stock_qty": "Stock",
            "unit": "Unit",
            "reorder_threshold": "Reorder pt",
            "status_label": "Status",
            "selling_price": "Price",
        }
    )
    st.dataframe(
        display[
            ["SKU", "Name", "Category", "Stock", "Unit", "Price", "Reorder pt", "Status"]
        ],
        width="stretch",
        hide_index=True,
    )
    server_pagination("products", page=page, total=total, page_size=DEFAULT_PAGE_SIZE)

    if not can(actor, "Owner"):
        return

    st.markdown("<br>", unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown("#### Product actions")
        options = {
            f"[{row['sku']}] {row['name']}": row for row in rows
        }
        selected_label = st.selectbox(
            "Select a product", ["Select...", *options.keys()]
        )
        if selected_label == "Select...":
            return
        product = options[selected_label]
        product_id = int(product["product_id"])

        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("Edit", width="stretch"):
                with db.connection() as conn:
                    full = (
                        get_product(conn, company_id, product_id) if conn else None
                    )
                if full:
                    st.session_state.edit_product_data = full
                    st.session_state.show_product_form = True
                    st.rerun()
                else:
                    st.error("Could not load that product. Try again.")
        with col2:
            if product.get("deleted_at") is None:
                if product["is_active"]:
                    if st.button("Deactivate", width="stretch"):
                        try:
                            with db.transaction() as conn:
                                set_active(conn, company_id, actor, product_id, False)
                            st.rerun()
                        except StockwiseError as exc:
                            handle_error(exc)
                else:
                    if st.button("Activate", width="stretch"):
                        try:
                            with db.transaction() as conn:
                                set_active(conn, company_id, actor, product_id, True)
                            st.rerun()
                        except StockwiseError as exc:
                            handle_error(exc)
        with col3:
            if product.get("deleted_at") is None:
                confirmed = st.checkbox(
                    "Confirm archive", key=f"archive_confirm_{product_id}"
                )
                if st.button(
                    "Archive",
                    type="primary",
                    width="stretch",
                    disabled=not confirmed,
                    help="Archives the product. Sales and ledger history are kept.",
                ):
                    try:
                        with db.transaction() as conn:
                            archive_product(conn, company_id, actor, product_id)
                        st.success("Product archived. History preserved.")
                        st.rerun()
                    except StockwiseError as exc:
                        handle_error(exc)
            else:
                st.caption("Archived products cannot be edited. History remains intact.")

        st.divider()
        with st.expander("Manual stock adjustment"):
            adjustment_product = st.selectbox(
                "Product",
                options=list(options.keys()),
                key="adjust_product",
            )
            qty = st.number_input("Quantity (+/-)", value=0, step=1, key="adjust_qty")
            reason = st.text_input(
                "Reason",
                placeholder="Damaged, return, cycle count...",
                key="adjust_reason",
            )
            if st.button("Submit adjustment", type="primary", width="stretch"):
                try:
                    with db.transaction() as conn:
                        adjust_stock(
                            conn,
                            company_id,
                            actor,
                            product_id=int(options[adjustment_product]["product_id"]),
                            quantity_change=int(qty),
                            reason=reason,
                        )
                    st.success("Stock adjusted and recorded in the ledger.")
                    st.rerun()
                except StockwiseError as exc:
                    handle_error(exc)
