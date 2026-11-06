"""Rebuild products.stock_qty from the inventory ledger."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import db  # noqa: E402
from core.stock import recompute_stock  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile materialized stock.")
    parser.add_argument("--company-id", type=int, default=1)
    parser.add_argument("--product-id", type=int, default=None)
    args = parser.parse_args()

    with db.connection() as conn:
        if conn is None:
            print("Database connection is not available.")
            return 2
        changed = recompute_stock(conn, args.company_id, args.product_id)
    print(f"Recomputed stock for {changed} product(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
