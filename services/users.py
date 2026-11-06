"""User-account and audit helpers."""

from __future__ import annotations

import re
from typing import Any

from core.auth import User, hash_password, require_owner
from core.errors import ValidationError
from core.time import utc_now
from services.common import log_audit, require_connection

VALID_ROLES = {"Owner", "Staff"}
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]{3,64}$")


def list_users(conn: Any | None, company_id: int, role: str | None = None) -> list[dict]:
    conn = require_connection(conn)
    cursor = conn.cursor(dictionary=True)
    try:
        query = (
            "SELECT user_id, username, role, is_active, created_at "
            "FROM users WHERE company_id = %s AND is_active = 1"
        )
        params: list[Any] = [company_id]
        if role:
            query += " AND role = %s"
            params.append(role)
        query += " ORDER BY role, username"
        cursor.execute(query, tuple(params))
        return list(cursor.fetchall())
    finally:
        cursor.close()


def list_owners(conn: Any | None, company_id: int) -> list[dict]:
    return list_users(conn, company_id, "Owner")


def create_user(
    conn: Any,
    company_id: int,
    actor: User,
    *,
    username: str,
    password: str,
    role: str,
) -> int:
    require_owner(actor)
    username = username.strip()
    if role not in VALID_ROLES:
        raise ValidationError("Role must be Owner or Staff.")
    if not username:
        raise ValidationError("Username is required.")
    if not USERNAME_PATTERN.fullmatch(username):
        raise ValidationError(
            "Username must be 3-64 characters using letters, numbers, dot, "
            "underscore, or hyphen."
        )
    if len(password) < 8:
        raise ValidationError("Password must be at least 8 characters.")
    cursor = conn.cursor()
    try:
        now = utc_now()
        cursor.execute(
            """
            INSERT INTO users
                (company_id, username, password, role, is_active,
                 created_by, updated_by, created_at, updated_at)
            VALUES (%s, %s, %s, %s, 1, %s, %s, %s, %s)
            """,
            (
                company_id,
                username,
                hash_password(password),
                role,
                actor.user_id,
                actor.user_id,
                now,
                now,
            ),
        )
        user_id = int(cursor.lastrowid)
        log_audit(
            conn,
            company_id=company_id,
            actor_id=actor.user_id,
            action=f"user.create_{role.lower()}",
            entity="user",
            entity_id=user_id,
            details={"username": username},
        )
        return user_id
    finally:
        cursor.close()


def create_owner(
    conn: Any, company_id: int, actor: User, *, username: str, password: str
) -> int:
    return create_user(
        conn, company_id, actor, username=username, password=password, role="Owner"
    )


def create_staff(
    conn: Any, company_id: int, actor: User, *, username: str, password: str
) -> int:
    return create_user(
        conn, company_id, actor, username=username, password=password, role="Staff"
    )


def deactivate_user(conn: Any, company_id: int, actor: User, user_id: int) -> None:
    require_owner(actor)
    if int(user_id) == actor.user_id:
        raise ValidationError("You cannot deactivate your own account.")
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT user_id, role FROM users WHERE company_id = %s AND user_id = %s "
            "AND is_active = 1 FOR UPDATE",
            (company_id, int(user_id)),
        )
        target = cursor.fetchone()
        if not target:
            raise ValidationError("User not found.")
        if target["role"] == "Owner":
            cursor.execute(
                "SELECT user_id FROM users WHERE company_id = %s AND role = 'Owner' "
                "AND is_active = 1 FOR UPDATE",
                (company_id,),
            )
            owners = cursor.fetchall()
            if len(owners) <= 1:
                raise ValidationError("At least one active owner must remain.")
        cursor.execute(
            """
            UPDATE users
            SET is_active = 0, updated_at = %s, updated_by = %s
            WHERE company_id = %s AND user_id = %s
            """,
            (utc_now(), actor.user_id, company_id, int(user_id)),
        )
        log_audit(
            conn,
            company_id=company_id,
            actor_id=actor.user_id,
            action="user.deactivate",
            entity="user",
            entity_id=user_id,
        )
    finally:
        cursor.close()


# Backwards-compatible name.
def deactivate_owner(conn: Any, company_id: int, actor: User, user_id: int) -> None:
    deactivate_user(conn, company_id, actor, user_id)


def record_login(conn: Any, company_id: int, user: User) -> None:
    log_audit(
        conn,
        company_id=company_id,
        actor_id=user.user_id,
        action="auth.login",
        entity="user",
        entity_id=user.user_id,
        details={"role": user.role},
    )
