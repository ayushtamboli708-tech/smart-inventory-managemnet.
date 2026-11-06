"""Precompute forecasts outside the Streamlit request thread."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import db  # noqa: E402
from forecast.forecasting_engine import run_full_analysis  # noqa: E402


def resolve_actor(conn, company_id: int, actor_id: int | None) -> int:
    if actor_id:
        return actor_id
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT user_id FROM users WHERE company_id = %s AND role = 'Owner' "
            "AND is_active = 1 ORDER BY user_id LIMIT 1",
            (company_id,),
        )
        row = cursor.fetchone()
        return int(row[0]) if row else 0
    finally:
        cursor.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Retrain Stockwise forecasts.")
    parser.add_argument("--company-id", type=int, default=1)
    parser.add_argument("--actor-id", type=int, default=None)
    parser.add_argument("--trigger", default="scheduled")
    args = parser.parse_args()

    with db.connection() as conn:
        if conn is None:
            print("Database connection is not available.")
            return 2
        actor_id = resolve_actor(conn, args.company_id, args.actor_id)
        result = run_full_analysis(
            conn, args.company_id, actor_id, trigger=args.trigger
        )
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
