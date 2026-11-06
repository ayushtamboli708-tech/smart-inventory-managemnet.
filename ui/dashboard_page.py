"""Dashboard page, extracted from the application shell."""

from __future__ import annotations

import html
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

import db
from core.auth import User, can
from core.cart import add_item, make_cart_item
from core.config import OVERSTOCK_MIN_UNITS, OVERSTOCK_MULTIPLIER
from core.errors import StockwiseError
from core.time import format_local
from forecast.forecasting_engine import (
    latest_run,
    pending_reorder_suggestions,
    product_forecast,
    run_full_analysis,
)
from services.catalog import list_active_products, search_products
from services.dashboard import (
    get_dashboard_summary,
    inventory_snapshot,
    top_selling,
)
from services.vendors import list_vendors
from ui.components import data_table, money, page_header


@st.dialog("Inventory details", width="large")
def show_inventory_dialog(kpi_type: str, company_id: int) -> None:
    with db.connection() as conn:
        rows = inventory_snapshot(conn, company_id) if conn else []
    if not rows:
        st.info("No inventory data.")
        return
    frame = pd.DataFrame(rows)
    if kpi_type == "Low Stock":
        frame = frame[(frame["stock_qty"] > 0) & (frame["stock_qty"] <= frame["reorder_threshold"])]
    elif kpi_type == "Out of Stock":
        frame = frame[frame["stock_qty"] <= 0]
    elif kpi_type == "Reorder Needed":
        frame = frame[frame["stock_qty"] <= frame["reorder_threshold"]]
    elif kpi_type == "Overstock":
        frame = frame[
            (frame["stock_qty"] > frame["reorder_threshold"] * OVERSTOCK_MULTIPLIER)
            & (frame["stock_qty"] > OVERSTOCK_MIN_UNITS)
        ]
    if frame.empty:
        st.info("No items in this category.")
        return
    display = frame.rename(
        columns={
            "name": "Product",
            "sku": "SKU",
            "category": "Category",
            "stock_qty": "Stock",
            "reorder_threshold": "Threshold",
            "selling_price": "Price",
        }
    )
    st.dataframe(display, width="stretch", hide_index=True)


@st.dialog("ML demand forecast", width="large")
def show_forecast_dialog(company_id: int, actor: User) -> None:
    with db.connection() as conn:
        products = list_active_products(conn, company_id) if conn else []
        vendors = list_vendors(conn, company_id) if conn else []
        run = latest_run(conn, company_id) if conn else None

    header, refresh = st.columns([3, 1])
    with header:
        st.markdown("### Forecast workspace")
        if run:
            st.caption(
                f"Last run {format_local(run.get('finished_at') or run.get('started_at'))} · "
                f"MAPE {run.get('mape') if run.get('mape') is not None else 'n/a'} · "
                f"RMSE {run.get('rmse') if run.get('rmse') is not None else 'n/a'} · "
                f"{run.get('products_processed', 0)} products"
            )
    with refresh:
        if can(actor, "Owner") and st.button(
            "Retrain", type="primary", width="stretch"
        ):
            with db.connection() as conn:
                if conn is None:
                    st.error("Database is unavailable.")
                else:
                    progress = st.progress(0.0, text="Fitting SARIMA models...")

                    def report(index: int, total: int, name: str) -> None:
                        progress.progress(
                            index / max(total, 1), text=f"Analyzed {index}/{total}: {name}"
                        )

                    result = run_full_analysis(
                        conn, company_id, actor.user_id, progress=report
                    )
                    progress.empty()
                    st.success(
                        f"Forecasts updated: {result['processed']} products, "
                        f"MAPE {result['mape']}, RMSE {result['rmse']}."
                    )
            st.rerun()

    if not products:
        st.info("Add products before forecasting.")
        return

    labels = {f"{p['name']} ({p['sku']})": p for p in products}
    selected = st.selectbox("Product", list(labels.keys()))
    product = labels[selected]

    with db.connection() as conn:
        forecast_rows = product_forecast(conn, company_id, int(product["product_id"])) if conn else []
    if forecast_rows:
        frame = pd.DataFrame(forecast_rows)
        frame["forecast_date"] = pd.to_datetime(frame["forecast_date"])
        frame["predicted_demand"] = pd.to_numeric(
            frame["predicted_demand"], errors="coerce"
        ).astype(float)
        fig = px.line(
            frame,
            x="forecast_date",
            y="predicted_demand",
            markers=True,
            color_discrete_sequence=["#8B5CF6"],
            labels={"forecast_date": "Date", "predicted_demand": "Predicted units"},
        )
        fig.update_layout(
            margin=dict(t=20, b=20, l=20, r=20),
            height=240,
            xaxis=dict(showgrid=False, type="date", tickformat="%b %d"),
            yaxis=dict(showgrid=True, gridcolor="#F3F4F6"),
        )
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    else:
        st.info("No forecasts yet. Run Retrain to generate them.")

    st.divider()
    st.markdown("#### Add to purchase cart")
    if not vendors:
        st.warning("Add a vendor before creating a purchase order.")
        return
    vendor_labels = {v["name"]: int(v["vendor_id"]) for v in vendors}
    with st.form("forecast_cart_form"):
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            vendor = st.selectbox("Vendor", list(vendor_labels.keys()))
        with col2:
            qty = st.number_input("Qty", min_value=1, step=1, value=1)
        with col3:
            cost = st.number_input(
                "Unit cost (₹)",
                min_value=0.0,
                step=1.0,
                value=float(product.get("selling_price", 0)) * 0.7,
            )
        if st.form_submit_button("Add to cart", type="primary", width="stretch"):
            try:
                item = make_cart_item(
                    company_id=company_id,
                    product_id=int(product["product_id"]),
                    product_name=str(product["name"]),
                    vendor_id=vendor_labels[vendor],
                    vendor_name=vendor,
                    quantity=int(qty),
                    cost_price=cost,
                    source="forecast",
                )
                add_item(st.session_state.setdefault("current_purchase_items", []), item)
                st.session_state.open_purchase_dialog = True
                st.session_state.nav_selection = "Purchases"
                st.rerun()
            except StockwiseError as exc:
                st.error(str(exc))


def _render_kpi(
    column: Any,
    title: str,
    value: int,
    accent: str,
    kpi_type: str,
    company_id: int,
) -> None:
    with column:
        st.markdown(
            f"""
            <div class="dashboard-card" style="border-left: 4px solid {accent};">
                <div class="kpi-label">{title}</div>
                <div class="kpi-num">{value}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("View list", key=f"kpi_{kpi_type}", width="stretch"):
            show_inventory_dialog(kpi_type, company_id)


def show_dashboard_page(company_id: int, actor: User) -> None:
    page_header("Dashboard", "Inventory health, sales activity, and demand signals")

    search = st.text_input(
        "Search", placeholder="Search any product by name or SKU...", label_visibility="collapsed"
    )
    if search:
        with db.connection() as conn:
            results = search_products(conn, company_id, search, limit=1) if conn else []
        if results:
            product = results[0]
            with st.container(border=True):
                st.markdown(f"#### {html.escape(str(product['name']))}")
                cols = st.columns(4)
                cols[0].metric("SKU", product["sku"])
                cols[1].metric("Category", product["category"])
                cols[2].metric("Price", money(product["selling_price"]))
                cols[3].metric("Stock", f"{product['stock_qty']:g}")
        else:
            st.warning(f"No product found matching '{search}'")

    with db.connection() as conn:
        if conn is None:
            st.error("Database is unavailable. Check your connection configuration.")
            return
        data = get_dashboard_summary(conn, company_id)
        current_top_selling = data["top_selling"]

    kpi = data["kpi"]
    col1, col2, col3, col4 = st.columns(4)
    _render_kpi(col1, "Low Stock", kpi["low"], "#F59E0B", "Low Stock", company_id)
    _render_kpi(col2, "Out of Stock", kpi["out"], "#EF4444", "Out of Stock", company_id)
    _render_kpi(col3, "Active Products", kpi["active"], "#10B981", "Active Products", company_id)
    _render_kpi(col4, "Reorder Needed", kpi["reorder"], "#3B82F6", "Reorder Needed", company_id)

    st.markdown("<br>", unsafe_allow_html=True)
    left, right = st.columns([1, 1])
    with left:
        st.markdown("<div class='section-title'>Inventory health</div>", unsafe_allow_html=True)
        health = data["health"]
        score = int(health["score"])
        color = "#10B981" if score > 70 else "#F59E0B"
        st.markdown(
            f"""
            <div class="dashboard-card" style="height:280px; display:flex; flex-direction:column; justify-content:center;">
                <div style="display:flex; justify-content:space-between;"><span>Score</span>
                    <span style="font-size:32px; font-weight:bold; color:{color}">{score}%</span></div>
                <div style="background:#F3F4F6; height:12px; border-radius:6px; margin:10px 0 30px;">
                    <div style="width:{score}%; background:{color}; height:100%; border-radius:6px;"></div></div>
                <div style="display:flex; justify-content:space-between; margin-bottom:10px;">
                    <span>Qty on hand</span><b>{int(health['qty_hand']):,}</b></div>
                <div style="display:flex; justify-content:space-between;">
                    <span>Pending PO value</span><b>{money(health['po_value'])}</b></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with right:
        heading, period_col = st.columns([2, 1])
        heading.markdown("<div class='section-title'>Top selling</div>", unsafe_allow_html=True)
        period = period_col.selectbox(
            "Period", ["All Time", "This Month"], label_visibility="collapsed"
        )
        if period == "This Month":
            with db.connection() as conn:
                current_top_selling = top_selling(conn, company_id, period) if conn else current_top_selling
        with st.container(border=True):
            if not current_top_selling.empty:
                figure = px.pie(
                    current_top_selling,
                    values="Sales",
                    names="Product",
                    hole=0.6,
                    color_discrete_sequence=px.colors.qualitative.Prism,
                )
                figure.update_layout(
                    margin=dict(t=20, b=20, l=20, r=20), height=230, showlegend=True
                )
                st.plotly_chart(figure, width="stretch")
            else:
                st.info("No completed sales yet.")

    st.markdown("<br>", unsafe_allow_html=True)
    revenue_col, activity_col = st.columns([1.5, 1])
    with revenue_col:
        st.markdown("<div class='section-title'>30-day revenue trend</div>", unsafe_allow_html=True)
        with st.container(border=True):
            if not data["revenue_trend"].empty:
                frame = data["revenue_trend"].copy()
                frame["Day"] = pd.to_datetime(frame["Day"])
                figure = px.line(
                    frame,
                    x="Day",
                    y="Revenue",
                    markers=True,
                    color_discrete_sequence=["#10B981"],
                    labels={"Day": "Date", "Revenue": "Revenue (₹)"},
                )
                figure.update_layout(
                    margin=dict(t=20, b=20, l=20, r=20),
                    height=230,
                    xaxis=dict(showgrid=False, type="date", tickformat="%b %d"),
                    yaxis=dict(showgrid=True, gridcolor="#F3F4F6"),
                )
                st.plotly_chart(
                    figure, width="stretch", config={"displayModeBar": False}
                )
            else:
                st.info("No sales recorded in the last 30 days.")

    with activity_col:
        st.markdown("<div class='section-title'>Recent sales</div>", unsafe_allow_html=True)
        recent = data["recent_sales"]
        if recent:
            frame = pd.DataFrame(recent)
            frame["sale_date"] = frame["sale_date"].apply(
                lambda value: format_local(value, "%d %b, %H:%M")
            )
            frame = frame.rename(
                columns={
                    "sale_id": "Sale",
                    "sale_date": "Date",
                    "total_amount": "Amount",
                    "status": "Status",
                }
            )
            st.dataframe(frame, width="stretch", hide_index=True)
        else:
            st.info("No recent sales activity.")

    st.markdown("<br>", unsafe_allow_html=True)
    reorder_col, forecast_col = st.columns([1.5, 1])
    with reorder_col:
        st.markdown("<div class='section-title'>Reorder suggestions</div>", unsafe_allow_html=True)
        with db.connection() as conn:
            suggestions = pending_reorder_suggestions(conn, company_id) if conn else []
        if suggestions:
            frame = pd.DataFrame(suggestions)
            frame = frame.rename(
                columns={
                    "name": "Product",
                    "sku": "SKU",
                    "stock_qty": "Stock",
                    "recommended_quantity": "Suggested",
                    "vendor_name": "Vendor",
                }
            )
            data_table(
                frame[["Product", "SKU", "Stock", "Suggested", "Vendor"]],
                key="dashboard_reorders",
                page_size=10,
                empty_message="No reorder suggestions.",
            )
        else:
            st.success("No urgent reorders.")

    with forecast_col:
        heading, filter_col = st.columns([2, 1])
        heading.markdown("<div class='section-title'>Demand forecast</div>", unsafe_allow_html=True)
        with db.connection() as conn:
            products = list_active_products(conn, company_id) if conn else []
        options = ["All products"] + [str(p["name"]) for p in products]
        selected = filter_col.selectbox("Product", options, label_visibility="collapsed")
        if selected != "All products":
            product = next(p for p in products if str(p["name"]) == selected)
            with db.connection() as conn:
                rows = product_forecast(conn, company_id, int(product["product_id"])) if conn else []
            with st.container(border=True):
                if rows:
                    frame = pd.DataFrame(rows)
                    frame["forecast_date"] = pd.to_datetime(frame["forecast_date"])
                    frame["predicted_demand"] = pd.to_numeric(
                        frame["predicted_demand"], errors="coerce"
                    ).astype(float)
                    figure = px.line(
                        frame,
                        x="forecast_date",
                        y="predicted_demand",
                        markers=True,
                        color_discrete_sequence=["#8B5CF6"],
                        labels={"forecast_date": "Date", "predicted_demand": "Predicted units"},
                    )
                    figure.update_layout(
                        margin=dict(t=20, b=20, l=20, r=20),
                        height=240,
                        xaxis=dict(showgrid=False),
                        yaxis=dict(showgrid=True, gridcolor="#F3F4F6"),
                    )
                    st.plotly_chart(
                        figure, width="stretch", config={"displayModeBar": False}
                    )
                else:
                    st.info("Run the forecast engine to see data.")
        else:
            with st.container(border=True):
                if not data["forecast_preview"].empty:
                    frame = pd.DataFrame(data["forecast_preview"])
                    frame["Day"] = pd.to_datetime(frame["Day"])
                    figure = px.line(
                        frame,
                        x="Day",
                        y="Expected Sales",
                        markers=True,
                        color_discrete_sequence=["#8B5CF6"],
                        labels={"Day": "Date", "Expected Sales": "Predicted units"},
                    )
                    figure.update_layout(
                        margin=dict(t=20, b=20, l=20, r=20),
                        height=240,
                        xaxis=dict(showgrid=False),
                        yaxis=dict(showgrid=True, gridcolor="#F3F4F6"),
                    )
                    st.plotly_chart(
                        figure, width="stretch", config={"displayModeBar": False}
                    )
                else:
                    st.info("No forecast run yet.")

    if st.button(" ", key="fab_main", help="AI forecast"):
        show_forecast_dialog(company_id, actor)
