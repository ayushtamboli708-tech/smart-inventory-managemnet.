"""Stockwise application shell: auth gate, sidebar, and route dispatch."""

from __future__ import annotations

import html
import logging

import streamlit as st

st.set_page_config(
    page_title="Stockwise",
    layout="wide",
    initial_sidebar_state="expanded",
    page_icon="📦",
)

import db  # noqa: E402
from core.auth import clear_session, require_owner, session_user  # noqa: E402
from core.errors import StockwiseError  # noqa: E402
from services.users import (  # noqa: E402
    create_user,
    deactivate_user,
    list_users,
)
from ui.styles import inject_global_styles  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

PAGES = ["Dashboard", "Alerts", "Sales", "Products", "Purchases"]


@st.dialog("User management", width="large")
def show_admin_settings() -> None:
    actor = require_owner(session_user(st))
    company_id = actor.company_id

    st.markdown("### Create an account")
    with st.form("create_user_form", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            username = st.text_input("Username*", placeholder="e.g. cashier_priya")
        with col2:
            password = st.text_input("Password*", type="password")
        with col3:
            role = st.selectbox("Role", ["Staff", "Owner"])
        if st.form_submit_button("Create account", type="primary", width="stretch"):
            if not username or not password:
                st.error("Username and password are required.")
            elif len(password) < 8:
                st.error("Password must be at least 8 characters.")
            else:
                try:
                    with db.transaction() as conn:
                        if conn is None:
                            st.error("Database is unavailable.")
                            return
                        create_user(
                            conn,
                            company_id,
                            actor,
                            username=username,
                            password=password,
                            role=role,
                        )
                    st.success(f"Created {role.lower()} account '{username}'.")
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    if "Duplicate" in str(exc) or "1062" in str(exc):
                        st.error("That username already exists in this workspace.")
                    else:
                        st.error(f"Could not create the account: {exc}")

    st.write("---")
    st.markdown("### Active accounts")
    with db.connection() as conn:
        users = list_users(conn, company_id) if conn else []
    if not users:
        st.info("No active accounts.")
        return
    for user in users:
        col1, col2, col3 = st.columns([4, 1, 1])
        with col1:
            st.markdown(
                f"**{user['username']}** · {user['role']} "
                f"· joined {str(user.get('created_at', ''))[:10]}"
            )
        with col2:
            st.caption("you" if int(user["user_id"]) == actor.user_id else "")
        with col3:
            if st.button(
                "Deactivate",
                key=f"deactivate_{user['user_id']}",
                disabled=int(user["user_id"]) == actor.user_id,
                width="stretch",
            ):
                try:
                    with db.transaction() as conn:
                        if conn is None:
                            st.error("Database is unavailable.")
                            return
                        deactivate_user(
                            conn, company_id, actor, int(user["user_id"])
                        )
                    st.success(f"Deactivated {user['username']}.")
                    st.rerun()
                except StockwiseError as exc:
                    st.error(str(exc))


def sidebar(actor) -> str:
    with st.sidebar:
        st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)
        st.markdown(
            """
            <div style="padding-bottom: 30px; padding-left: 10px;">
                <span style="font-size: 24px; font-weight: 700; color: #111827;
                      letter-spacing: -0.5px;">Stockwise</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.session_state.get("nav_selection") not in PAGES:
            st.session_state.nav_selection = "Dashboard"
        # Only seed the widget state when it does not exist yet. Writing it on
        # every rerun overwrites the value Streamlit just received from the
        # user's click, which pinned the app to whatever page was selected
        # before the click (the "cannot leave the dashboard" bug).
        if "nav_radio" not in st.session_state:
            st.session_state.nav_radio = st.session_state.nav_selection
        selected = st.radio(
            "Navigation",
            PAGES,
            label_visibility="collapsed",
            key="nav_radio",
        )
        st.session_state.nav_selection = selected

        st.markdown("<div style='min-height: 40vh;'></div>", unsafe_allow_html=True)
        st.write("---")
        if actor.role == "Owner":
            if st.button("Admin settings", width="stretch"):
                show_admin_settings()
        if st.button("Logout", width="stretch"):
            clear_session(st)
            st.rerun()
    return selected


def header(page: str, actor) -> None:
    col1, col2 = st.columns([4, 1])
    with col1:
        st.markdown(
            f"<h2 style='margin:0; padding-top:5px;'>{html.escape(page)}</h2>",
            unsafe_allow_html=True,
        )
    with col2:
        badge = "Owner" if actor.role == "Owner" else "Staff"
        st.markdown(
            f"<div style='text-align:right; font-weight:600; padding-top:10px;'>"
            f"{badge} | {html.escape(actor.username)}</div>",
            unsafe_allow_html=True,
        )
    st.markdown("<br>", unsafe_allow_html=True)


def main() -> None:
    for key, value in (
        ("authenticated", False),
        ("role", None),
        ("user_name", None),
        ("company_id", 1),
        ("nav_selection", "Dashboard"),
        ("current_sale_items", []),
        ("current_purchase_items", []),
    ):
        st.session_state.setdefault(key, value)

    inject_global_styles()

    if "schema_ready" not in st.session_state:
        st.session_state.schema_ready = db.schema_is_current()
    if not st.session_state.schema_ready:
        st.error("This database still uses the original Stockwise schema.")
        st.markdown(
            "A new database needs `python scripts/migrate.py`. An existing "
            "database needs the reviewed in-place upgrade:"
        )
        st.code(
            "python scripts/upgrade_legacy.py --apply --backup",
            language="powershell",
        )
        st.caption(
            "Back up first: DDL cannot be rolled back. See migrations/README.md."
        )
        if st.button("Re-check schema"):
            st.session_state.schema_ready = db.schema_is_current()
            st.rerun()
        st.stop()

    actor = session_user(st)
    if actor is None:
        from ui.login_page import show_login_screen

        show_login_screen()
        st.stop()

    selected = sidebar(actor)
    header(selected, actor)

    if selected == "Dashboard":
        from ui.dashboard_page import show_dashboard_page

        show_dashboard_page(actor.company_id, actor)
    elif selected == "Alerts":
        from ui.alert_page import show_alert_page

        show_alert_page()
    elif selected == "Sales":
        from ui.sales_page import show_sales_page

        show_sales_page()
    elif selected == "Products":
        from ui.product_page import show_product_page

        show_product_page()
    elif selected == "Purchases":
        from ui.purchase_page import show_purchase_page

        show_purchase_page()


try:
    with db.request_scope():
        main()
except Exception as exc:  # noqa: BLE001 - never leave a blank terminal
    logging.getLogger("stockwise.app").exception("Unhandled application error")
    st.error("The application hit an unexpected error. Check the server logs.")
    with st.expander("Technical detail"):
        st.code(f"{type(exc).__name__}: {exc}")
