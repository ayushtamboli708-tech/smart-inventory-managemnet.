"""Database access layer.

One process-wide MySQL connection pool plus a per-script-run request scope.
Services accept the scoped connection, so a page render no longer opens a new
connection for every widget.
"""

from __future__ import annotations

import contextvars
import logging
import os
import threading
from contextlib import contextmanager
from typing import Any, Iterator

import mysql.connector
from mysql.connector import Error
from mysql.connector.constants import ClientFlag
from mysql.connector.pooling import MySQLConnectionPool

from core.errors import DatabaseUnavailable

logger = logging.getLogger("stockwise")

_request_conn: contextvars.ContextVar[Any | None] = contextvars.ContextVar(
    "stockwise_request_conn", default=None
)
_pool: MySQLConnectionPool | None = None
_pool_key: tuple[tuple[str, Any], ...] | None = None
_pool_lock = threading.Lock()


def _secrets_config() -> dict[str, Any]:
    try:
        import streamlit as st

        section = st.secrets["mysql"]
        config = {
            "host": str(section["host"]),
            "port": int(section.get("port", 3306)),
            "database": str(section["database"]),
            "user": str(section["user"]),
            "password": str(section["password"]),
        }
        for key in ("ssl_ca", "ssl_cert", "ssl_key", "ssl_disabled", "ssl_verify_cert"):
            if key in section:
                config[key] = section[key]
        return config
    except Exception:
        return {}


def get_db_config() -> dict[str, Any]:
    config = _secrets_config()
    if not config:
        config = {
            "host": os.getenv("STOCKWISE_DB_HOST", ""),
            "port": int(os.getenv("STOCKWISE_DB_PORT", "3306")),
            "database": os.getenv("STOCKWISE_DB_NAME", ""),
            "user": os.getenv("STOCKWISE_DB_USER", ""),
            "password": os.getenv("STOCKWISE_DB_PASSWORD", ""),
        }
    if not config.get("host") or not config.get("database"):
        raise DatabaseUnavailable(
            "Database is not configured. Add [mysql] to .streamlit/secrets.toml."
        )
    return config


def get_pool() -> MySQLConnectionPool:
    global _pool, _pool_key
    config = get_db_config()
    key = tuple(sorted((name, str(value)) for name, value in config.items()))
    with _pool_lock:
        if _pool is None or _pool_key != key:
            pool_size = max(1, int(os.getenv("STOCKWISE_POOL_SIZE", "5")))
            _pool = MySQLConnectionPool(
                pool_name="stockwise_pool",
                pool_size=pool_size,
                pool_reset_session=True,
                connection_timeout=10,
                client_flags=[ClientFlag.FOUND_ROWS],
                **config,
            )
            _pool_key = key
            logger.info("Created MySQL pool with %d connections", pool_size)
    return _pool


def reset_pool() -> None:
    """Test hook: force a new pool on the next access."""
    global _pool, _pool_key
    with _pool_lock:
        _pool = None
        _pool_key = None


def _new_connection() -> Any | None:
    try:
        return get_pool().get_connection()
    except Exception as exc:  # noqa: BLE001 - driver raises several types
        # Keep the driver detail in the server log; the browser only needs a
        # generic message, since connection errors often include host/user info.
        logger.error("Database connection failed: %s", exc)
        _report("Database connection failed. Check the connection settings.")
        return None


def _report(message: str) -> None:
    """Show a Streamlit error only when a script run is active."""
    try:
        import streamlit as st
        from streamlit.runtime import exists

        if exists():
            st.error(message)
    except Exception:
        pass


def get_db_connection() -> Any | None:
    """Return the request-scoped connection or a pooled one.

    Prefer :func:`transaction` / :func:`connection` in new code so ownership is
    explicit.
    """
    scoped = _request_conn.get()
    if scoped is not None:
        return scoped
    return _new_connection()


@contextmanager
def request_scope() -> Iterator[Any | None]:
    """Open one connection for the whole Streamlit script run."""
    scoped = _request_conn.get()
    if scoped is not None:
        yield scoped
        return

    conn = _new_connection()
    token = _request_conn.set(conn)
    try:
        yield conn
    finally:
        _request_conn.reset(token)
        if conn is not None:
            conn.close()


@contextmanager
def connection() -> Iterator[Any | None]:
    """Read-only connection context (does not commit or close scoped conn)."""
    scoped = _request_conn.get()
    if scoped is not None:
        yield scoped
        return

    conn = _new_connection()
    try:
        yield conn
    finally:
        if conn is not None:
            conn.close()


@contextmanager
def transaction() -> Iterator[Any | None]:
    """Transactional connection context.

    Commits on success, rolls back on any exception, and returns the connection
    to the request scope or pool afterwards.
    """
    scoped = _request_conn.get()
    conn = scoped if scoped is not None else _new_connection()
    if conn is None:
        yield None
        return

    try:
        yield conn
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Error:
            pass
        raise
    finally:
        if scoped is None:
            conn.close()


def schema_is_current() -> bool:
    """True when the database has the canonical schema.

    Legacy installations predate ``products.company_id``; detect that before the
    UI starts issuing tenant-scoped queries so the user sees upgrade instructions
    instead of a wall of SQL errors.
    """
    try:
        with connection() as conn:
            if conn is None:
                return False
            cursor = conn.cursor()
            try:
                cursor.execute("SHOW COLUMNS FROM products LIKE 'company_id'")
                return cursor.fetchone() is not None
            finally:
                cursor.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Schema check failed: %s", exc)
        return False


def healthcheck() -> bool:
    try:
        with connection() as conn:
            if conn is None:
                return False
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Database healthcheck failed: %s", exc)
        return False
