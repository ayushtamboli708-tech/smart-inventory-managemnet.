-- Migration 002: audit trail table.
-- Every write service records actor, action, entity, and optional JSON details.

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
