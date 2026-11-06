"""Replace legacy plaintext passwords with bcrypt hashes.

Safe by default: reports how many rows need hashing without changing anything.
Pass ``--apply`` to hash them. Existing passwords keep working because a
plaintext row already contains the password itself.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import db  # noqa: E402
from core.auth import hash_legacy_passwords, is_legacy_plaintext  # noqa: E402


def pending_count(conn) -> int:
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT password FROM users")
        return sum(
            1
            for row in cursor.fetchall()
            if is_legacy_plaintext(str(row.get("password") or ""))
        )
    finally:
        cursor.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Hash legacy plaintext passwords in the users table."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually rewrite the rows. Without this flag it is a dry run.",
    )
    args = parser.parse_args()

    with db.connection() as conn:
        if conn is None:
            print("Database connection is not available.")
            return 2
        pending = pending_count(conn)
        print(f"plaintext passwords: {pending}")
        if not args.apply:
            if pending:
                print("Dry run only. Re-run with --apply to hash these rows.")
            return 0
        changed = hash_legacy_passwords(conn)

    print(f"hashed {changed} password(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
