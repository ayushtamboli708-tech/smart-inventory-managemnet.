-- Migration 001: core Stockwise schema.

-- Stockwise canonical schema (MySQL 8 / TiDB Cloud compatible).
-- Fresh installs: run `python scripts/migrate.py`.
-- Existing installations: back up first, then review migrations/README.md.

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

CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    company_id BIGINT UNSIGNED NOT NULL,
    username VARCHAR(80) NOT NULL,
    password VARCHAR(255) NOT NULL,
    role ENUM('Owner', 'Staff') NOT NULL DEFAULT 'Staff',
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NULL,
    created_by BIGINT UNSIGNED NULL,
    updated_by BIGINT UNSIGNED NULL,
    UNIQUE KEY uq_users_company_username (company_id, username),
    KEY idx_users_company_role (company_id, role, is_active),
    CONSTRAINT fk_users_company FOREIGN KEY (company_id) REFERENCES companies (company_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS vendors (
    vendor_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    company_id BIGINT UNSIGNED NOT NULL,
    name VARCHAR(160) NOT NULL,
    contact VARCHAR(160) NOT NULL DEFAULT '',
    address VARCHAR(255) NOT NULL DEFAULT '',
    lead_time_days INT NOT NULL DEFAULT 0,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    deleted_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NULL,
    created_by BIGINT UNSIGNED NULL,
    updated_by BIGINT UNSIGNED NULL,
    KEY idx_vendors_company (company_id, is_active, deleted_at),
    CONSTRAINT fk_vendors_company FOREIGN KEY (company_id) REFERENCES companies (company_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS products (
    product_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    company_id BIGINT UNSIGNED NOT NULL,
    sku VARCHAR(64) NOT NULL,
    name VARCHAR(200) NOT NULL,
    category VARCHAR(80) NOT NULL DEFAULT 'Other',
    unit VARCHAR(32) NOT NULL DEFAULT 'Pc',
    selling_price DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    reorder_threshold INT NOT NULL DEFAULT 10,
    stock_qty DECIMAL(14, 2) NOT NULL DEFAULT 0.00,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    deleted_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NULL,
    created_by BIGINT UNSIGNED NULL,
    updated_by BIGINT UNSIGNED NULL,
    UNIQUE KEY uq_products_company_sku (company_id, sku),
    KEY idx_products_company_active (company_id, is_active, deleted_at),
    KEY idx_products_company_category (company_id, category),
    CONSTRAINT fk_products_company FOREIGN KEY (company_id) REFERENCES companies (company_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS product_vendors (
    company_id BIGINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    vendor_id BIGINT UNSIGNED NOT NULL,
    cost_price DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    is_primary TINYINT(1) NOT NULL DEFAULT 0,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (company_id, product_id, vendor_id),
    CONSTRAINT fk_pv_company FOREIGN KEY (company_id) REFERENCES companies (company_id),
    CONSTRAINT fk_pv_product FOREIGN KEY (product_id) REFERENCES products (product_id),
    CONSTRAINT fk_pv_vendor FOREIGN KEY (vendor_id) REFERENCES vendors (vendor_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS sales (
    sale_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    company_id BIGINT UNSIGNED NOT NULL,
    sale_date DATETIME(6) NOT NULL,
    total_amount DECIMAL(14, 2) NOT NULL DEFAULT 0.00,
    status ENUM('COMPLETED', 'REFUNDED') NOT NULL DEFAULT 'COMPLETED',
    created_by BIGINT UNSIGNED NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NULL,
    updated_by BIGINT UNSIGNED NULL,
    KEY idx_sales_company_date (company_id, sale_date),
    KEY idx_sales_company_status (company_id, status),
    CONSTRAINT fk_sales_company FOREIGN KEY (company_id) REFERENCES companies (company_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS sale_items (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    company_id BIGINT UNSIGNED NOT NULL,
    sale_id BIGINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    quantity INT NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    line_total DECIMAL(14, 2) NOT NULL,
    KEY idx_sale_items_sale (company_id, sale_id),
    KEY idx_sale_items_product (company_id, product_id),
    CONSTRAINT fk_sale_items_sale FOREIGN KEY (sale_id) REFERENCES sales (sale_id),
    CONSTRAINT fk_sale_items_product FOREIGN KEY (product_id) REFERENCES products (product_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS purchases (
    purchase_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    company_id BIGINT UNSIGNED NOT NULL,
    vendor_id BIGINT UNSIGNED NOT NULL,
    purchase_date DATETIME(6) NOT NULL,
    total_amount DECIMAL(14, 2) NOT NULL DEFAULT 0.00,
    status ENUM('PENDING', 'RECEIVED', 'CANCELLED') NOT NULL DEFAULT 'PENDING',
    created_by BIGINT UNSIGNED NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NULL,
    updated_by BIGINT UNSIGNED NULL,
    KEY idx_purchases_company_date (company_id, purchase_date),
    KEY idx_purchases_company_status (company_id, status),
    CONSTRAINT fk_purchases_company FOREIGN KEY (company_id) REFERENCES companies (company_id),
    CONSTRAINT fk_purchases_vendor FOREIGN KEY (vendor_id) REFERENCES vendors (vendor_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS purchase_items (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    company_id BIGINT UNSIGNED NOT NULL,
    purchase_id BIGINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    quantity INT NOT NULL,
    cost_price DECIMAL(12, 2) NOT NULL,
    line_total DECIMAL(14, 2) NOT NULL,
    KEY idx_purchase_items_purchase (company_id, purchase_id),
    KEY idx_purchase_items_product (company_id, product_id),
    CONSTRAINT fk_purchase_items_purchase FOREIGN KEY (purchase_id) REFERENCES purchases (purchase_id),
    CONSTRAINT fk_purchase_items_product FOREIGN KEY (product_id) REFERENCES products (product_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS inventory_ledger (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    company_id BIGINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    transaction_type ENUM('SALE', 'REFUND', 'PURCHASE', 'ADJUSTMENT', 'PURCHASE_REVERSAL') NOT NULL,
    reference_type VARCHAR(30) NOT NULL DEFAULT 'MANUAL',
    reference_id BIGINT UNSIGNED NULL,
    quantity_change DECIMAL(14, 2) NOT NULL,
    reason VARCHAR(255) NULL,
    occurred_at DATETIME(6) NOT NULL,
    created_by BIGINT UNSIGNED NULL,
    KEY idx_ledger_company_product_time (company_id, product_id, occurred_at),
    KEY idx_ledger_company_reference (company_id, reference_type, reference_id),
    CONSTRAINT fk_ledger_company FOREIGN KEY (company_id) REFERENCES companies (company_id),
    CONSTRAINT fk_ledger_product FOREIGN KEY (product_id) REFERENCES products (product_id)
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

CREATE TABLE IF NOT EXISTS forecasts (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    company_id BIGINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    run_id BIGINT UNSIGNED NOT NULL,
    forecast_date DATE NOT NULL,
    avg_daily_demand DECIMAL(14, 4) NOT NULL DEFAULT 0.0000,
    predicted_demand DECIMAL(14, 4) NOT NULL DEFAULT 0.0000,
    lower_bound DECIMAL(14, 4) NULL,
    upper_bound DECIMAL(14, 4) NULL,
    model_type VARCHAR(40) NOT NULL DEFAULT 'SARIMA',
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_forecasts_run_product_day (company_id, run_id, product_id, forecast_date),
    KEY idx_forecasts_company_day (company_id, forecast_date),
    CONSTRAINT fk_forecasts_company FOREIGN KEY (company_id) REFERENCES companies (company_id),
    CONSTRAINT fk_forecasts_product FOREIGN KEY (product_id) REFERENCES products (product_id),
    CONSTRAINT fk_forecasts_run FOREIGN KEY (run_id) REFERENCES forecast_runs (run_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS forecast_metrics (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    company_id BIGINT UNSIGNED NOT NULL,
    run_id BIGINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
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

CREATE TABLE IF NOT EXISTS reorder_suggestions (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    company_id BIGINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    vendor_id BIGINT UNSIGNED NULL,
    recommended_quantity INT NOT NULL,
    generated_date DATETIME(6) NOT NULL,
    status ENUM('PENDING', 'ORDERED', 'DISMISSED', 'SUPERSEDED') NOT NULL DEFAULT 'PENDING',
    status_updated_at DATETIME(6) NULL,
    status_updated_by BIGINT UNSIGNED NULL,
    forecast_run_id BIGINT UNSIGNED NULL,
    KEY idx_reorder_company_status (company_id, status, product_id),
    CONSTRAINT fk_reorder_company FOREIGN KEY (company_id) REFERENCES companies (company_id),
    CONSTRAINT fk_reorder_product FOREIGN KEY (product_id) REFERENCES products (product_id),
    CONSTRAINT fk_reorder_vendor FOREIGN KEY (vendor_id) REFERENCES vendors (vendor_id),
    CONSTRAINT fk_reorder_run FOREIGN KEY (forecast_run_id) REFERENCES forecast_runs (run_id)
) ENGINE=InnoDB;

