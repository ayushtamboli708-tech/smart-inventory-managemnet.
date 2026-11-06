"""Upgrade a pre-company_id Stockwise database to the current schema.

The command is a dry run by default. It only changes the database when
``--apply`` is passed. Take a full backup first; DDL cannot be rolled back.

Usage:
    python scripts/upgrade_legacy.py
    python scripts/upgrade_legacy.py --apply --backup
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import mysql.connector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import db  # noqa: E402
from core.auth import hash_legacy_passwords  # noqa: E402

LEGACY_TABLES = [
    "users",
    "vendors",
    "products",
    "sales",
    "sale_items",
    "purchases",
    "purchase_items",
    "inventory_ledger",
    "forecasts",
    "reorder_suggestions",
]
LEGACY_SCHEMA_FILE = ROOT / "migrations" / "legacy" / "000_legacy_schema.sql"
LEGACY_FILE = ROOT / "migrations" / "legacy" / "003_legacy_upgrade.sql"


def statements(sql: str) -> list[str]:
    lines = [line for line in sql.splitlines() if not line.strip().startswith("--")]
    return [part.strip() for part in "\n".join(lines).split(";") if part.strip()]


def table_exists(cursor, table: str) -> bool:
    cursor.execute("SHOW TABLES LIKE %s", (table,))
    return cursor.fetchone() is not None


def column_exists(cursor, table: str, column: str) -> bool:
    if not table_exists(cursor, table):
        return False
    cursor.execute(f"SHOW COLUMNS FROM `{table}` LIKE %s", (column,))
    return cursor.fetchone() is not None


def is_legacy(cursor) -> bool:
    return not column_exists(cursor, "products", "company_id")


def already_upgraded(cursor) -> bool:
    if not table_exists(cursor, "schema_migrations"):
        return False
    cursor.execute(
        "SELECT 1 FROM schema_migrations WHERE version = %s LIMIT 1",
        ("003_legacy_upgrade.sql",),
    )
    return cursor.fetchone() is not None


def make_backups(conn, cursor) -> list[str]:
    suffix = datetime.now(timezone.utc).strftime("_backup_%Y%m%d_%H%M%S")
    created: list[str] = []
    for table in LEGACY_TABLES:
        if not table_exists(cursor, table):
            continue
        backup = f"{table}{suffix}"
        cursor.execute(f"CREATE TABLE `{backup}` LIKE `{table}`")
        cursor.execute(f"INSERT INTO `{backup}` SELECT * FROM `{table}`")
        conn.commit()
        created.append(backup)
    return created


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Upgrade a legacy Stockwise database to the current schema."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually modify the database. Without this flag it is a dry run.",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Copy each legacy table to <table>_backup_<timestamp> first.",
    )
    parser.add_argument(
        "--database",
        default=None,
        help="Override the configured database name (useful for a tested copy).",
    )
    args = parser.parse_args()

    config = db.get_db_config()
    if args.database:
        config["database"] = args.database
    conn = mysql.connector.connect(**config, autocommit=False)
    cursor = conn.cursor()
    try:
        if not table_exists(cursor, "products"):
            print("No products table found. This does not look like a Stockwise DB.")
            return 2

        legacy = is_legacy(cursor)
        upgraded = already_upgraded(cursor)
        print(f"database: {config.get('database')}")
        print(f"legacy schema: {legacy}")
        print(f"003 already recorded: {upgraded}")

        if not legacy:
            print("Nothing to do: products.company_id already exists.")
            return 0
        if upgraded:
            print("Migration 003 is recorded but the schema still looks legacy.")
            print("Inspect the database before running anything else.")
            return 2
        if not table_exists(cursor, "forecasts"):
            print("The legacy forecasts table is missing; cannot preserve history.")
            return 2
        if table_exists(cursor, "forecasts_legacy"):
            print("forecasts_legacy already exists. Refusing to overwrite it.")
            return 2

        legacy_schema_statements = statements(
            LEGACY_SCHEMA_FILE.read_text(encoding="utf-8")
        )
        upgrade_statements = statements(LEGACY_FILE.read_text(encoding="utf-8"))
        print(f"legacy schema statements: {len(legacy_schema_statements)}")
        print(f"upgrade statements: {len(upgrade_statements)}")

        if not args.apply:
            print("\nDry run only. Re-run with --apply to modify the database.")
            print("Recommended: take a mysqldump backup or pass --backup.")
            return 0

        if args.backup:
            created = make_backups(conn, cursor)
            print("backups:", ", ".join(created) if created else "none")
        else:
            print("WARNING: running without --backup. DDL cannot be rolled back.")

        print("applying migrations/legacy/000_legacy_schema.sql ...")
        for index, statement in enumerate(legacy_schema_statements, start=1):
            cursor.execute(statement)
            if index % 5 == 0:
                print(f"  {index}/{len(legacy_schema_statements)}")
        conn.commit()

        print("applying migrations/legacy/003_legacy_upgrade.sql ...")
        for index, statement in enumerate(upgrade_statements, start=1):
            cursor.execute(statement)
            if index % 5 == 0:
                print(f"  {index}/{len(upgrade_statements)}")
        conn.commit()

        for version in (
            "001_initial.sql",
            "002_audit_logs.sql",
            "003_legacy_upgrade.sql",
        ):
            cursor.execute(
                "INSERT INTO schema_migrations (version) VALUES (%s) "
                "ON DUPLICATE KEY UPDATE version = VALUES(version)",
                (version,),
            )
        conn.commit()
        hashed = hash_legacy_passwords(conn)
        print(f"upgrade complete; legacy forecasts preserved as forecasts_legacy")
        print(f"bcrypt password rows updated: {hashed}")
        return 0
    except Exception as exc:  # noqa: BLE001 - surface the failing statement
        try:
            conn.rollback()
        except Exception:
            pass
        print(f"UPGRADE FAILED: {type(exc).__name__}: {exc}")
        print("Restore from your backup before retrying.")
        return 1
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
