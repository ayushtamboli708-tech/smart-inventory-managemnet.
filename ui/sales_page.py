"""POS sales page with stock-checked checkout and refunds."""

from __future__ import annotations

import pandas as pd
import streamlit as st

import db
from core.auth import User, can, session_user
from core.config import DEFAULT_PAGE_SIZE
from core.errors import StockwiseError
from core.time import format_local, local_today
from services.catalog import list_active_products
from services.sales import (
    complete_sale,
    export_sales_rows,
    list_sales,
    refund_sale,
    sales_summary,
)
from ui.components import (
    flash,
    handle_error,
    money,
    page_header,
    server_page,
    server_pagination,
    show_flash,
)


@st.dialog("Create a sale", width="large")
def create_sale_dialog(company_id: int, actor: User) -> None:
    with db.connection() as conn:
        products = list_active_products(conn, company_id) if conn else []
    if not products:
        st.info("No active products are available.")
        return

    labels = {f"{p['name']} ({p['sku']})": p for p in products}
    col1, col2, col3 = st.columns([4, 2, 2])
    with col1:
        selected = st.selectbox("Product", list(labels.keys()))
    with col2:
        qty = st.number_input("Qty", min_value=1, step=1, value=1)
    with col3:
        st.write("")
        st.write("")
        if st.button("Add item", width="stretch"):
            product = labels[selected]
            cart = st.session_state.setdefault("current_sale_items", [])
            already = sum(
                int(item["quantity"])
                for item in cart
                if int(item["product_id"]) == int(product["product_id"])
            )
            if already + int(qty) > float(product["stock_qty"]):
                st.warning(
                    f"Only {product['stock_qty']:g} units of {product['name']} are available."
                )
            else:
                cart.append(
                    {
                        "product_id": int(product["product_id"]),
                        "name": product["name"],
                        "price": float(product["selling_price"]),
                        "quantity": int(qty),
                    }
                )
                st.rerun()

    cart = st.session_state.setdefault("current_sale_items", [])
    if not cart:
        st.info("The cart is empty.")
        return

    frame = pd.DataFrame(cart)
    frame["total"] = frame["price"] * frame["quantity"]
    st.dataframe(
        frame.rename(
            columns={"name": "Item", "price": "Price", "quantity": "Qty", "total": "Total"}
        )[["Item", "Qty", "Price", "Total"]],
        width="stretch",
        hide_index=True,
    )
    st.markdown(f"**Total: {money(frame['total'].sum())}**")

    remove_col, action_col = st.columns([2, 2])
    with remove_col:
        remove_label = st.selectbox(
            "Remove line", ["Keep all", *[f"{i + 1}. {item['name']}" for i, item in enumerate(cart)]]
        )
        if remove_label != "Keep all" and st.button("Remove selected", width="stretch"):
            index = int(remove_label.split(".")[0]) - 1
            cart.pop(index)
            st.rerun()
    with action_col:
        st.write("")
        st.write("")
        if st.button("Complete sale", type="primary", width="stretch"):
            try:
                with db.transaction() as conn:
                    if conn is None:
                        st.error("Database is unavailable.")
                        return
                    result = complete_sale(conn, company_id, actor, cart)
                st.session_state.current_sale_items = []
                flash(
                    "success",
                    f"Sale SALE-{result['sale_id']} completed for {money(result['total'])}.",
                )
                st.rerun()
            except StockwiseError as exc:
                handle_error(exc)
        if st.button("Cancel", width="stretch"):
            st.session_state.current_sale_items = []
            st.rerun()


def show_sales_page() -> None:
    actor = session_user(st)
    if actor is None:
        st.error("Please sign in.")
        return
    company_id = actor.company_id
    show_flash()
    st.session_state.setdefault("current_sale_items", [])

    header, action = st.columns([4, 1])
    with header:
        page_header("Sales", "Checkout, history, refunds, and exports")
    with action:
        if st.button("New sale", type="primary", width="stretch"):
            create_sale_dialog(company_id, actor)

    filter_col1, filter_col2 = st.columns([3, 1])
    with filter_col1:
        search = st.text_input(
            "Search",
            placeholder="Search sale ID or product name...",
            label_visibility="collapsed",
        )
    with filter_col2:
        date_filter = st.selectbox(
            "Date", ["All Time", "Today", "Last 7 Days"], label_visibility="collapsed"
        )

    page = server_page("sales")
    with db.connection() as conn:
        if conn is None:
            st.error("Database is unavailable.")
            return
        rows, total = list_sales(
            conn,
            company_id,
            search=search,
            date_filter=date_filter,
            page=page,
            page_size=DEFAULT_PAGE_SIZE,
        )
        summary = sales_summary(
            conn, company_id, search=search, date_filter=date_filter
        )

    col1, col2 = st.columns(2)
    col1.metric("Revenue (completed)", money(summary["revenue"]))
    col2.metric("Transactions", summary["transactions"])

    if not rows:
        st.info("No sales found.")
        server_pagination("sales", page=page, total=total, page_size=DEFAULT_PAGE_SIZE)
        return

    frame = pd.DataFrame(rows)
    display = frame.copy()
    display["sale_id"] = display["sale_id"].apply(lambda value: f"SALE-{value}")
    display["sale_date"] = display["sale_date"].apply(
        lambda value: format_local(value, "%d %b %Y, %I:%M %p")
    )
    display = display.rename(
        columns={
            "sale_id": "Sale",
            "sale_date": "Date",
            "items_count": "Lines",
            "units_count": "Units",
            "total_amount": "Total",
            "status": "Status",
        }
    )
    display["Total"] = display["Total"].apply(money)
    st.dataframe(
        display[["Sale", "Date", "Lines", "Units", "Total", "Status"]],
        width="stretch",
        hide_index=True,
    )
    server_pagination("sales", page=page, total=total, page_size=DEFAULT_PAGE_SIZE)

    st.write("---")
    export_filter = f"{search}|{date_filter}"
    if st.button("Prepare filtered sales CSV"):
        st.session_state.sales_export_filter = export_filter
    if st.session_state.get("sales_export_filter") == export_filter:
        with db.connection() as conn:
            export_rows = (
                export_sales_rows(
                    conn, company_id, search=search, date_filter=date_filter
                )
                if conn
                else []
            )
        export = pd.DataFrame(export_rows)
        if export.empty:
            st.info("Nothing to export.")
        else:
            export["sale_date"] = pd.to_datetime(export["sale_date"]).dt.strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            st.download_button(
                "Download CSV",
                data=export.to_csv(index=False).encode("utf-8"),
                file_name=f"stockwise_sales_{local_today().isoformat()}.csv",
                mime="text/csv",
                width="stretch",
            )

    if can(actor, "Owner"):
        st.write("---")
        with st.container(border=True):
            st.markdown("#### Refund a sale")
            refundable = {
                f"SALE-{row['sale_id']} · {money(row['total_amount'])}": row
                for row in rows
                if row["status"] == "COMPLETED"
            }
            if not refundable:
                st.info("No completed sales on this page.")
            else:
                selected = st.selectbox("Sale", list(refundable.keys()))
                confirmed = st.checkbox(
                    "I understand this restores stock and marks the sale refunded."
                )
                if st.button(
                    "Refund selected sale",
                    type="primary",
                    disabled=not confirmed,
                    width="stretch",
                ):
                    try:
                        with db.transaction() as conn:
                            if conn is None:
                                st.error("Database is unavailable.")
                                return
                            refund_sale(
                                conn,
                                company_id,
                                actor,
                                int(refundable[selected]["sale_id"]),
                            )
                        flash("success", "Sale refunded and stock restored.")
                        st.rerun()
                    except StockwiseError as exc:
                        handle_error(exc)
