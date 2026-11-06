-- Legacy upgrade step 0: create the tables that did not exist in the original
-- Stockwise schema.
--
-- This is the legacy twin of `schema.sql`. The original database uses signed
-- INT primary keys for users, vendors, products, sales, and purchases, and TiDB
-- cannot widen a primary-key column in place ("Unsupported modify column: this
-- column has primary key flag"). The new tables therefore reference those
-- columns with signed INT instead of the canonical BIGINT UNSIGNED.
--
-- Only the tables below are created here. Every other canonical table already
-- exists in a legacy database, so `schema.sql` would be a no-op for them.
-- Fresh installs keep using `schema.sql`; this file is applied only by
-- `scripts/upgrade_legacy.py`.

CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR(64) NOT NULL PRIMARY KEY,
    applied_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS companies (
    company_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(40) NOT NULL,
    name VARCHAR(160) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_companies_code (code)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS product_vendors (
    company_id BIGINT UNSIGNED NOT NULL,
    product_id INT NOT NULL,
    vendor_id INT NOT NULL,
    cost_price DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    is_primary TINYINT(1) NOT NULL DEFAULT 0,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (company_id, product_id, vendor_id),
    CONSTRAINT fk_pv_company FOREIGN KEY (company_id) REFERENCES companies (company_id),
    CONSTRAINT fk_pv_product FOREIGN KEY (product_id) REFERENCES products (product_id),
    CONSTRAINT fk_pv_vendor FOREIGN KEY (vendor_id) REFERENCES vendors (vendor_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS forecast_runs (
    run_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    company_id BIGINT UNSIGNED NOT NULL,
    started_at DATETIME(6) NOT NULL,
    finished_at DATETIME(6) NULL,
    status ENUM('RUNNING', 'COMPLETED', 'PARTIAL', 'FAILED') NOT NULL DEFAULT 'RUNNING',
    products_processed INT NOT NULL DEFAULT 0,
    products_failed INT NOT NULL DEFAULT 0,
    mape DECIMAL(10, 4) NULL,
    rmse DECIMAL(14, 4) NULL,
    trigger_source VARCHAR(40) NOT NULL DEFAULT 'manual',
    error_message TEXT NULL,
    created_by BIGINT UNSIGNED NULL,
    KEY idx_forecast_runs_company (company_id, started_at),
    CONSTRAINT fk_forecast_runs_company FOREIGN KEY (company_id) REFERENCES companies (company_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS forecast_metrics (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    company_id BIGINT UNSIGNED NOT NULL,
    run_id BIGINT UNSIGNED NOT NULL,
    product_id INT NOT NULL,
    train_rows INT NOT NULL DEFAULT 0,
    holdout_rows INT NOT NULL DEFAULT 0,
    mape DECIMAL(10, 4) NULL,
    rmse DECIMAL(14, 4) NULL,
    model_type VARCHAR(40) NOT NULL DEFAULT 'SARIMA',
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_forecast_metrics_run_product (company_id, run_id, product_id),
    CONSTRAINT fk_metrics_company FOREIGN KEY (company_id) REFERENCES companies (company_id),
    CONSTRAINT fk_metrics_run FOREIGN KEY (run_id) REFERENCES forecast_runs (run_id),
    CONSTRAINT fk_metrics_product FOREIGN KEY (product_id) REFERENCES products (product_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS audit_logs (
    audit_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    company_id BIGINT UNSIGNED NOT NULL,
    actor_id BIGINT UNSIGNED NULL,
    action VARCHAR(80) NOT NULL,
    entity VARCHAR(60) NOT NULL,
    entity_id VARCHAR(80) NULL,
    details JSON NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    KEY idx_audit_company_time (company_id, created_at),
    KEY idx_audit_action (company_id, action),
    CONSTRAINT fk_audit_company FOREIGN KEY (company_id) REFERENCES companies (company_id)
) ENGINE=InnoDB;
