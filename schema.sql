PRAGMA foreign_keys = ON;

BEGIN TRANSACTION;

-- =========================================================
-- USERS / AUTH / SETTINGS
-- =========================================================
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    full_name       TEXT NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('admin','pharmacist','cashier')),
    avatar          TEXT,
    phone           TEXT,
    email           TEXT,
    is_active       INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    last_login_at   TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS user_sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    session_token   TEXT NOT NULL UNIQUE,
    ip_address      TEXT,
    user_agent      TEXT,
    expires_at      TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS system_settings (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL,
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- =========================================================
-- INVENTORY
-- =========================================================
CREATE TABLE IF NOT EXISTS products (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT NOT NULL,
    barcode             TEXT NOT NULL UNIQUE,
    category            TEXT NOT NULL CHECK (category IN ('medicine','cosmetic','supplement','equipment','baby','herbal')),
    description         TEXT,
    price               REAL NOT NULL CHECK (price >= 0),
    cost                REAL NOT NULL CHECK (cost >= 0),
    vat_rate            REAL NOT NULL DEFAULT 0.15 CHECK (vat_rate >= 0),
    stock               INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
    min_stock           INTEGER NOT NULL DEFAULT 10 CHECK (min_stock >= 0),
    is_active           INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS product_batches (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id          INTEGER NOT NULL,
    batch_number        TEXT NOT NULL,
    quantity            INTEGER NOT NULL CHECK (quantity >= 0),
    remaining_quantity  INTEGER NOT NULL CHECK (remaining_quantity >= 0),
    cost_price          REAL NOT NULL CHECK (cost_price >= 0),
    purchase_date       TEXT,
    expiry_date         TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','expired','damaged','returned')),
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(product_id, batch_number),
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS inventory_movements (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id          INTEGER NOT NULL,
    batch_id            INTEGER,
    movement_type       TEXT NOT NULL CHECK (movement_type IN ('purchase_in','sale_out','adjustment_in','adjustment_out','damaged_out','expired_out','return_in','return_out')),
    quantity            INTEGER NOT NULL CHECK (quantity > 0),
    unit_cost           REAL,
    unit_price          REAL,
    reference_type      TEXT,
    reference_id        INTEGER,
    notes               TEXT,
    moved_by_user_id    INTEGER,
    moved_at            TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE RESTRICT,
    FOREIGN KEY (batch_id) REFERENCES product_batches(id) ON DELETE SET NULL,
    FOREIGN KEY (moved_by_user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS damaged_items (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id          INTEGER NOT NULL,
    batch_id            INTEGER,
    quantity            INTEGER NOT NULL CHECK (quantity > 0),
    reason              TEXT NOT NULL CHECK (reason IN ('expired','damaged','broken','returned','other')),
    unit_cost           REAL NOT NULL DEFAULT 0 CHECK (unit_cost >= 0),
    total_value         REAL NOT NULL DEFAULT 0 CHECK (total_value >= 0),
    note                TEXT,
    reported_by_user_id INTEGER,
    reported_at         TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE RESTRICT,
    FOREIGN KEY (batch_id) REFERENCES product_batches(id) ON DELETE SET NULL,
    FOREIGN KEY (reported_by_user_id) REFERENCES users(id) ON DELETE SET NULL
);

-- =========================================================
-- SUPPLIERS / PURCHASES
-- =========================================================
CREATE TABLE IF NOT EXISTS suppliers (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT NOT NULL,
    phone               TEXT,
    email               TEXT,
    address             TEXT,
    balance             REAL NOT NULL DEFAULT 0,
    status              TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','inactive')),
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS purchase_invoices (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_number      TEXT NOT NULL UNIQUE,
    supplier_id         INTEGER NOT NULL,
    invoice_date        TEXT NOT NULL,
    subtotal            REAL NOT NULL DEFAULT 0 CHECK (subtotal >= 0),
    discount            REAL NOT NULL DEFAULT 0 CHECK (discount >= 0),
    tax                 REAL NOT NULL DEFAULT 0 CHECK (tax >= 0),
    total               REAL NOT NULL CHECK (total >= 0),
    paid                REAL NOT NULL DEFAULT 0 CHECK (paid >= 0),
    remaining           REAL NOT NULL DEFAULT 0 CHECK (remaining >= 0),
    status              TEXT NOT NULL CHECK (status IN ('paid','partial','unpaid','cancelled')),
    notes               TEXT,
    created_by_user_id  INTEGER,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (supplier_id) REFERENCES suppliers(id) ON DELETE RESTRICT,
    FOREIGN KEY (created_by_user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS purchase_invoice_items (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    purchase_invoice_id     INTEGER NOT NULL,
    product_id              INTEGER,
    product_name_snapshot   TEXT NOT NULL,
    barcode_snapshot        TEXT,
    quantity                INTEGER NOT NULL CHECK (quantity > 0),
    unit_price              REAL NOT NULL CHECK (unit_price >= 0),
    line_total              REAL NOT NULL CHECK (line_total >= 0),
    batch_number            TEXT,
    expiry_date             TEXT,
    created_at              TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (purchase_invoice_id) REFERENCES purchase_invoices(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS purchase_payments (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    purchase_invoice_id INTEGER NOT NULL,
    payment_date        TEXT NOT NULL,
    amount              REAL NOT NULL CHECK (amount > 0),
    method              TEXT NOT NULL CHECK (method IN ('cash','bank_transfer','card','check','other')),
    reference_no        TEXT,
    note                TEXT,
    created_by_user_id  INTEGER,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (purchase_invoice_id) REFERENCES purchase_invoices(id) ON DELETE CASCADE,
    FOREIGN KEY (created_by_user_id) REFERENCES users(id) ON DELETE SET NULL
);

-- =========================================================
-- SALES / POS
-- =========================================================
CREATE TABLE IF NOT EXISTS sales (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_number          TEXT NOT NULL UNIQUE,
    sale_date               TEXT NOT NULL DEFAULT (datetime('now')),
    pharmacist_user_id      INTEGER,
    pharmacist_name_snapshot TEXT,
    customer_name           TEXT,
    customer_phone          TEXT,
    payment_method          TEXT NOT NULL CHECK (payment_method IN ('cash','card','insurance','debt','mixed')),
    insurance_company_id    INTEGER,
    subtotal                REAL NOT NULL CHECK (subtotal >= 0),
    tax                     REAL NOT NULL CHECK (tax >= 0),
    total                   REAL NOT NULL CHECK (total >= 0),
    discount                REAL NOT NULL DEFAULT 0 CHECK (discount >= 0),
    final_total             REAL NOT NULL CHECK (final_total >= 0),
    amount_received         REAL,
    change_amount           REAL,
    status                  TEXT NOT NULL DEFAULT 'completed' CHECK (status IN ('completed','cancelled','refunded')),
    note                    TEXT,
    created_at              TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (pharmacist_user_id) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (insurance_company_id) REFERENCES insurance_companies(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS sale_items (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id                 INTEGER NOT NULL,
    product_id              INTEGER,
    batch_id                INTEGER,
    product_name_snapshot   TEXT NOT NULL,
    barcode_snapshot        TEXT,
    quantity                INTEGER NOT NULL CHECK (quantity > 0),
    unit_price              REAL NOT NULL CHECK (unit_price >= 0),
    unit_cost               REAL NOT NULL DEFAULT 0 CHECK (unit_cost >= 0),
    vat_rate                REAL NOT NULL DEFAULT 0.15 CHECK (vat_rate >= 0),
    line_subtotal           REAL NOT NULL CHECK (line_subtotal >= 0),
    line_tax                REAL NOT NULL CHECK (line_tax >= 0),
    line_total              REAL NOT NULL CHECK (line_total >= 0),
    FOREIGN KEY (sale_id) REFERENCES sales(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL,
    FOREIGN KEY (batch_id) REFERENCES product_batches(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS sale_drafts (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_code              TEXT NOT NULL UNIQUE,
    user_id                 INTEGER,
    cart_json               TEXT NOT NULL,
    subtotal                REAL NOT NULL DEFAULT 0,
    tax                     REAL NOT NULL DEFAULT 0,
    total                   REAL NOT NULL DEFAULT 0,
    created_at              TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at              TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);

-- =========================================================
-- CUSTOMER DEBTS
-- =========================================================
CREATE TABLE IF NOT EXISTS customer_debts (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_name       TEXT NOT NULL,
    phone               TEXT,
    source_sale_id      INTEGER,
    amount              REAL NOT NULL CHECK (amount >= 0),
    paid                REAL NOT NULL DEFAULT 0 CHECK (paid >= 0),
    remaining           REAL NOT NULL CHECK (remaining >= 0),
    due_date            TEXT NOT NULL,
    status              TEXT NOT NULL CHECK (status IN ('pending','due-today','overdue','paid','cancelled')),
    notes               TEXT,
    created_by_user_id  INTEGER,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    closed_at           TEXT,
    FOREIGN KEY (source_sale_id) REFERENCES sales(id) ON DELETE SET NULL,
    FOREIGN KEY (created_by_user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS debt_payments (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    debt_id             INTEGER NOT NULL,
    payment_date        TEXT NOT NULL,
    amount              REAL NOT NULL CHECK (amount > 0),
    method              TEXT NOT NULL CHECK (method IN ('cash','card','transfer','other')),
    reference_no        TEXT,
    note                TEXT,
    collected_by_user_id INTEGER,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (debt_id) REFERENCES customer_debts(id) ON DELETE CASCADE,
    FOREIGN KEY (collected_by_user_id) REFERENCES users(id) ON DELETE SET NULL
);

-- =========================================================
-- INSURANCE
-- =========================================================
CREATE TABLE IF NOT EXISTS insurance_companies (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT NOT NULL UNIQUE,
    phone               TEXT,
    email               TEXT,
    contract_number     TEXT,
    discount_rate       REAL NOT NULL DEFAULT 0 CHECK (discount_rate >= 0 AND discount_rate <= 100),
    status              TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','inactive')),
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS insurance_claims (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id             INTEGER NOT NULL,
    insurance_company_id INTEGER NOT NULL,
    claim_number        TEXT UNIQUE,
    claim_date          TEXT NOT NULL,
    approved_amount     REAL NOT NULL DEFAULT 0 CHECK (approved_amount >= 0),
    patient_share       REAL NOT NULL DEFAULT 0 CHECK (patient_share >= 0),
    status              TEXT NOT NULL DEFAULT 'submitted' CHECK (status IN ('submitted','approved','rejected','paid')),
    notes               TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (sale_id) REFERENCES sales(id) ON DELETE CASCADE,
    FOREIGN KEY (insurance_company_id) REFERENCES insurance_companies(id) ON DELETE RESTRICT
);

-- =========================================================
-- ALERTS / AUDIT
-- =========================================================
CREATE TABLE IF NOT EXISTS notifications (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    type                TEXT NOT NULL,
    title               TEXT NOT NULL,
    message             TEXT NOT NULL,
    severity            TEXT NOT NULL DEFAULT 'info' CHECK (severity IN ('info','warning','error')),
    related_table       TEXT,
    related_id          INTEGER,
    is_read             INTEGER NOT NULL DEFAULT 0 CHECK (is_read IN (0,1)),
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER,
    action              TEXT NOT NULL,
    table_name          TEXT,
    record_id           INTEGER,
    old_values          TEXT,
    new_values          TEXT,
    ip_address          TEXT,
    user_agent          TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);

-- =========================================================
-- INDEXES
-- =========================================================
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_products_name ON products(name);
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);
CREATE INDEX IF NOT EXISTS idx_products_stock ON products(stock);
CREATE INDEX IF NOT EXISTS idx_product_batches_product ON product_batches(product_id);
CREATE INDEX IF NOT EXISTS idx_product_batches_expiry ON product_batches(expiry_date);
CREATE INDEX IF NOT EXISTS idx_inventory_movements_product ON inventory_movements(product_id);
CREATE INDEX IF NOT EXISTS idx_purchase_invoices_supplier ON purchase_invoices(supplier_id);
CREATE INDEX IF NOT EXISTS idx_purchase_invoices_date ON purchase_invoices(invoice_date);
CREATE INDEX IF NOT EXISTS idx_sales_date ON sales(sale_date);
CREATE INDEX IF NOT EXISTS idx_sales_payment_method ON sales(payment_method);
CREATE INDEX IF NOT EXISTS idx_sale_items_sale ON sale_items(sale_id);
CREATE INDEX IF NOT EXISTS idx_customer_debts_due ON customer_debts(due_date);
CREATE INDEX IF NOT EXISTS idx_customer_debts_status ON customer_debts(status);
CREATE INDEX IF NOT EXISTS idx_debt_payments_debt ON debt_payments(debt_id);
CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications(is_read, created_at);

-- =========================================================
-- TRIGGERS: updated_at helpers
-- =========================================================
CREATE TRIGGER IF NOT EXISTS trg_users_updated_at
AFTER UPDATE ON users
FOR EACH ROW
BEGIN
    UPDATE users SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_products_updated_at
AFTER UPDATE ON products
FOR EACH ROW
BEGIN
    UPDATE products SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_suppliers_updated_at
AFTER UPDATE ON suppliers
FOR EACH ROW
BEGIN
    UPDATE suppliers SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_purchase_invoices_updated_at
AFTER UPDATE ON purchase_invoices
FOR EACH ROW
BEGIN
    UPDATE purchase_invoices SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_insurance_companies_updated_at
AFTER UPDATE ON insurance_companies
FOR EACH ROW
BEGIN
    UPDATE insurance_companies SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_sale_drafts_updated_at
AFTER UPDATE ON sale_drafts
FOR EACH ROW
BEGIN
    UPDATE sale_drafts SET updated_at = datetime('now') WHERE id = NEW.id;
END;

-- =========================================================
-- VIEWS: reporting shortcuts
-- =========================================================
CREATE VIEW IF NOT EXISTS v_supplier_balances AS
SELECT
    s.id AS supplier_id,
    s.name AS supplier_name,
    COALESCE(SUM(pi.total), 0) AS total_invoiced,
    COALESCE(SUM(pi.paid), 0) AS total_paid,
    COALESCE(SUM(pi.remaining), 0) AS total_due
FROM suppliers s
LEFT JOIN purchase_invoices pi ON pi.supplier_id = s.id AND pi.status <> 'cancelled'
GROUP BY s.id, s.name;

CREATE VIEW IF NOT EXISTS v_customer_debts_open AS
SELECT
    id,
    customer_name,
    phone,
    due_date,
    amount,
    paid,
    remaining,
    status
FROM customer_debts
WHERE status IN ('pending','due-today','overdue') AND remaining > 0;

CREATE VIEW IF NOT EXISTS v_low_stock_products AS
SELECT
    id,
    name,
    barcode,
    category,
    stock,
    min_stock
FROM products
WHERE is_active = 1 AND stock <= min_stock;

CREATE VIEW IF NOT EXISTS v_sales_daily AS
SELECT
    date(sale_date) AS day,
    COUNT(*) AS invoices_count,
    SUM(subtotal) AS subtotal,
    SUM(tax) AS total_tax,
    SUM(final_total) AS net_sales
FROM sales
WHERE status = 'completed'
GROUP BY date(sale_date)
ORDER BY day DESC;

-- =========================================================
-- OPTIONAL SEED (DEV ONLY) - replace password_hash in production
-- =========================================================
INSERT OR IGNORE INTO users (username, password_hash, full_name, role, avatar)
VALUES
    ('admin', 'admin', 'المدير', 'admin', 'م'),
    ('pharma', 'pharma', 'د. أحمد', 'pharmacist', 'أ');

INSERT OR IGNORE INTO system_settings(key, value) VALUES
    ('taxRate', '0.15'),
    ('lowStockThreshold', '10'),
    ('expiryAlertDays', '30'),
    ('pharmacyName', 'صيدلية الشفاء'),
    ('pharmacyAddress', 'الرياض، المملكة العربية السعودية'),
    ('pharmacyPhone', '0123456789');

COMMIT;
