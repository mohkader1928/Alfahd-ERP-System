# Phase 7 — Database Design

**Status:** Draft for approval | **Version:** 0.1
**Builds on:** [06-er-diagram.md](06-er-diagram.md)
**Target engine:** PostgreSQL 15+

---

## 1. Conventions

### 1.1 Common Envelope

Every tenant-scoped table includes these columns (per FR-CORE-020). Shown once here; omitted from individual `CREATE TABLE` statements below except where it deviates.

```sql
id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
tenant_id     UUID NOT NULL,
company_id    UUID NOT NULL REFERENCES company(id),
branch_id     UUID NULL REFERENCES branch(id),        -- NULL = company-wide record
created_by    UUID NOT NULL REFERENCES app_user(id),
updated_by    UUID NULL REFERENCES app_user(id),
deleted_by    UUID NULL REFERENCES app_user(id),
created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
deleted_at    TIMESTAMPTZ NULL,
version       INTEGER NOT NULL DEFAULT 1
```

Extension required: `CREATE EXTENSION IF NOT EXISTS pgcrypto;` (for `gen_random_uuid()`).

### 1.2 Naming

- Tables: `snake_case`, singular (`sales_order`, not `sales_orders`).
- Foreign keys: `<referenced_table>_id`.
- Enums: PostgreSQL native `ENUM` types, named `<table>_<column>_enum`.
- Money columns: `NUMERIC(18,4)` — never `FLOAT`/`REAL` for anything financial.
- Quantities: `NUMERIC(18,6)` (supports fractional UoM conversions).
- Booleans: `is_<adjective>`.

### 1.3 Soft Delete & Uniqueness

Because `deleted_at` is used instead of hard delete, all `UNIQUE` constraints that matter for active records must be **partial indexes**, e.g.:

```sql
CREATE UNIQUE INDEX ux_partner_vat_number
  ON partner (company_id, vat_number)
  WHERE deleted_at IS NULL;
```

Otherwise a deleted record would permanently block reuse of e.g. a VAT number.

### 1.4 Multi-Tenant Isolation Strategy (NFR-CORE-004 / FR-CORE-004)

Defense in depth, two layers:

1. **Application layer:** every repository query is required to include `tenant_id`/`company_id` filters via a shared base repository (enforced by code review + automated tests — see Phase 11).
2. **Database layer (belt-and-suspenders):** PostgreSQL **Row-Level Security (RLS)** enabled on every tenant table:

```sql
ALTER TABLE sales_order ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON sales_order
  USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
```

The application sets `SET LOCAL app.current_tenant_id = '<uuid>';` at the start of every request transaction. This means even a bug in application-level filtering **cannot** leak cross-tenant data — the database itself refuses to return other tenants' rows.

### 1.5 Optimistic Locking

Every UPDATE increments `version` and checks the previous value:

```sql
UPDATE sales_order SET ..., version = version + 1
WHERE id = :id AND version = :expected_version;
-- 0 rows affected => 409 Conflict returned to the client
```

### 1.6 Financial Integrity

Balanced-journal-entry enforcement (FR-ACC-003) cannot be a simple column `CHECK` (it aggregates sibling rows), so it is enforced via a deferred constraint trigger:

```sql
CREATE CONSTRAINT TRIGGER trg_journal_entry_balanced
  AFTER INSERT OR UPDATE ON journal_entry_line
  DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION fn_check_journal_balanced();
```

`fn_check_journal_balanced()` sums debit/credit for the affected `journal_entry_id` and raises an exception if they don't match at commit time — this is the database-level backstop behind the FR-ACC-003 service-layer check.

---

## 2. Module: Foundation & Master Data (M0)

```sql
CREATE TABLE tenant (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  legal_name    TEXT NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at    TIMESTAMPTZ NULL
);

CREATE TABLE company (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         UUID NOT NULL REFERENCES tenant(id),
  legal_name        TEXT NOT NULL,
  legal_name_ar     TEXT NOT NULL,
  vat_number        VARCHAR(15) NOT NULL,        -- ZATCA: 15-digit VAT registration number
  cr_number         VARCHAR(20) NULL,             -- Commercial Registration number
  base_currency_id  UUID NOT NULL REFERENCES currency(id),
  valuation_method  TEXT NOT NULL CHECK (valuation_method IN ('fifo','average')),
  zatca_environment TEXT NOT NULL DEFAULT 'sandbox' CHECK (zatca_environment IN ('sandbox','simulation','production')),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at        TIMESTAMPTZ NULL
);
CREATE UNIQUE INDEX ux_company_vat ON company (vat_number) WHERE deleted_at IS NULL;

CREATE TABLE branch (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     UUID NOT NULL,
  company_id    UUID NOT NULL REFERENCES company(id),
  name          TEXT NOT NULL,
  name_ar       TEXT NOT NULL,
  is_main       BOOLEAN NOT NULL DEFAULT false,
  address       JSONB NULL,                       -- {street, city, postal_code, additional_number} per ZATCA address fields
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at    TIMESTAMPTZ NULL
);

CREATE TABLE app_user (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        UUID NOT NULL,
  email            CITEXT NOT NULL,
  password_hash    TEXT NOT NULL,
  full_name        TEXT NOT NULL,
  preferred_locale TEXT NOT NULL DEFAULT 'ar' CHECK (preferred_locale IN ('ar','en')),
  preferred_calendar TEXT NOT NULL DEFAULT 'gregorian' CHECK (preferred_calendar IN ('gregorian','hijri')),
  totp_secret      TEXT NULL,
  is_2fa_enabled   BOOLEAN NOT NULL DEFAULT false,
  is_active        BOOLEAN NOT NULL DEFAULT true,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at       TIMESTAMPTZ NULL
);
CREATE UNIQUE INDEX ux_app_user_email ON app_user (email) WHERE deleted_at IS NULL;

CREATE TABLE user_company_access (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      UUID NOT NULL REFERENCES app_user(id),
  company_id   UUID NOT NULL REFERENCES company(id),
  branch_id    UUID NULL REFERENCES branch(id),      -- NULL = all branches of the company
  UNIQUE (user_id, company_id, branch_id)
);

CREATE TABLE role (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id    UUID NOT NULL REFERENCES company(id),
  name          TEXT NOT NULL,
  is_system     BOOLEAN NOT NULL DEFAULT false        -- system roles cannot be deleted
);

CREATE TABLE permission (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code          TEXT NOT NULL UNIQUE,                 -- e.g. 'sales_order.create', 'journal_entry.post'
  scope         TEXT NOT NULL CHECK (scope IN ('screen','field','action'))
);

CREATE TABLE role_permission (
  role_id       UUID NOT NULL REFERENCES role(id),
  permission_id UUID NOT NULL REFERENCES permission(id),
  PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE user_role (
  user_id UUID NOT NULL REFERENCES app_user(id),
  role_id UUID NOT NULL REFERENCES role(id),
  PRIMARY KEY (user_id, role_id)
);

CREATE TABLE record_rule (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  role_id       UUID NOT NULL REFERENCES role(id),
  target_table  TEXT NOT NULL,                        -- e.g. 'sales_order'
  filter_expr   JSONB NOT NULL                         -- structured condition, e.g. {"field":"sales_rep_id","op":"eq","value":"$current_user"}
);

CREATE TABLE audit_log (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     UUID NOT NULL,
  company_id    UUID NOT NULL,
  user_id       UUID NULL REFERENCES app_user(id),
  target_table  TEXT NOT NULL,
  target_id     UUID NOT NULL,
  field_name    TEXT NOT NULL,
  old_value     TEXT NULL,
  new_value     TEXT NULL,
  changed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_audit_log_target ON audit_log (target_table, target_id);

CREATE TABLE activity_log (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     UUID NOT NULL,
  company_id    UUID NOT NULL,
  user_id       UUID NULL REFERENCES app_user(id),
  action        TEXT NOT NULL,
  target_table  TEXT NULL,
  target_id     UUID NULL,
  occurred_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_activity_log_company_date ON activity_log (company_id, occurred_at DESC);

CREATE TABLE currency (
  id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code    CHAR(3) NOT NULL UNIQUE,                    -- ISO 4217, e.g. 'SAR'
  symbol  TEXT NOT NULL,
  decimal_places SMALLINT NOT NULL DEFAULT 2
);

CREATE TABLE currency_rate (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id    UUID NOT NULL REFERENCES company(id),
  currency_id   UUID NOT NULL REFERENCES currency(id),
  rate_date     DATE NOT NULL,
  rate_to_base  NUMERIC(18,6) NOT NULL,
  UNIQUE (company_id, currency_id, rate_date)
);

CREATE TABLE uom_category (
  id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name  TEXT NOT NULL
);

CREATE TABLE uom (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  category_id   UUID NOT NULL REFERENCES uom_category(id),
  name          TEXT NOT NULL,
  ratio_to_base NUMERIC(18,6) NOT NULL DEFAULT 1       -- conversion factor within category
);

CREATE TABLE partner (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     UUID NOT NULL,
  company_id    UUID NOT NULL REFERENCES company(id),
  name          TEXT NOT NULL,
  name_ar       TEXT NULL,
  is_customer   BOOLEAN NOT NULL DEFAULT false,
  is_vendor     BOOLEAN NOT NULL DEFAULT false,
  vat_number    VARCHAR(15) NULL,
  cr_number     VARCHAR(20) NULL,
  address       JSONB NULL,
  default_price_list_id UUID NULL,                     -- FK added after price_list is defined
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at    TIMESTAMPTZ NULL
);
CREATE UNIQUE INDEX ux_partner_vat ON partner (company_id, vat_number) WHERE deleted_at IS NULL AND vat_number IS NOT NULL;

CREATE TABLE product_category (
  id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL REFERENCES company(id),
  name    TEXT NOT NULL,
  parent_id UUID NULL REFERENCES product_category(id)
);

CREATE TABLE product (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      UUID NOT NULL,
  company_id     UUID NOT NULL REFERENCES company(id),
  sku            TEXT NOT NULL,
  name            TEXT NOT NULL,
  name_ar         TEXT NULL,
  category_id     UUID NULL REFERENCES product_category(id),
  uom_id          UUID NOT NULL REFERENCES uom(id),
  is_stockable    BOOLEAN NOT NULL DEFAULT true,        -- false = service item
  sales_price     NUMERIC(18,4) NOT NULL DEFAULT 0,
  cost_price      NUMERIC(18,4) NOT NULL DEFAULT 0,
  default_tax_rate_id UUID NULL,                        -- FK added after tax_rate is defined
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at      TIMESTAMPTZ NULL
);
CREATE UNIQUE INDEX ux_product_sku ON product (company_id, sku) WHERE deleted_at IS NULL;

CREATE TABLE attachment (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id     UUID NOT NULL REFERENCES company(id),
  target_table   TEXT NOT NULL,
  target_id      UUID NOT NULL,
  file_name      TEXT NOT NULL,
  storage_path   TEXT NOT NULL,
  content_type   TEXT NOT NULL,
  size_bytes     BIGINT NOT NULL,
  uploaded_by    UUID NOT NULL REFERENCES app_user(id),
  uploaded_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_attachment_target ON attachment (target_table, target_id);

CREATE TABLE approval_rule (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id     UUID NOT NULL REFERENCES company(id),
  target_table   TEXT NOT NULL,
  condition_expr JSONB NOT NULL,                        -- e.g. {"field":"total_amount","op":"gt","value":50000}
  approver_role_id UUID NOT NULL REFERENCES role(id),
  level          SMALLINT NOT NULL DEFAULT 1
);

CREATE TABLE approval_request (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id     UUID NOT NULL REFERENCES company(id),
  target_table   TEXT NOT NULL,
  target_id      UUID NOT NULL,
  status         TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
  current_level  SMALLINT NOT NULL DEFAULT 1,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE approval_step (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  approval_request_id UUID NOT NULL REFERENCES approval_request(id),
  level              SMALLINT NOT NULL,
  approver_id        UUID NULL REFERENCES app_user(id),
  decision           TEXT NULL CHECK (decision IN ('approved','rejected','delegated')),
  comment            TEXT NULL,
  decided_at         TIMESTAMPTZ NULL
);

CREATE TABLE notification (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID NOT NULL REFERENCES app_user(id),
  title       TEXT NOT NULL,
  body        TEXT NULL,
  target_table TEXT NULL,
  target_id   UUID NULL,
  is_read     BOOLEAN NOT NULL DEFAULT false,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_notification_user_unread ON notification (user_id) WHERE is_read = false;
```

---

## 3. Module: Accounting (M1)

```sql
CREATE TYPE account_type_enum AS ENUM ('asset','liability','equity','revenue','expense');

CREATE TABLE account_type (
  id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code  account_type_enum NOT NULL UNIQUE
);

CREATE TABLE account (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id     UUID NOT NULL REFERENCES company(id),
  code           TEXT NOT NULL,
  name           TEXT NOT NULL,
  name_ar        TEXT NULL,
  account_type_id UUID NOT NULL REFERENCES account_type(id),
  parent_id      UUID NULL REFERENCES account(id),
  is_active      BOOLEAN NOT NULL DEFAULT true,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at     TIMESTAMPTZ NULL
);
CREATE UNIQUE INDEX ux_account_code ON account (company_id, code) WHERE deleted_at IS NULL;

CREATE TABLE journal (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id  UUID NOT NULL REFERENCES company(id),
  code        TEXT NOT NULL,                            -- 'SALES','PURCH','BANK','CASH','GEN'
  name        TEXT NOT NULL,
  default_debit_account_id  UUID NULL REFERENCES account(id),
  default_credit_account_id UUID NULL REFERENCES account(id)
);

CREATE TABLE journal_entry (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id   UUID NOT NULL REFERENCES company(id),
  branch_id    UUID NULL REFERENCES branch(id),
  journal_id   UUID NOT NULL REFERENCES journal(id),
  entry_date   DATE NOT NULL,
  reference    TEXT NULL,                                -- e.g. link to source invoice number
  source_table TEXT NULL,                                -- polymorphic origin, e.g. 'sales_invoice'
  source_id    UUID NULL,
  status       TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','posted','reversed')),
  reversed_entry_id UUID NULL REFERENCES journal_entry(id),
  posted_at    TIMESTAMPTZ NULL,
  created_by   UUID NOT NULL REFERENCES app_user(id),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  version      INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX ix_journal_entry_source ON journal_entry (source_table, source_id);
-- A posted entry is immutable at the application layer (FR-ACC-004);
-- enforced by REVOKE UPDATE on posted rows via a BEFORE UPDATE trigger that
-- raises an exception when OLD.status = 'posted' and only 'reversed_entry_id'/'status' are allowed to change.

CREATE TABLE cost_center (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL REFERENCES company(id),
  name       TEXT NOT NULL
);

CREATE TABLE journal_entry_line (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  journal_entry_id UUID NOT NULL REFERENCES journal_entry(id),
  account_id       UUID NOT NULL REFERENCES account(id),
  cost_center_id   UUID NULL REFERENCES cost_center(id),
  debit            NUMERIC(18,4) NOT NULL DEFAULT 0 CHECK (debit >= 0),
  credit           NUMERIC(18,4) NOT NULL DEFAULT 0 CHECK (credit >= 0),
  description      TEXT NULL,
  CHECK (NOT (debit > 0 AND credit > 0))                  -- a line is either debit or credit, never both
);
CREATE INDEX ix_jel_entry ON journal_entry_line (journal_entry_id);
CREATE INDEX ix_jel_account ON journal_entry_line (account_id);

CREATE TYPE tax_kind_enum AS ENUM ('standard','zero_rated','exempt','out_of_scope');

CREATE TABLE tax_group (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL REFERENCES company(id),
  name       TEXT NOT NULL
);

CREATE TABLE tax_rate (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id    UUID NOT NULL REFERENCES company(id),
  tax_group_id  UUID NULL REFERENCES tax_group(id),
  name          TEXT NOT NULL,
  kind          tax_kind_enum NOT NULL,
  rate_percent  NUMERIC(5,2) NOT NULL DEFAULT 0,          -- 15.00, 0.00
  is_withholding BOOLEAN NOT NULL DEFAULT false
);

CREATE TABLE fiscal_period (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id  UUID NOT NULL REFERENCES company(id),
  period_start DATE NOT NULL,
  period_end   DATE NOT NULL,
  is_closed    BOOLEAN NOT NULL DEFAULT false,
  UNIQUE (company_id, period_start, period_end)
);

-- Deferred FKs from Section 2 now resolvable:
ALTER TABLE partner ADD CONSTRAINT fk_partner_price_list FOREIGN KEY (default_price_list_id) REFERENCES price_list(id);
ALTER TABLE product ADD CONSTRAINT fk_product_tax_rate FOREIGN KEY (default_tax_rate_id) REFERENCES tax_rate(id);
```

---

## 4. Module: Sales & E-Invoicing (M2)

```sql
CREATE TABLE price_list (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL REFERENCES company(id),
  name       TEXT NOT NULL,
  currency_id UUID NOT NULL REFERENCES currency(id)
);

CREATE TABLE price_list_item (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  price_list_id UUID NOT NULL REFERENCES price_list(id),
  product_id    UUID NOT NULL REFERENCES product(id),
  price         NUMERIC(18,4) NOT NULL,
  UNIQUE (price_list_id, product_id)
);

CREATE TYPE doc_status_enum AS ENUM ('draft','confirmed','done','cancelled');

CREATE TABLE quotation (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id   UUID NOT NULL REFERENCES company(id),
  branch_id    UUID NOT NULL REFERENCES branch(id),
  partner_id   UUID NOT NULL REFERENCES partner(id),
  number       TEXT NOT NULL,
  status       doc_status_enum NOT NULL DEFAULT 'draft',
  currency_id  UUID NOT NULL REFERENCES currency(id),
  quote_date   DATE NOT NULL DEFAULT CURRENT_DATE,
  total_amount NUMERIC(18,4) NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX ux_quotation_number ON quotation (company_id, number);

CREATE TABLE quotation_line (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  quotation_id UUID NOT NULL REFERENCES quotation(id),
  product_id   UUID NOT NULL REFERENCES product(id),
  qty          NUMERIC(18,6) NOT NULL,
  unit_price   NUMERIC(18,4) NOT NULL,
  tax_rate_id  UUID NOT NULL REFERENCES tax_rate(id)
);

CREATE TABLE sales_order (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id   UUID NOT NULL REFERENCES company(id),
  branch_id    UUID NOT NULL REFERENCES branch(id),
  partner_id   UUID NOT NULL REFERENCES partner(id),
  quotation_id UUID NULL REFERENCES quotation(id),
  number       TEXT NOT NULL,
  status       doc_status_enum NOT NULL DEFAULT 'draft',
  currency_id  UUID NOT NULL REFERENCES currency(id),
  order_date   DATE NOT NULL DEFAULT CURRENT_DATE,
  total_amount NUMERIC(18,4) NOT NULL DEFAULT 0,
  version      INTEGER NOT NULL DEFAULT 1
);
CREATE UNIQUE INDEX ux_sales_order_number ON sales_order (company_id, number);

CREATE TABLE sales_order_line (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  sales_order_id UUID NOT NULL REFERENCES sales_order(id),
  product_id     UUID NOT NULL REFERENCES product(id),
  qty            NUMERIC(18,6) NOT NULL,
  unit_price     NUMERIC(18,4) NOT NULL,
  tax_rate_id    UUID NOT NULL REFERENCES tax_rate(id),
  qty_delivered  NUMERIC(18,6) NOT NULL DEFAULT 0,
  qty_invoiced   NUMERIC(18,6) NOT NULL DEFAULT 0
);

CREATE TABLE delivery (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id     UUID NOT NULL REFERENCES company(id),
  branch_id      UUID NOT NULL REFERENCES branch(id),
  sales_order_id UUID NOT NULL REFERENCES sales_order(id),
  warehouse_id   UUID NOT NULL REFERENCES warehouse(id),
  number         TEXT NOT NULL,
  status         doc_status_enum NOT NULL DEFAULT 'draft',
  delivery_date  DATE NOT NULL DEFAULT CURRENT_DATE
);

CREATE TABLE delivery_line (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  delivery_id  UUID NOT NULL REFERENCES delivery(id),
  sales_order_line_id UUID NOT NULL REFERENCES sales_order_line(id),
  product_id   UUID NOT NULL REFERENCES product(id),
  qty          NUMERIC(18,6) NOT NULL,
  stock_move_id UUID NULL REFERENCES stock_move(id)
);

CREATE TYPE invoice_type_enum AS ENUM ('tax','simplified','credit_note','debit_note');
CREATE TYPE invoice_status_enum AS ENUM ('draft','pending_submission','cleared','reported','rejected','cancelled');

CREATE TABLE sales_invoice (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id         UUID NOT NULL REFERENCES company(id),
  branch_id          UUID NOT NULL REFERENCES branch(id),
  partner_id         UUID NOT NULL REFERENCES partner(id),
  sales_order_id     UUID NULL REFERENCES sales_order(id),
  delivery_id        UUID NULL REFERENCES delivery(id),
  original_invoice_id UUID NULL REFERENCES sales_invoice(id),   -- set for credit/debit notes
  invoice_type       invoice_type_enum NOT NULL,
  number             TEXT NOT NULL,
  status             invoice_status_enum NOT NULL DEFAULT 'draft',
  currency_id        UUID NOT NULL REFERENCES currency(id),
  invoice_date       DATE NOT NULL DEFAULT CURRENT_DATE,
  subtotal_amount    NUMERIC(18,4) NOT NULL DEFAULT 0,
  tax_amount         NUMERIC(18,4) NOT NULL DEFAULT 0,
  total_amount       NUMERIC(18,4) NOT NULL DEFAULT 0,
  journal_entry_id   UUID NULL REFERENCES journal_entry(id),
  version            INTEGER NOT NULL DEFAULT 1
);
CREATE UNIQUE INDEX ux_sales_invoice_number ON sales_invoice (company_id, number);

CREATE TABLE sales_invoice_line (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  sales_invoice_id  UUID NOT NULL REFERENCES sales_invoice(id),
  product_id        UUID NOT NULL REFERENCES product(id),
  qty               NUMERIC(18,6) NOT NULL,
  unit_price        NUMERIC(18,4) NOT NULL,
  tax_rate_id       UUID NOT NULL REFERENCES tax_rate(id),
  line_total        NUMERIC(18,4) NOT NULL
);

CREATE TABLE zatca_submission (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  sales_invoice_id UUID NOT NULL REFERENCES sales_invoice(id),
  uuid_value       UUID NOT NULL,                              -- ZATCA invoice UUID (distinct from PK)
  icv              BIGINT NOT NULL,                             -- Invoice Counter Value, per-device monotonic
  previous_hash    TEXT NOT NULL,
  invoice_hash     TEXT NOT NULL,
  qr_payload       TEXT NOT NULL,
  xml_document     TEXT NOT NULL,
  submission_mode  TEXT NOT NULL CHECK (submission_mode IN ('clearance','reporting')),
  status           invoice_status_enum NOT NULL DEFAULT 'pending_submission',
  zatca_response   JSONB NULL,
  submitted_at     TIMESTAMPTZ NULL,
  retry_count      INTEGER NOT NULL DEFAULT 0,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX ux_zatca_invoice ON zatca_submission (sales_invoice_id);
-- Hash-chain integrity: previous_hash of invoice N must equal invoice_hash of invoice N-1
-- within the same company+branch device sequence. Enforced in the ZATCA Adapter service (Phase 8),
-- verified periodically by a consistency-check job.
```

---

## 5. Module: Inventory (M3)

```sql
CREATE TABLE warehouse (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL REFERENCES company(id),
  branch_id  UUID NOT NULL REFERENCES branch(id),
  name       TEXT NOT NULL
);

CREATE TABLE location (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  warehouse_id UUID NOT NULL REFERENCES warehouse(id),
  parent_id    UUID NULL REFERENCES location(id),
  name         TEXT NOT NULL,
  is_virtual   BOOLEAN NOT NULL DEFAULT false           -- e.g. 'Customer', 'Inventory Loss' virtual locations
);

CREATE TYPE stock_move_type_enum AS ENUM ('receipt','delivery','transfer','adjustment');

CREATE TABLE stock_move (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id      UUID NOT NULL REFERENCES company(id),
  product_id      UUID NOT NULL REFERENCES product(id),
  source_location_id UUID NOT NULL REFERENCES location(id),
  dest_location_id   UUID NOT NULL REFERENCES location(id),
  qty             NUMERIC(18,6) NOT NULL CHECK (qty > 0),
  unit_cost       NUMERIC(18,4) NOT NULL,
  move_type       stock_move_type_enum NOT NULL,
  source_table    TEXT NOT NULL,                        -- 'delivery_line','goods_receipt_line','cycle_count_line','stock_transfer'
  source_id       UUID NOT NULL,
  moved_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  journal_entry_id UUID NULL REFERENCES journal_entry(id)
);
CREATE INDEX ix_stock_move_product_loc ON stock_move (product_id, dest_location_id);

CREATE TABLE stock_quant (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id       UUID NOT NULL REFERENCES company(id),
  product_id       UUID NOT NULL REFERENCES product(id),
  location_id      UUID NOT NULL REFERENCES location(id),
  qty_on_hand      NUMERIC(18,6) NOT NULL DEFAULT 0,
  moving_avg_cost  NUMERIC(18,4) NOT NULL DEFAULT 0,     -- used only when company.valuation_method = 'average'
  UNIQUE (product_id, location_id)
);
CREATE INDEX ix_stock_quant_negative ON stock_quant (product_id, location_id) WHERE qty_on_hand < 0;

CREATE TABLE stock_layer (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id    UUID NOT NULL REFERENCES company(id),
  product_id    UUID NOT NULL REFERENCES product(id),
  location_id   UUID NOT NULL REFERENCES location(id),
  qty_remaining NUMERIC(18,6) NOT NULL CHECK (qty_remaining >= 0),
  unit_cost     NUMERIC(18,4) NOT NULL,
  received_at   TIMESTAMPTZ NOT NULL DEFAULT now()
  -- used only when company.valuation_method = 'fifo'; consumed oldest-first
);
CREATE INDEX ix_stock_layer_fifo ON stock_layer (product_id, location_id, received_at) WHERE qty_remaining > 0;

CREATE TABLE cycle_count (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id   UUID NOT NULL REFERENCES company(id),
  warehouse_id UUID NOT NULL REFERENCES warehouse(id),
  status       TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','counted','approved')),
  scheduled_date DATE NOT NULL
);

CREATE TABLE cycle_count_line (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  cycle_count_id  UUID NOT NULL REFERENCES cycle_count(id),
  product_id      UUID NOT NULL REFERENCES product(id),
  location_id     UUID NOT NULL REFERENCES location(id),
  system_qty      NUMERIC(18,6) NOT NULL,
  counted_qty     NUMERIC(18,6) NOT NULL,
  stock_move_id   UUID NULL REFERENCES stock_move(id)
);
```

---

## 6. Module: Purchasing (M4)

```sql
CREATE TABLE purchase_order (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id   UUID NOT NULL REFERENCES company(id),
  branch_id    UUID NOT NULL REFERENCES branch(id),
  partner_id   UUID NOT NULL REFERENCES partner(id),
  number       TEXT NOT NULL,
  status       doc_status_enum NOT NULL DEFAULT 'draft',
  currency_id  UUID NOT NULL REFERENCES currency(id),
  order_date   DATE NOT NULL DEFAULT CURRENT_DATE,
  total_amount NUMERIC(18,4) NOT NULL DEFAULT 0,
  approval_request_id UUID NULL REFERENCES approval_request(id)
);
CREATE UNIQUE INDEX ux_po_number ON purchase_order (company_id, number);

CREATE TABLE purchase_order_line (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  purchase_order_id  UUID NOT NULL REFERENCES purchase_order(id),
  product_id         UUID NOT NULL REFERENCES product(id),
  qty                NUMERIC(18,6) NOT NULL,
  unit_price         NUMERIC(18,4) NOT NULL,
  tax_rate_id        UUID NOT NULL REFERENCES tax_rate(id),
  qty_received       NUMERIC(18,6) NOT NULL DEFAULT 0,
  qty_billed         NUMERIC(18,6) NOT NULL DEFAULT 0
);

CREATE TABLE goods_receipt (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id        UUID NOT NULL REFERENCES company(id),
  purchase_order_id UUID NOT NULL REFERENCES purchase_order(id),
  warehouse_id      UUID NOT NULL REFERENCES warehouse(id),
  number            TEXT NOT NULL,
  status            doc_status_enum NOT NULL DEFAULT 'draft',
  receipt_date      DATE NOT NULL DEFAULT CURRENT_DATE
);

CREATE TABLE goods_receipt_line (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  goods_receipt_id    UUID NOT NULL REFERENCES goods_receipt(id),
  purchase_order_line_id UUID NOT NULL REFERENCES purchase_order_line(id),
  product_id          UUID NOT NULL REFERENCES product(id),
  qty                 NUMERIC(18,6) NOT NULL,
  stock_move_id       UUID NULL REFERENCES stock_move(id)
);

CREATE TABLE vendor_bill (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id         UUID NOT NULL REFERENCES company(id),
  branch_id          UUID NOT NULL REFERENCES branch(id),
  partner_id         UUID NOT NULL REFERENCES partner(id),
  purchase_order_id  UUID NOT NULL REFERENCES purchase_order(id),
  number             TEXT NOT NULL,
  vendor_reference   TEXT NULL,
  status             TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','matched','mismatched','approved','posted')),
  currency_id        UUID NOT NULL REFERENCES currency(id),
  bill_date          DATE NOT NULL DEFAULT CURRENT_DATE,
  total_amount       NUMERIC(18,4) NOT NULL DEFAULT 0,
  journal_entry_id   UUID NULL REFERENCES journal_entry(id)
);

CREATE TABLE vendor_bill_line (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  vendor_bill_id UUID NOT NULL REFERENCES vendor_bill(id),
  purchase_order_line_id UUID NOT NULL REFERENCES purchase_order_line(id),
  product_id     UUID NOT NULL REFERENCES product(id),
  qty            NUMERIC(18,6) NOT NULL,
  unit_price     NUMERIC(18,4) NOT NULL,
  tax_rate_id    UUID NOT NULL REFERENCES tax_rate(id)
);
```

---

## 7. Indexing Strategy Summary

| Pattern | Rationale |
|---------|-----------|
| `(company_id, number)` unique partial index on every numbered document | Document numbering is per-company, must remain unique among non-deleted rows |
| `(target_table, target_id)` on `attachment`, `audit_log` | Polymorphic lookups always filter by owning document |
| `(product_id, location_id)` on `stock_quant`, `stock_layer` | Every valuation/availability check is by product+location |
| Partial index `WHERE qty_on_hand < 0` on `stock_quant` | Cheap monitoring query for FR-INV-007 violations |
| Partial index `WHERE is_read = false` on `notification` | Unread-count queries dominate notification reads |
| `tenant_id` present on every RLS-enabled table, always the leading filter | RLS policies filter on it for every single query |

---

## 8. Migration Strategy (informs Phase 11)

- Schema managed via **Alembic** (SQLAlchemy's migration tool); every schema change is a versioned, reversible migration script — never a manual `ALTER` against production.
- Each module (Foundation, Accounting, Sales, Inventory, Purchasing) owns its migration namespace so a future module extraction doesn't require untangling migration history.
- Seed data (default Saudi Chart of Accounts template, default tax rates 15%/0%/Exempt/Out-of-Scope, SAR currency) shipped as an idempotent seed script, not baked into schema migrations.

---

## 9. General Acceptance Criteria

- [ ] Project owner (or a technical delegate) approves the schema, especially: the RLS-based tenant isolation strategy, the FIFO/Average dual-structure decision, and the `zatca_submission` table design.
- [ ] No table is added or removed without updating the Phase 6 ER diagram to match.

---

*End of Phase 7. Proceeding to Phase 8: System Architecture.*
