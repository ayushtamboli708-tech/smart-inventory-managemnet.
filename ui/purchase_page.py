"""Procurement page: vendors, multi-vendor cart, and PO lifecycle."""

from __future__ import annotations

import pandas as pd
import streamlit as st

import db
from core.auth import User, can, session_user
from core.cart import cart_total, normalize_cart
from core.config import DEFAULT_PAGE_SIZE
from core.errors import CartError, StockwiseError
from core.time import format_local, local_today
from services.purchases import (
    cancel_purchase,
    create_purchase_orders,
    list_purchases,
    mark_received,
    purchase_summary,
)
from services.vendors import archive_vendor, get_vendor, list_vendors
from ui.components import (
    flash,
    handle_error,
    money,
    page_header,
    server_page,
    server_pagination,
    show_flash,
)
from ui.dialogs import show_vendor_dialog


@st.dialog("Create purchase orders", width="large")
def create_purchase_dialog(company_id: int, actor: User) -> None:
    raw_cart = st.session_state.get("current_purchase_items", [])
    try:
        items = normalize_cart(raw_cart, company_id)
    except CartError as exc:
        st.error(str(exc))
        if st.button("Clear invalid cart", width="stretch"):
            st.session_state.current_purchase_items = []
            st.rerun()
        return

    if not items:
        st.info("Add items from the catalog or the alert page first.")
        return

    st.markdown("#### Smart cart")
    frame = pd.DataFrame(
        [
            {
                "Vendor": item.vendor_name,
                "Product": item.name,
                "Qty": item.quantity,
                "Unit cost": float(item.cost_price),
                "Total": float(item.total),
            }
            for item in items
        ]
    )
    st.dataframe(frame, width="stretch", hide_index=True)

    remove_index = st.selectbox(
        "Remove a line",
        ["Keep all", *[f"{i + 1}. {item.name} ({item.vendor_name})" for i, item in enumerate(items)]],
    )
    if remove_index != "Keep all" and st.button("Remove selected line"):
        index = int(remove_index.split(".")[0]) - 1
        st.session_state.current_purchase_items.pop(index)
        st.rerun()

    col1, col2, col3 = st.columns(3)
    with col1:
        purchase_date = st.date_input("Purchase date", value=local_today())
    with col2:
        status = st.selectbox("Status", ["PENDING", "RECEIVED"])
    with col3:
        st.metric("Grand total", money(cart_total(items)))

    save_col, clear_col = st.columns(2)
    with save_col:
        if st.button("Save orders", type="primary", width="stretch"):
            try:
                with db.transaction() as conn:
                    if conn is None:
                        st.error("Database is unavailable.")
                        return
                    purchase_ids = create_purchase_orders(
                        conn,
                        company_id,
                        actor,
                        items,
                        purchase_date=purchase_date,
                        status=status,
                    )
                st.session_state.current_purchase_items = []
                flash(
                    "success",
                    f"Created {len(purchase_ids)} purchase order(s).",
                )
                st.rerun()
            except StockwiseError as exc:
                handle_error(exc)
    with clear_col:
        if st.button("Clear cart", width="stretch"):
            st.session_state.current_purchase_items = []
            st.rerun()


def _vendor_management(company_id: int, actor: User) -> None:
    if not can(actor, "Owner"):
        return
    with st.expander("Vendor management"):
        with db.connection() as conn:
            vendors = list_vendors(conn, company_id, include_inactive=True) if conn else []
        if not vendors:
            st.info("No vendors yet. Use Add Vendor to create one.")
            return
        labels = {
            f"{vendor['name']} ({'active' if vendor['is_active'] else 'inactive'})": vendor
            for vendor in vendors
        }
        selected = st.selectbox("Vendor", list(labels.keys()), key="vendor_manage_select")
        vendor = labels[selected]
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Edit vendor", width="stretch"):
                with db.connection() as conn:
                    full = get_vendor(conn, company_id, int(vendor["vendor_id"])) if conn else None
                if full:
                    show_vendor_dialog(full)
        with col2:
            confirmed = st.checkbox(
                "Confirm archive", key=f"archive_vendor_{vendor['vendor_id']}"
            )
            if st.button(
                "Archive vendor",
                type="primary",
                width="stretch",
                disabled=not confirmed or not vendor["is_active"],
            ):
                try:
                    with db.transaction() as conn:
                        if conn is None:
                            st.error("Database is unavailable.")
                            return
                        archive_vendor(
                            conn, company_id, actor, int(vendor["vendor_id"])
                        )
                    st.success("Vendor archived.")
                    st.rerun()
                except StockwiseError as exc:
                    handle_error(exc)


def show_purchase_page() -> None:
    actor = session_user(st)
    if actor is None:
        st.error("Please sign in.")
        return
    company_id = actor.company_id
    show_flash()
    st.session_state.setdefault("current_purchase_items", [])

    header, add_vendor, new_purchase = st.columns([3, 1, 1])
    with header:
        page_header("Purchases", "Vendors, procurement, and purchase-order lifecycle")
    with add_vendor:
        if can(actor, "Owner") and st.button("Add vendor", width="stretch"):
            show_vendor_dialog()
    with new_purchase:
        if st.button("New purchase", type="primary", width="stretch"):
            create_purchase_dialog(company_id, actor)

    if st.session_state.pop("open_purchase_dialog", False):
        create_purchase_dialog(company_id, actor)

    _vendor_management(company_id, actor)
    st.write("---")

    with db.connection() as conn:
        if conn is None:
            st.error("Database is unavailable.")
            return
        vendors = list_vendors(conn, company_id, include_inactive=True)
        summary = purchase_summary(conn, company_id)

    filter_cols = st.columns([4, 2, 2])
    with filter_cols[0]:
        search = st.text_input(
            "Search",
            placeholder="Search PO ID or vendor...",
            label_visibility="collapsed",
        )
    with filter_cols[1]:
        vendor_filter = st.selectbox(
            "Vendor", ["All", *[vendor["name"] for vendor in vendors]], label_visibility="collapsed"
        )
    with filter_cols[2]:
        status_filter = st.selectbox(
            "Status", ["All", "PENDING", "RECEIVED", "CANCELLED"], label_visibility="collapsed"
        )

    page = server_page("purchases")
    with db.connection() as conn:
        rows, total = list_purchases(
            conn,
            company_id,
            search=search,
            vendor=vendor_filter,
            status=status_filter,
            page=page,
            page_size=DEFAULT_PAGE_SIZE,
        )

    col1, col2, col3 = st.columns(3)
    col1.metric("Pending value", money(summary["pending_value"]))
    col2.metric("Pending orders", summary["pending_count"])
    col3.metric("Received value", money(summary["received_value"]))

    if not rows:
        st.info("No purchase orders found.")
        server_pagination("purchases", page=page, total=total, page_size=DEFAULT_PAGE_SIZE)
        return

    frame = pd.DataFrame(rows)
    display = frame.copy()
    display["purchase_id"] = display["purchase_id"].apply(
        lambda value: f"PO-{int(value):03d}"
    )
    display["purchase_date"] = display["purchase_date"].apply(
        lambda value: format_local(value, "%d %b %Y, %I:%M %p")
    )
    display["vendor_name"] = display["vendor_name"].fillna("Unknown vendor")
    display["total_amount"] = display["total_amount"].apply(money)
    display = display.rename(
        columns={
            "purchase_id": "PO",
            "purchase_date": "Date",
            "vendor_name": "Vendor",
            "items_count": "Items",
            "total_amount": "Total",
            "status": "Status",
        }
    )
    st.dataframe(
        display[["PO", "Date", "Vendor", "Items", "Total", "Status"]],
        width="stretch",
        hide_index=True,
    )
    server_pagination("purchases", page=page, total=total, page_size=DEFAULT_PAGE_SIZE)

    st.markdown("<br>", unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown("#### Purchase actions")
        options = {
            f"PO-{int(row['purchase_id']):03d} · {row['vendor_name'] or 'Unknown'} ({row['status']})": row
            for row in rows
        }
        selected = st.selectbox("Select a purchase order", ["Select...", *options.keys()])
        if selected == "Select...":
            return
        purchase = options[selected]
        purchase_id = int(purchase["purchase_id"])
        if purchase["status"] == "PENDING":
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Mark as received", type="primary", width="stretch"):
                    try:
                        with db.transaction() as conn:
                            if conn is None:
                                st.error("Database is unavailable.")
                                return
                            mark_received(conn, company_id, actor, purchase_id)
                        flash("success", "Purchase received and stock updated.")
                        st.rerun()
                    except StockwiseError as exc:
                        handle_error(exc)
            with col2:
                confirmed = st.checkbox("Confirm cancellation", key=f"cancel_po_{purchase_id}")
                if st.button(
                    "Cancel purchase",
                    width="stretch",
                    disabled=not confirmed,
                ):
                    try:
                        with db.transaction() as conn:
                            if conn is None:
                                st.error("Database is unavailable.")
                                return
                            cancel_purchase(conn, company_id, actor, purchase_id)
                        flash("success", "Purchase order cancelled.")
                        st.rerun()
                    except StockwiseError as exc:
                        handle_error(exc)
        else:
            st.caption(f"This order is {purchase['status'].lower()} and cannot be changed.")
