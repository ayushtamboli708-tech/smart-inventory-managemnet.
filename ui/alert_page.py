"""Alerts page: low stock, overstock, and ML reorder suggestions."""

from __future__ import annotations

import pandas as pd
import streamlit as st

import db
from core.auth import session_user
from core.config import OVERSTOCK_MIN_UNITS, OVERSTOCK_MULTIPLIER
from forecast.forecasting_engine import pending_reorder_suggestions
from services.catalog import low_stock_rows
from services.dashboard import inventory_snapshot
from ui.components import data_table, page_header
from ui.dialogs import show_add_to_cart_dialog


def show_alert_page() -> None:
    actor = session_user(st)
    if actor is None:
        st.error("Please sign in.")
        return
    company_id = actor.company_id

    st.session_state.setdefault("alerts_muted", False)

    header, action = st.columns([4, 1])
    with header:
        page_header("Alerts", "Inventory risks and reorder signals")
    with action:
        if st.button("Silence toasts", width="stretch"):
            st.session_state.alerts_muted = True
            st.toast("Toasts are silenced for this session.", icon="✅")

    with db.connection() as conn:
        if conn is None:
            st.error("Database is unavailable.")
            return
        low_rows = low_stock_rows(conn, company_id)
        snapshot = inventory_snapshot(conn, company_id)
        suggestions = pending_reorder_suggestions(conn, company_id)

    low_frame = pd.DataFrame(low_rows)
    if not low_frame.empty:
        low_frame["severity"] = low_frame["stock_qty"].apply(
            lambda value: "High" if float(value) <= 0 else "Medium"
        )
        low_frame["issue"] = low_frame["stock_qty"].apply(
            lambda value: "Out of stock" if float(value) <= 0 else "Stock critically low"
        )

    over_frame = pd.DataFrame(snapshot)
    if not over_frame.empty:
        over_frame = over_frame[
            (over_frame["stock_qty"] > over_frame["reorder_threshold"] * OVERSTOCK_MULTIPLIER)
            & (over_frame["stock_qty"] > OVERSTOCK_MIN_UNITS)
        ].copy()
        if not over_frame.empty:
            over_frame["value_locked"] = over_frame["stock_qty"] * over_frame["selling_price"]
            over_frame["severity"] = "Low"

    reorder_frame = pd.DataFrame(suggestions)
    out_of_stock = 0
    if not low_frame.empty:
        out_of_stock = int((low_frame["stock_qty"] <= 0).sum())
    if not st.session_state.alerts_muted and out_of_stock:
        st.toast(
            f"{out_of_stock} item(s) are completely out of stock.",
            icon="⚠️",
        )

    col1, col2, col3 = st.columns(3)
    col1.metric("Low stock / out", len(low_frame))
    col2.metric("Reorder required", len(reorder_frame))
    col3.metric("Overstock", len(over_frame))

    st.write("---")
    filter_col1, filter_col2 = st.columns([1, 1])
    with filter_col1:
        alert_type = st.selectbox(
            "Alert type", ["All Alerts", "Low Stock", "Reorder Required", "Overstock"]
        )
    with filter_col2:
        severity = st.selectbox("Severity", ["All", "High", "Medium", "Low"])

    if (
        alert_type == "All Alerts"
        and low_frame.empty
        and reorder_frame.empty
        and over_frame.empty
    ):
        st.success("No active alerts. Inventory is within its thresholds.")
        return

    if alert_type in ("All Alerts", "Low Stock"):
        st.markdown("#### Low stock")
        display = low_frame.copy()
        if severity == "High":
            display = display[display["severity"] == "High"]
        elif severity == "Medium":
            display = display[display["severity"] == "Medium"]
        elif severity == "Low":
            display = display.iloc[0:0]
        if display.empty:
            st.success("No low-stock alerts at this severity.")
        else:
            display = display.rename(
                columns={
                    "name": "Product",
                    "sku": "SKU",
                    "category": "Category",
                    "stock_qty": "Stock",
                    "reorder_threshold": "Threshold",
                    "issue": "Issue",
                    "severity": "Severity",
                }
            )
            data_table(
                display[
                    ["Product", "SKU", "Stock", "Threshold", "Issue", "Severity"]
                ],
                key="alerts_low",
                page_size=10,
            )

    if alert_type in ("All Alerts", "Reorder Required"):
        st.markdown("#### ML reorder suggestions")
        if reorder_frame.empty:
            st.info("No reorder suggestions. Run the forecast engine to refresh them.")
        else:
            display = reorder_frame.copy()
            display["vendor_name"] = display["vendor_name"].fillna("No primary vendor")
            display = display.rename(
                columns={
                    "name": "Product",
                    "sku": "SKU",
                    "stock_qty": "Stock",
                    "recommended_quantity": "Suggested",
                    "vendor_name": "Vendor",
                }
            )
            data_table(
                display[["Product", "SKU", "Stock", "Suggested", "Vendor"]],
                key="alerts_reorder",
                page_size=10,
            )

            st.markdown("<br>", unsafe_allow_html=True)
            with st.container(border=True):
                st.write("**Draft a purchase order**")
                labels = {
                    f"{row['name']} ({row['sku']}) · {row['recommended_quantity']} units": row
                    for row in suggestions
                }
                selected = st.selectbox(
                    "Select a suggestion",
                    ["Select...", *labels.keys()],
                    label_visibility="collapsed",
                )
                if selected != "Select..." and st.button(
                    "Add to purchase cart", type="primary"
                ):
                    row = labels[selected]
                    show_add_to_cart_dialog(
                        {
                            "product_id": row["product_id"],
                            "name": row["name"],
                            "sku": row["sku"],
                            "selling_price": row["selling_price"],
                        },
                        default_qty=int(row["recommended_quantity"]),
                        suggestion_id=int(row["suggestion_id"]),
                    )

    if alert_type in ("All Alerts", "Overstock"):
        st.markdown("#### Overstock")
        display = over_frame.copy()
        if severity in ("High", "Medium"):
            display = display.iloc[0:0]
        if display.empty:
            st.info("No overstock warnings at this severity.")
        else:
            display = display.rename(
                columns={
                    "name": "Product",
                    "sku": "SKU",
                    "stock_qty": "Stock",
                    "reorder_threshold": "Threshold",
                    "value_locked": "Value locked",
                    "severity": "Severity",
                }
            )
            display["Value locked"] = display["Value locked"].apply(
                lambda value: f"₹{float(value):,.2f}"
            )
            data_table(
                display[["Product", "SKU", "Stock", "Threshold", "Value locked", "Severity"]],
                key="alerts_overstock",
                page_size=10,
            )
