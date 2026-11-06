"""Role-aware login screen.

Staff no longer use a shared PIN that could silently disappear from secrets.
Both roles authenticate against named, hashed accounts, so every action has an
identity and the app fails closed when no staff account exists.
"""

from __future__ import annotations

import time

import streamlit as st

import db
from core.auth import (
    authenticate_user,
    clear_session,
    find_company,
    set_session_user,
)
from core.errors import StockwiseError
from services.users import record_login

MAX_FAILURES = 5
LOCK_SECONDS = 60


def _default_company_code() -> str:
    try:
        return str(st.secrets.get("app", {}).get("company_code", "demo"))
    except Exception:
        return "demo"


def _locked() -> int:
    until = float(st.session_state.get("login_locked_until", 0) or 0)
    remaining = int(until - time.time())
    return max(0, remaining)


def _record_failure() -> None:
    failures = int(st.session_state.get("login_failures", 0) or 0) + 1
    st.session_state.login_failures = failures
    if failures >= MAX_FAILURES:
        st.session_state.login_locked_until = time.time() + LOCK_SECONDS
        st.session_state.login_failures = 0


def _attempt(role: str, company_code: str, username: str, password: str) -> bool:
    with db.transaction() as conn:
        if conn is None:
            st.error("Database is unavailable. Check the connection settings.")
            return False
        company = find_company(conn, company_code)
        if not company:
            return False
        user = authenticate_user(
            conn,
            username,
            password,
            int(company["company_id"]),
            role=role,
        )
        if not user:
            return False
        record_login(conn, user.company_id, user)
        set_session_user(st, user)
        st.session_state.company_code = company["code"]
        return True


def _login_form(role: str) -> None:
    label = "Owner" if role == "Owner" else "Staff"
    st.markdown(
        f"<h2 style='margin-top:0; font-weight:800; text-align:center;'>{label} sign in</h2>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<p style='color:#6B7280; font-size:14px; margin-bottom:20px; text-align:center;'>"
        "Use the account your owner created for you.</p>",
        unsafe_allow_html=True,
    )

    remaining = _locked()
    if remaining:
        st.warning(f"Too many attempts. Try again in {remaining} seconds.")
        if st.button("Back", width="stretch"):
            st.session_state.login_mode = None
            st.rerun()
        return

    with st.form(f"{role.lower()}_login_form"):
        company_code = st.text_input(
            "Workspace code", value=st.session_state.get("company_code", _default_company_code())
        )
        username = st.text_input("Username", placeholder="Enter username")
        password = st.text_input("Password", type="password", placeholder="Enter password")
        submitted = st.form_submit_button(
            "Unlock Terminal", type="primary", width="stretch"
        )

    if submitted:
        if not company_code or not username or not password:
            st.error("Workspace, username, and password are required.")
        else:
            try:
                if _attempt(role, company_code, username, password):
                    st.session_state.login_failures = 0
                    st.session_state.login_mode = None
                    st.rerun()
                _record_failure()
                st.error("Incorrect workspace, username, or password.")
            except StockwiseError as exc:
                st.error(str(exc))
            except Exception:  # noqa: BLE001
                st.error("Sign-in failed. Please try again.")

    if st.button("← Back to role selection", width="stretch"):
        st.session_state.login_mode = None
        st.rerun()


def show_login_screen() -> None:
    if "login_mode" not in st.session_state:
        st.session_state.login_mode = None
    if "company_code" not in st.session_state:
        st.session_state.company_code = _default_company_code()

    left, right = st.columns([1, 1], gap="large")
    with left:
        st.markdown(
            """
            <div class='brand-box'>
                <div class='brand-title'>STOCKWISE</div>
                <div class='brand-sub'>Fast. Simple. Reliable.</div>
                <div class='version-text'>Stockwise Enterprise POS v2.1</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with right:
        with st.container(border=True):
            mode = st.session_state.login_mode
            if mode in ("Owner", "Staff"):
                _login_form(mode)
            else:
                st.markdown(
                    "<h2 style='margin-top:0; font-weight:800; text-align:center;'>"
                    "Terminal Access</h2>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    "<p style='color:#6B7280; font-size:14px; margin-bottom:30px; "
                    "text-align:center;'>Select your role to continue.</p>",
                    unsafe_allow_html=True,
                )
                if st.button("Staff sign in", width="stretch"):
                    st.session_state.login_mode = "Staff"
                    st.rerun()
                st.caption("Named staff account required.")
                if st.button(
                    "Owner sign in", type="primary", width="stretch"
                ):
                    st.session_state.login_mode = "Owner"
                    st.rerun()
                st.caption("Owner accounts can manage users and catalog data.")
                if st.button("Clear session", width="stretch"):
                    clear_session(st)
                    st.rerun()
