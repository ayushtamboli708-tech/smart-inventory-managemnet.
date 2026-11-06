-- Demo seed for a fresh database. Safe to run once after migrations.
-- Owner:  owner / ChangeMe123!
-- Staff:  cashier / Staff123!

INSERT INTO companies (company_id, code, name)
VALUES (1, 'demo', 'Stockwise Demo')
ON DUPLICATE KEY UPDATE name = VALUES(name), code = VALUES(code);

INSERT INTO users
    (user_id, company_id, username, password, role, is_active, created_by, updated_by)
VALUES
    (1, 1, 'owner',
     '$2b$12$lz3ZhgTTJ37iT3j1.AYOv.q.0qt09TlHOCxh7Br0kHq3H49E0yAky',
     'Owner', 1, 1, 1),
    (2, 1, 'cashier',
     '$2b$12$BVsw/0peyDo1esdq/ibliOxbhaLlQlGtoULR/Xzb/xSurwDCIQtDW',
     'Staff', 1, 1, 1)
ON DUPLICATE KEY UPDATE
    password = VALUES(password), role = VALUES(role), is_active = 1;

INSERT INTO vendors
    (vendor_id, company_id, name, contact, address, lead_time_days, is_active, created_by, updated_by)
VALUES
    (1, 1, 'Northwind Dairy', 'orders@northwind.example', 'Industrial Area, Pune', 3, 1, 1, 1),
    (2, 1, 'Sunrise Distributors', 'sales@sunrise.example', 'Market Road, Nashik', 5, 1, 1, 1)
ON DUPLICATE KEY UPDATE
    contact = VALUES(contact), address = VALUES(address), is_active = 1;

INSERT INTO products
    (product_id, company_id, sku, name, category, unit, selling_price,
     reorder_threshold, stock_qty, is_active, created_by, updated_by)
VALUES
    (1, 1, 'DAI-001', 'Full Cream Milk 1L', 'Dairy', 'Ltr', 68.00, 40, 1000, 1, 1, 1),
    (2, 1, 'DAI-002', 'Paneer 250g', 'Dairy', 'Pc', 95.00, 20, 600, 1, 1, 1),
    (3, 1, 'BEV-001', 'Filter Coffee 200g', 'Beverages', 'Pc', 210.00, 15, 400, 1, 1, 1),
    (4, 1, 'SNK-001', 'Masala Chips 90g', 'Snacks', 'Pc', 40.00, 30, 800, 1, 1, 1),
    (5, 1, 'GRO-001', 'Basmati Rice 5kg', 'Grocery', 'Box', 620.00, 10, 250, 1, 1, 1)
ON DUPLICATE KEY UPDATE
    name = VALUES(name), selling_price = VALUES(selling_price),
    reorder_threshold = VALUES(reorder_threshold), is_active = 1;

INSERT INTO product_vendors
    (company_id, product_id, vendor_id, cost_price, is_primary)
VALUES
    (1, 1, 1, 46.00, 1),
    (1, 2, 1, 68.00, 1),
    (1, 3, 2, 158.00, 1),
    (1, 4, 2, 27.00, 1),
    (1, 5, 2, 520.00, 1)
ON DUPLICATE KEY UPDATE
    cost_price = VALUES(cost_price), is_primary = VALUES(is_primary);

INSERT INTO inventory_ledger
    (company_id, product_id, transaction_type, reference_type, reference_id,
     quantity_change, reason, occurred_at, created_by)
SELECT 1, p.product_id, 'ADJUSTMENT', 'OPENING', p.product_id,
       p.stock_qty, 'Opening balance', UTC_TIMESTAMP(6), 1
FROM products p
WHERE p.company_id = 1
  AND NOT EXISTS (
      SELECT 1 FROM inventory_ledger il
      WHERE il.company_id = 1 AND il.product_id = p.product_id
  );
