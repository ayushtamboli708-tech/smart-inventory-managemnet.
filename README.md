# Stockwise

Predictive inventory, POS, and procurement for small and medium retailers.
Stockwise combines day-to-day checkout and purchasing with SARIMA demand
forecasting, reorder suggestions, role-based access, and a full inventory
ledger.

## What changed in this refactor

The application was split from one large Streamlit file into small layers:

```text
.
├── app.py                     # Shell: auth gate, sidebar, routing only
├── db.py                      # MySQL pool + request-scoped connection
├── core/
│   ├── auth.py                # Password hashing, roles, session helpers
│   ├── cart.py                # One validated purchase-cart contract
│   ├── config.py              # Thresholds, windows, timezone, page size
│   ├── errors.py              # Domain errors mapped to UI messages
│   ├── pagination.py          # Shared pagination/clamping
│   ├── stock.py               # Row locks, ledger writes, balance updates
│   └── time.py                # UTC storage and local-time display
├── services/
│   ├── catalog.py             # Product CRUD, CSV import, stock adjustment
│   ├── dashboard.py           # Dashboard aggregates
│   ├── purchases.py           # Multi-vendor POs, receive, cancel
│   ├── sales.py               # Transactional checkout, refunds, reports
│   ├── users.py               # Named owner/staff accounts + audit
│   └── vendors.py             # Vendor CRUD and product-vendor links
├── forecast/
│   ├── forecasting_engine.py  # SARIMA training and reorder logic
│   └── metrics.py             # MAPE / RMSE (pure functions)
├── ui/
│   ├── dashboard_page.py      # Extracted dashboard + forecast dialog
│   ├── product_page.py        # Catalog and stock adjustments
│   ├── sales_page.py          # Checkout, refunds, CSV export
│   ├── purchase_page.py       # Cart, vendor management, PO actions
│   ├── alert_page.py          # Low stock / overstock / reorders
│   ├── login_page.py          # Named owner and staff sign-in
│   ├── dialogs.py             # Shared cart and vendor dialogs
│   ├── components.py          # Paginated dataframes, KPIs, errors
│   └── styles.py              # Single source of CSS
├── migrations/                # Ordered SQL migrations + upgrade notes
│   ├── 001_initial.sql        # Canonical tables (fresh installs)
│   ├── 002_audit_logs.sql     # Audit trail
│   └── legacy/                # One-time in-place upgrade for old databases
├── scripts/
│   ├── migrate.py             # Apply migrations, record versions
│   ├── seed_demo.py           # Demo catalog + 120 days of sales
│   ├── retrain_forecasts.py   # Precompute forecasts outside the UI
│   └── reconcile_stock.py     # Rebuild stock_qty from the ledger
├── tests/                     # pytest suite (47 tests)
├── schema.sql                 # Canonical fresh-install schema
├── seed.sql                   # Demo company, users, vendors, products
├── requirements.txt           # Pinned runtime dependencies
├── requirements-dev.txt       # Pinned test dependencies
└── .github/workflows/ci.yml   # Compile + test on every push/PR
```

## Key design decisions

### Authentication fails closed

Staff no longer share a PIN. Both Owner and Staff sign in with named accounts
stored in `users`; passwords must be bcrypt hashes. Rows that are still plaintext
are refused at login unless an operator sets `STOCKWISE_ALLOW_PLAINTEXT=1` during
migration; the upgrade script hashes them in place. The legacy PIN helper remains
fail-closed: if no PIN is configured, access is denied. Every login and write is
recorded in `audit_logs`.

### One cart contract

Manual purchases, dashboard forecasts, and alert suggestions all build the same
`CartItem` through `core.cart.make_cart_item`. A missing vendor is rejected at
construction time instead of crashing later with a `KeyError`. Adding an item
sets `open_purchase_dialog`, switches to the Purchases page, and opens the
purchase dialog.

### Stock is checked inside the transaction

Checkout aggregates quantities per product, locks the product rows with
`SELECT ... FOR UPDATE`, validates availability, inserts the sale, writes the
ledger, and updates the materialized `products.stock_qty`. The balance update
also has a `stock_qty + delta >= 0` guard, so stock cannot go negative even if a
caller forgets validation. Purchases, refunds, and adjustments use the same
`apply_ledger_entry` helper.

### Ledger plus materialized balance

`inventory_ledger` is the audit trail; `products.stock_qty` is the fast current
balance. `scripts/reconcile_stock.py` rebuilds balances from the ledger.

### Soft deletes

Products and vendors are archived with `deleted_at`, never hard-deleted. Sales,
sale items, purchase orders, and ledger rows always keep their history.

### Multi-tenancy

Every business table carries `company_id`. The workspace code selects the
company at login (`demo` in the seed), and service queries filter by it.

### UTC storage, local display

All datetimes are stored as naive UTC. `core.time` converts to the configured
shop timezone (`Asia/Kolkata` by default) only at the presentation edge.

## Setup

Requirements: Python 3.11+ (tested on 3.14) and MySQL 8 or TiDB Cloud.

1. Create a virtual environment and install pinned dependencies:

   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

2. Create `.streamlit/secrets.toml` (git-ignored):

   ```toml
   [mysql]
   host = "your-database-host"
   port = 3306
   database = "your_database"
   user = "your_user"
   password = "your_password"
   ```

   Optional environment overrides: `STOCKWISE_DB_HOST`, `STOCKWISE_DB_PORT`,
   `STOCKWISE_DB_NAME`, `STOCKWISE_DB_USER`, `STOCKWISE_DB_PASSWORD`,
   `STOCKWISE_POOL_SIZE`.

3. Create the schema and optional demo data:

   ```powershell
   python scripts/migrate.py
   python scripts/seed_demo.py
   ```

4. Start the app:

   ```powershell
   streamlit run app.py
   ```

Demo accounts after `seed_demo.py`:

| Role | Username | Password | Workspace |
| --- | --- | --- | --- |
| Owner | `owner` | `ChangeMe123!` | `demo` |
| Staff | `cashier` | `Staff123!` | `demo` |

Change these passwords before using the app with real data.

## Forecasting

For each active product the engine:

1. Loads up to **90 days** of daily completed-sales history, filling missing
   days with zero.
2. Holds out the last **14 days** and fits SARIMA
   `(1,1,1)(1,1,0,7)` with weekend and Indian-holiday exogenous variables.
3. Scores that holdout with **MAPE and RMSE**.
4. Refits on the full window and predicts a **28-day** horizon with confidence
   bounds.
5. Stores every prediction in `forecasts` and the run/product metrics in
   `forecast_runs` and `forecast_metrics`.
6. Generates reorder suggestions from predicted week-1 demand, a 20% safety
   stock, the product reorder threshold, and available stock.

Products with too little history use a mean-demand fallback and record
`model_type = MEAN_FALLBACK` with no MAPE/RMSE. The UI shows the latest run's
metrics; retraining is Owner-only. For production, run the precompute job on a
schedule instead of in the web thread:

```powershell
python scripts/retrain_forecasts.py --company-id 1 --trigger scheduled
```

**Answer to "how many months/rows and what error?":** the code trains on at most
90 daily rows (about 3 months), evaluates on 14 held-out daily rows, then
produces 28 daily predictions. Actual MAPE/RMSE are data-dependent; they are
computed per run and stored in `forecast_runs` and `forecast_metrics`, not
hard-coded.

Measured on the connected sample database (fixed 90-day window
`2026-01-12..2026-04-12`, 11 products with history):

| Items | Value |
| --- | --- |
| Rows per product | 77 train + 14 holdout daily rows |
| Mean holdout MAPE | **89.03%** |
| Mean holdout RMSE | **3.91 units** |

MAPE is high because this sample has intermittent demand (many zero-sale days).
These are sample-data measurements, not a production accuracy claim. On the
current 90-day window only two products have a sale, so the engine correctly
falls back to `MEAN_FALLBACK` and reports no MAPE/RMSE for them.

## Testing

The suite uses **pytest** (not `unittest`) and currently contains **47 tests**
across 7 files covering auth/role policy, cart validation, stock guards,
pagination, timezone bounds, MAPE/RMSE, and forecast/reorder logic. Most tests
run without a database.

```powershell
pip install -r requirements.txt
python -m pytest -q
```

CI runs `compileall` and the same test suite on every push and pull request.

## Scale

The repository ships a demo seed of:

- 1 company (`demo`)
- 2 users (1 Owner, 1 Staff)
- 2 vendors
- 5 products
- 120 days of generated sales

The connected sample database (the original Stockwise data) contains:

| Table | Rows |
| --- | --- |
| Products | 13 (all active) |
| Vendors | 2 |
| Users | 3 (all Owner) |
| Sales | 289 across 92 distinct days |
| Purchase orders | 24 |
| Forecast rows | 308 |
| Reorder suggestions | 7 |

With the new thresholds, the upgraded copy flags **9 of 13 products** for
reorder (8 out of stock, 1 at or below its reorder point) and 1 as overstock, so
the alert page stays short instead of listing the whole catalog.

These are demo/sample fixtures, not production limits. No production product,
supplier, user, or alert-volume numbers are claimed. The schema, server-side
pagination, connection pooling, and materialized stock balances are designed to
scale beyond the fixture, but real capacity depends on the database plan and
deployment.

## Migrations and legacy databases

`schema.sql` is the canonical **fresh-install** schema. Legacy databases did not
have `company_id`, `products.stock_qty`, audit columns, or forecast tables, so
there is no automatic destructive upgrade. A reviewed in-place upgrader is
provided and is a dry run by default:

```powershell
python scripts/upgrade_legacy.py                    # report only
python scripts/upgrade_legacy.py --apply --backup   # backs up tables, then migrates
```

It preserves sales, purchase, and ledger history, moves legacy forecasts to
`forecasts_legacy`, and backfills materialized stock balances. Take a full
backup first; DDL cannot be rolled back. See
[`migrations/README.md`](migrations/README.md) for the full sequence, the TiDB
signed-`INT` note, and how to test against a database copy.

## Limitations

- `.streamlit/secrets.toml` is required; there is no local SQLite fallback.
- The workspace code must match a row in `companies`.
- Reporting exports CSV only; PDF invoices are not implemented.
- The UI can retrain forecasts synchronously, but scheduled precomputation via
  `scripts/retrain_forecasts.py` is the recommended production path.
- Legacy data requires a reviewed migration; it is not applied automatically.
- Login throttling is per browser session. For internet-facing deployments put
  the app behind a reverse proxy or identity-aware proxy that rate-limits and
  authenticates requests.
- Keep `.streamlit/secrets.toml` out of version control (it is git-ignored) and
  use a least-privilege database account rather than a root account.
- `requirment.txt.txt` is an obsolete duplicate of `requirements.txt` and can be
  removed.
