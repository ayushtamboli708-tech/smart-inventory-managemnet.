# Migrations

## Fresh install

1. Create an empty MySQL or TiDB database.
2. Put the connection details in `.streamlit/secrets.toml` (see the README).
3. Run:

```powershell
python scripts/migrate.py
python scripts/seed_demo.py   # optional demo catalog + 120 days of sales
```

`migrate.py` applies every `migrations/*.sql` file in filename order and records
it in `schema_migrations`, so it is safe to run again. It does not run the files
under `migrations/legacy/`; those are only for the manual legacy upgrade below.

## Legacy upgrade (pre-`company_id` database)

The original Stockwise schema had no `company_id`, no `products.stock_qty`, no
audit columns, no soft-delete columns, and no forecast run/metric tables. Sales,
purchase, and ledger history must be preserved, so this is a reviewed,
manual upgrade and not part of `migrate.py`.

The upgrader is a dry run by default:

```powershell
python scripts/upgrade_legacy.py                    # report only
python scripts/upgrade_legacy.py --apply --backup   # modify, with table copies
```

What `--apply` does, in order:

1. **Backs up** each legacy table to `<table>_backup_<utc-timestamp>`
   (`--backup`).
2. **Creates the missing tables** from
   `migrations/legacy/000_legacy_schema.sql`: `companies`, `product_vendors`,
   `forecast_runs`, `forecast_metrics`, `audit_logs`, and
   `schema_migrations`.
3. **Upgrades the existing tables** with
   `migrations/legacy/003_legacy_upgrade.sql`:
   - adds `company_id`, audit columns, `is_active`, and `deleted_at`;
   - backfills `products.stock_qty` from `inventory_ledger`;
   - backfills `line_total` on sale and purchase lines;
   - normalizes legacy `INITIAL` ledger rows to `ADJUSTMENT`;
   - derives `product_vendors` links from historical purchase lines;
   - moves legacy forecasts into a synthetic completed `forecast_runs` row and
     keeps the originals in `forecasts_legacy`;
   - adds the demo `cashier` staff account.
4. **Records** `001_initial.sql`, `002_audit_logs.sql`, and
   `003_legacy_upgrade.sql` in `schema_migrations`.

### TiDB note: signed legacy IDs

Legacy primary keys are signed `INT`. TiDB rejects widening a primary-key
column in place (`Unsupported modify column: this column has primary key flag`),
so the legacy upgrade keeps those columns signed. The tables created by
`000_legacy_schema.sql` therefore use `INT` foreign keys for products, vendors,
sales, and purchases. Fresh installs use `schema.sql`, where everything is
`BIGINT UNSIGNED`. This difference is intentional and only affects databases
that started from the pre-`company_id` schema.

### Testing the upgrade safely

`scripts/upgrade_legacy.py --database <copy>` can target a copy:

```powershell
python scripts/upgrade_legacy.py --database stockwise_copy --apply --backup
```

Always test on a copy first. DDL is not transactional on MySQL/TiDB, so restoring
the backup is the only rollback path.

### After the upgrade

1. The upgrade script hashes any remaining plaintext passwords with bcrypt. If
   you upgraded before this step existed, run
   `python scripts/hash_legacy_passwords.py --apply`. Login fails closed on a
   non-bcrypt row unless `STOCKWISE_ALLOW_PLAINTEXT=1` is set temporarily.
2. Change the demo `cashier` password (`Staff123!`) or deactivate the account.
3. Run `python scripts/reconcile_stock.py` if you want to re-verify the
   materialized balances against the ledger.
4. Run `python scripts/retrain_forecasts.py --company-id 1` to replace the
   imported legacy forecasts with scored SARIMA runs.

Legacy databases where every owner account should be re-created from scratch can
instead be exported and loaded into a fresh `schema.sql` database; the in-place
upgrade is for installations that must keep their history.
