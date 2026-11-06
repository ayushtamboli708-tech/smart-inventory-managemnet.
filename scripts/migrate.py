"""Apply SQL migrations in order and record them in schema_migrations."""

from __future__ import annotations

import sys
from pathlib import Path

import mysql.connector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import db  # noqa: E402


def statements(sql: str) -> list[str]:
    lines = [line for line in sql.splitlines() if not line.strip().startswith("--")]
    return [part.strip() for part in "\n".join(lines).split(";") if part.strip()]


def main() -> int:
    config = db.get_db_config()
    conn = mysql.connector.connect(**config, autocommit=False)
    results: list[tuple[str, str]] = []
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version VARCHAR(64) NOT NULL PRIMARY KEY,
                applied_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
            ) ENGINE=InnoDB
            """
        )
        conn.commit()
        cursor.execute("SELECT version FROM schema_migrations")
        applied = {row[0] for row in cursor.fetchall()}

        for path in sorted((ROOT / "migrations").glob("*.sql")):
            version = path.name
            if version in applied:
                results.append((version, "already applied"))
                continue
            for statement in statements(path.read_text(encoding="utf-8")):
                cursor.execute(statement)
            cursor.execute(
                "INSERT INTO schema_migrations (version) VALUES (%s)", (version,)
            )
            conn.commit()
            results.append((version, "applied"))
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    for version, state in results:
        print(f"{version}: {state}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
