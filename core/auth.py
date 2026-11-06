"""Authentication, role policy, and session helpers."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

import bcrypt

from core.errors import PermissionDenied
from core.time import utc_now

logger = logging.getLogger("stockwise.auth")

BCRYPT_PREFIXES = ("$2a$", "$2b$", "$2y$")


@dataclass(frozen=True)
class User:
    user_id: int
    company_id: int
    username: str
    role: str


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("Password cannot be empty.")
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, stored: str) -> bool:
    if not stored:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), stored.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def is_legacy_plaintext(stored: str) -> bool:
    return bool(stored) and not stored.startswith(BCRYPT_PREFIXES)


def plaintext_login_enabled() -> bool:
    """Explicit, opt-in escape hatch for a pre-upgrade database.

    Default is ``False`` so a row that is not a bcrypt hash can never
    authenticate. Set ``STOCKWISE_ALLOW_PLAINTEXT=1`` only while migrating.
    """
    return os.getenv("STOCKWISE_ALLOW_PLAINTEXT", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def hash_legacy_passwords(conn: Any) -> int:
    """Replace every non-bcrypt password with its bcrypt hash in place.

    A legacy row stores the password itself, so hashing it directly preserves
    the user's existing credentials. Returns the number of rows changed.
    """
    cursor = conn.cursor(dictionary=True)
    changed = 0
    try:
        cursor.execute("SELECT user_id, password FROM users")
        for row in cursor.fetchall():
            stored = str(row.get("password") or "")
            if not is_legacy_plaintext(stored):
                continue
            cursor.execute(
                "UPDATE users SET password = %s, updated_at = %s WHERE user_id = %s",
                (hash_password(stored), utc_now(), row["user_id"]),
            )
            changed += 1
        conn.commit()
        return changed
    finally:
        cursor.close()


def authenticate_user(
    conn: Any,
    username: str,
    password: str,
    company_id: int,
    *,
    role: str | None = None,
) -> User | None:
    """Return the user when credentials match, otherwise ``None``.

    Only bcrypt hashes authenticate. A legacy plaintext row is refused unless
    an operator explicitly sets ``STOCKWISE_ALLOW_PLAINTEXT=1`` while running
    the one-time migration. Staff use named accounts rather than a shared PIN,
    so every action can be attributed.
    """
    if not username or not password:
        return None
    cursor = conn.cursor(dictionary=True)
    try:
        query = (
            "SELECT user_id, company_id, username, password, role, is_active "
            "FROM users WHERE company_id = %s AND username = %s"
        )
        params: list[Any] = [company_id, username]
        if role:
            query += " AND role = %s"
            params.append(role)
        query += " LIMIT 1"
        cursor.execute(query, tuple(params))
        row = cursor.fetchone()
        if not row or not row.get("is_active", 1):
            return None

        stored = str(row["password"])
        if verify_password(password, stored):
            return User(
                user_id=int(row["user_id"]),
                company_id=int(row["company_id"]),
                username=str(row["username"]),
                role=str(row["role"]),
            )

        if is_legacy_plaintext(stored):
            if not plaintext_login_enabled():
                logger.warning(
                    "Refusing non-bcrypt password for user_id=%s; "
                    "run scripts/hash_legacy_passwords.py --apply",
                    row["user_id"],
                )
                return None
            if password == stored:
                cursor.execute(
                    "UPDATE users SET password = %s, updated_at = %s WHERE user_id = %s",
                    (hash_password(password), utc_now(), row["user_id"]),
                )
                conn.commit()
                return User(
                    user_id=int(row["user_id"]),
                    company_id=int(row["company_id"]),
                    username=str(row["username"]),
                    role=str(row["role"]),
                )
        return None
    finally:
        cursor.close()


def authenticate_owner(
    conn: Any, username: str, password: str, company_id: int
) -> User | None:
    return authenticate_user(
        conn, username, password, company_id, role="Owner"
    )


def find_company(conn: Any, code: str) -> dict | None:
    if not code:
        return None
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT company_id, code, name FROM companies WHERE code = %s LIMIT 1",
            (code.strip().lower(),),
        )
        return cursor.fetchone()
    finally:
        cursor.close()


def staff_pin_configured(configured_pin: str | None) -> bool:
    return bool(configured_pin and str(configured_pin).strip())


def authenticate_staff_pin(pin_input: str, configured_pin: str | None) -> bool:
    """Fail closed: no configured PIN means no staff access."""
    if not staff_pin_configured(configured_pin):
        return False
    if not pin_input:
        return False
    return str(pin_input) == str(configured_pin)


def require_role(user: User | None, *roles: str) -> User:
    if user is None:
        raise PermissionDenied("Please sign in to continue.")
    if roles and user.role not in roles:
        allowed = ", ".join(roles)
        raise PermissionDenied(f"This action requires one of: {allowed}.")
    return user


def require_owner(user: User | None) -> User:
    return require_role(user, "Owner")


def can(user: User | None, *roles: str) -> bool:
    return user is not None and (not roles or user.role in roles)


# ---------------------------------------------------------------------------
# Streamlit session helpers (imported lazily so core stays unit-testable)
# ---------------------------------------------------------------------------


def set_session_user(st: Any, user: User) -> None:
    st.session_state.authenticated = True
    st.session_state.user_id = user.user_id
    st.session_state.company_id = user.company_id
    st.session_state.user_name = user.username
    st.session_state.role = user.role
    st.session_state.user = {
        "user_id": user.user_id,
        "company_id": user.company_id,
        "username": user.username,
        "role": user.role,
    }


def clear_session(st: Any) -> None:
    for key in (
        "authenticated",
        "user_id",
        "company_id",
        "user_name",
        "role",
        "user",
        "nav_selection",
        "current_sale_items",
        "current_purchase_items",
    ):
        st.session_state.pop(key, None)


def session_user(st: Any) -> User | None:
    data = st.session_state.get("user")
    if isinstance(data, dict) and data.get("user_id") is not None:
        return User(
            user_id=int(data["user_id"]),
            company_id=int(data.get("company_id", 1)),
            username=str(data.get("username", "")),
            role=str(data.get("role", "Staff")),
        )
    if st.session_state.get("authenticated"):
        # Backwards-compatible fallback for sessions created before this refactor.
        return User(
            user_id=int(st.session_state.get("user_id", 0) or 0),
            company_id=int(st.session_state.get("company_id", 1) or 1),
            username=str(st.session_state.get("user_name", "")),
            role=str(st.session_state.get("role", "Staff")),
        )
    return None


def ensure_role(st: Any, *roles: str) -> User:
    return require_role(session_user(st), *roles)


def assert_company(user: User, company_id: int) -> None:
    if user.company_id != int(company_id):
        raise PermissionDenied("Cross-company access is not allowed.")
