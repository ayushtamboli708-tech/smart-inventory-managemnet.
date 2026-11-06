-- Legacy upgrade: bring the pre-company_id Stockwise schema up to the current
-- canonical schema without deleting sales, purchase, or ledger history.
--
-- Run through `python scripts/upgrade_legacy.py --apply`, never directly on a
-- database that has not been backed up. The script first applies
-- `migrations/legacy/000_legacy_schema.sql`, which creates the tables that did
-- not exist in the original schema (with INT foreign keys that match the legacy
-- signed primary keys), then runs this file.

INSERT INTO companies (company_id, code, name)
VALUES (1, 'demo', 'Stockwise')
ON DUPLICATE KEY UPDATE name = VALUES(name);

-- ---------------------------------------------------------------------------
-- users: add tenancy, active flag, audit columns, and a demo staff account.
-- Existing plaintext owner passwords are upgraded to bcrypt on first login.
-- ---------------------------------------------------------------------------
ALTER TABLE users
    ADD COLUMN company_id BIGINT UNSIGNED NOT NULL DEFAULT 1,
    ADD COLUMN is_active TINYINT(1) NOT NULL DEFAULT 1,
    ADD COLUMN created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    ADD COLUMN updated_at DATETIME(6) NULL,
    ADD COLUMN created_by BIGINT UNSIGNED NULL,
    ADD COLUMN updated_by BIGINT UNSIGNED NULL,
    MODIFY COLUMN role ENUM('Owner', 'Staff') NOT NULL DEFAULT 'Staff';

ALTER TABLE users
    ADD UNIQUE KEY uq_users_company_username (company_id, username),
    ADD KEY idx_users_company_role (company_id, role, is_active);

INSERT INTO users
    (company_id, username, password, role, is_active, created_by, updated_by,
     created_at, updated_at)
VALUES
    (1, 'cashier',
     '$2b$12$BVsw/0peyDo1esdq/ibliOxbhaLlQlGtoULR/Xzb/xSurwDCIQtDW',
     'Staff', 1, 1, 1, UTC_TIMESTAMP(6), UTC_TIMESTAMP(6))
ON DUPLICATE KEY UPDATE
    role = 'Staff', is_active = 1;

-- ---------------------------------------------------------------------------
-- vendors
-- ---------------------------------------------------------------------------
ALTER TABLE vendors
    ADD COLUMN company_id BIGINT UNSIGNED NOT NULL DEFAULT 1,
    ADD COLUMN is_active TINYINT(1) NOT NULL DEFAULT 1,
    ADD COLUMN deleted_at DATETIME(6) NULL,
    ADD COLUMN created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    ADD COLUMN updated_at DATETIME(6) NULL,
    ADD COLUMN created_by BIGINT UNSIGNED NULL,
    ADD COLUMN updated_by BIGINT UNSIGNED NULL;

ALTER TABLE vendors
    ADD KEY idx_vendors_company (company_id, is_active, deleted_at);

-- ---------------------------------------------------------------------------
-- products: materialized balance is backfilled from the existing ledger.
-- ---------------------------------------------------------------------------
ALTER TABLE products
    ADD COLUMN company_id BIGINT UNSIGNED NOT NULL DEFAULT 1,
    ADD COLUMN stock_qty DECIMAL(14, 2) NOT NULL DEFAULT 0.00,
    ADD COLUMN deleted_at DATETIME(6) NULL,
    ADD COLUMN created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    ADD COLUMN updated_at DATETIME(6) NULL,
    ADD COLUMN created_by BIGINT UNSIGNED NULL,
    ADD COLUMN updated_by BIGINT UNSIGNED NULL;

ALTER TABLE products
    ADD UNIQUE KEY uq_products_company_sku (company_id, sku),
    ADD KEY idx_products_company_active (company_id, is_active, deleted_at),
    ADD KEY idx_products_company_category (company_id, category);

UPDATE products p
LEFT JOIN (
    SELECT product_id, SUM(quantity_change) AS qty
    FROM inventory_ledger
    GROUP BY product_id
) ledger ON ledger.product_id = p.product_id
-- The legacy ledger is incomplete for some products (missing opening rows), so
-- its sum can be negative. Real stock cannot be negative: clamp the materialized
-- balance at zero and leave the ledger rows untouched as the audit trail.
SET p.stock_qty = GREATEST(COALESCE(ledger.qty, 0.00), 0.00);

-- ---------------------------------------------------------------------------
-- sales / sale_items
-- ---------------------------------------------------------------------------
ALTER TABLE sales
    ADD COLUMN company_id BIGINT UNSIGNED NOT NULL DEFAULT 1,
    ADD COLUMN status ENUM('COMPLETED', 'REFUNDED') NOT NULL DEFAULT 'COMPLETED',
    ADD COLUMN created_by BIGINT UNSIGNED NULL,
    ADD COLUMN created_at DATETIME(6) NULL,
    ADD COLUMN updated_at DATETIME(6) NULL,
    ADD COLUMN updated_by BIGINT UNSIGNED NULL;

ALTER TABLE sales
    ADD KEY idx_sales_company_date (company_id, sale_date),
    ADD KEY idx_sales_company_status (company_id, status);

UPDATE sales SET created_at = sale_date WHERE created_at IS NULL;

ALTER TABLE sales
    MODIFY COLUMN created_at DATETIME(6) NOT NULL
        DEFAULT CURRENT_TIMESTAMP(6);

ALTER TABLE sale_items
    ADD COLUMN company_id BIGINT UNSIGNED NOT NULL DEFAULT 1,
    ADD COLUMN line_total DECIMAL(14, 2) NOT NULL DEFAULT 0.00;

ALTER TABLE sale_items
    ADD KEY idx_sale_items_sale (company_id, sale_id),
    ADD KEY idx_sale_items_product (company_id, product_id);

UPDATE sale_items
SET line_total = quantity * unit_price;

-- ---------------------------------------------------------------------------
-- purchases / purchase_items
-- ---------------------------------------------------------------------------
ALTER TABLE purchases
    ADD COLUMN company_id BIGINT UNSIGNED NOT NULL DEFAULT 1,
    ADD COLUMN created_by BIGINT UNSIGNED NULL,
    ADD COLUMN created_at DATETIME(6) NULL,
    ADD COLUMN updated_at DATETIME(6) NULL,
    ADD COLUMN updated_by BIGINT UNSIGNED NULL,
    MODIFY COLUMN status ENUM('PENDING', 'RECEIVED', 'CANCELLED')
        NOT NULL DEFAULT 'PENDING';

ALTER TABLE purchases
    ADD KEY idx_purchases_company_date (company_id, purchase_date),
    ADD KEY idx_purchases_company_status (company_id, status);

UPDATE purchases SET created_at = purchase_date WHERE created_at IS NULL;

ALTER TABLE purchases
    MODIFY COLUMN created_at DATETIME(6) NOT NULL
        DEFAULT CURRENT_TIMESTAMP(6);

ALTER TABLE purchase_items
    ADD COLUMN company_id BIGINT UNSIGNED NOT NULL DEFAULT 1,
    ADD COLUMN line_total DECIMAL(14, 2) NOT NULL DEFAULT 0.00;

ALTER TABLE purchase_items
    ADD KEY idx_purchase_items_purchase (company_id, purchase_id),
    ADD KEY idx_purchase_items_product (company_id, product_id);

UPDATE purchase_items
SET line_total = quantity * cost_price;

-- ---------------------------------------------------------------------------
-- inventory_ledger: add reference/actor metadata and normalize INITIAL.
-- ---------------------------------------------------------------------------
ALTER TABLE inventory_ledger
    ADD COLUMN company_id BIGINT UNSIGNED NOT NULL DEFAULT 1,
    ADD COLUMN reference_type VARCHAR(30) NOT NULL DEFAULT 'MANUAL',
    ADD COLUMN reason VARCHAR(255) NULL,
    ADD COLUMN occurred_at DATETIME(6) NULL,
    ADD COLUMN created_by BIGINT UNSIGNED NULL;

ALTER TABLE inventory_ledger
    ADD KEY idx_ledger_company_product_time
        (company_id, product_id, occurred_at),
    ADD KEY idx_ledger_company_reference
        (company_id, reference_type, reference_id);

UPDATE inventory_ledger
SET reference_type = CASE transaction_type
    WHEN 'SALE' THEN 'SALE'
    WHEN 'PURCHASE' THEN 'PURCHASE'
    WHEN 'INITIAL' THEN 'OPENING'
    ELSE 'MANUAL'
END;

UPDATE inventory_ledger
SET occurred_at = COALESCE(transaction_date, UTC_TIMESTAMP(6))
WHERE occurred_at IS NULL;

ALTER TABLE inventory_ledger
    MODIFY COLUMN transaction_type
        ENUM('SALE', 'REFUND', 'PURCHASE', 'ADJUSTMENT',
             'PURCHASE_REVERSAL', 'INITIAL') NOT NULL;

UPDATE inventory_ledger
SET transaction_type = 'ADJUSTMENT'
WHERE transaction_type = 'INITIAL';

ALTER TABLE inventory_ledger
    MODIFY COLUMN transaction_type
        ENUM('SALE', 'REFUND', 'PURCHASE', 'ADJUSTMENT',
             'PURCHASE_REVERSAL') NOT NULL,
    MODIFY COLUMN occurred_at DATETIME(6) NOT NULL;

-- ---------------------------------------------------------------------------
-- product_vendors: derive links from historical purchase lines.
-- ---------------------------------------------------------------------------
INSERT INTO product_vendors
    (company_id, product_id, vendor_id, cost_price, is_primary, created_at)
SELECT 1, pi.product_id, p.vendor_id, MAX(pi.cost_price), 0, UTC_TIMESTAMP(6)
FROM purchase_items pi
JOIN purchases p ON p.purchase_id = pi.purchase_id
GROUP BY pi.product_id, p.vendor_id
ON DUPLICATE KEY UPDATE cost_price = VALUES(cost_price);

UPDATE product_vendors pv
JOIN (
    SELECT product_id, MIN(cost_price) AS cost_price
    FROM product_vendors
    WHERE company_id = 1
    GROUP BY product_id
) cheapest
  ON cheapest.product_id = pv.product_id
 AND cheapest.cost_price = pv.cost_price
SET pv.is_primary = 1
WHERE pv.company_id = 1;

-- ---------------------------------------------------------------------------
-- forecasts: keep the legacy rows in a backup table and load them into a
-- synthetic completed run so the new dashboard can display them.
-- ---------------------------------------------------------------------------
RENAME TABLE forecasts TO forecasts_legacy;

CREATE TABLE forecasts (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    company_id BIGINT UNSIGNED NOT NULL,
    product_id INT NOT NULL,
    run_id BIGINT UNSIGNED NOT NULL,
    forecast_date DATE NOT NULL,
    avg_daily_demand DECIMAL(14, 4) NOT NULL DEFAULT 0.0000,
    predicted_demand DECIMAL(14, 4) NOT NULL DEFAULT 0.0000,
    lower_bound DECIMAL(14, 4) NULL,
    upper_bound DECIMAL(14, 4) NULL,
    model_type VARCHAR(40) NOT NULL DEFAULT 'SARIMA',
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_forecasts_run_product_day
        (company_id, run_id, product_id, forecast_date),
    KEY idx_forecasts_company_day (company_id, forecast_date),
    CONSTRAINT fk_forecasts_company FOREIGN KEY (company_id)
        REFERENCES companies (company_id),
    CONSTRAINT fk_forecasts_product FOREIGN KEY (product_id)
        REFERENCES products (product_id),
    CONSTRAINT fk_forecasts_run FOREIGN KEY (run_id)
        REFERENCES forecast_runs (run_id)
) ENGINE=InnoDB;

INSERT INTO forecast_runs
    (company_id, started_at, finished_at, status, products_processed,
     trigger_source)
VALUES
    (1, UTC_TIMESTAMP(6), UTC_TIMESTAMP(6), 'COMPLETED',
     (SELECT COUNT(DISTINCT product_id) FROM forecasts_legacy), 'legacy');

SET @legacy_run_id = LAST_INSERT_ID();

INSERT IGNORE INTO forecasts
    (company_id, product_id, run_id, forecast_date, avg_daily_demand,
     predicted_demand, lower_bound, upper_bound, model_type, created_at)
SELECT 1, product_id, @legacy_run_id, forecast_date, avg_daily_demand,
       predicted_demand, NULL, NULL, model_type, UTC_TIMESTAMP(6)
FROM forecasts_legacy;

-- ---------------------------------------------------------------------------
-- reorder_suggestions
-- ---------------------------------------------------------------------------
ALTER TABLE reorder_suggestions
    CHANGE COLUMN suggestion_id id INT NOT NULL AUTO_INCREMENT,
    ADD COLUMN company_id BIGINT UNSIGNED NOT NULL DEFAULT 1,
    ADD COLUMN vendor_id INT NULL,
    ADD COLUMN status_updated_at DATETIME(6) NULL,
    ADD COLUMN status_updated_by BIGINT UNSIGNED NULL,
    ADD COLUMN forecast_run_id BIGINT UNSIGNED NULL,
    MODIFY COLUMN status ENUM('PENDING', 'ORDERED', 'DISMISSED', 'SUPERSEDED')
        NOT NULL DEFAULT 'PENDING';

ALTER TABLE reorder_suggestions
    ADD KEY idx_reorder_company_status (company_id, status, product_id);

UPDATE reorder_suggestions rs
LEFT JOIN product_vendors pv
  ON pv.product_id = rs.product_id
 AND pv.company_id = 1
 AND pv.is_primary = 1
SET rs.vendor_id = pv.vendor_id
WHERE rs.vendor_id IS NULL;
