# Phase 2 — Functional Requirements

**Status:** Draft for approval | **Version:** 0.1
**Builds on:** [01-business-analysis.md](01-business-analysis.md) — Core Nucleus scope M0–M5

---

## 1. Numbering & Priority Scheme

Each requirement has a unique ID `FR-<Module>-<Seq>` and a MoSCoW priority:

- **M** = Must Have (the nucleus cannot ship without it)
- **S** = Should Have (important, but not release-blocking)
- **C** = Could Have (added if time allows)

---

## 2. FR-CORE — Architectural Foundation (M0)

### 2.1 Multi-Company & Multi-Branch
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-CORE-001 | The system allows creating more than one Company; each company has its own chart of accounts and base currency | M |
| FR-CORE-002 | Each Company can have multiple Branches; every document (invoice, sales order...) is tied to a specific branch | M |
| FR-CORE-003 | A user can be granted access to one or more company/branch combinations, and cannot see data outside that scope | M |
| FR-CORE-004 | No query can return data belonging to another Tenant/Company even if an application-level filtering bug occurs (isolation enforced at the query layer) | M |

### 2.2 Authentication & Authorization
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-CORE-010 | Login via JWT (Access + Refresh Token) | M |
| FR-CORE-011 | Two-Factor Authentication (2FA) via TOTP, optional per user or mandatory per company | M |
| FR-CORE-012 | Configurable password policy (length, complexity, expiry, reuse prevention) | M |
| FR-CORE-013 | Session management: view active sessions and revoke them remotely | S |
| FR-CORE-014 | RBAC: customizable Roles, each a set of Permissions | M |
| FR-CORE-015 | Screen-level permissions (which menus a user can see) | M |
| FR-CORE-016 | Field-level permissions (hide/read-only for sensitive fields like item cost or employee salary) | M |
| FR-CORE-017 | Record Rules: restrict visible records by condition (e.g., a sales rep only sees their own customers) | M |
| FR-CORE-018 | IP-based access restriction (optional, per company) | C |

### 2.3 Audit & Data Integrity
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-CORE-020 | Every record carries: UUID, Created/Updated/Deleted By, Created/Updated/Deleted At, Version, Tenant/Company/Branch ID | M |
| FR-CORE-021 | Deletion defaults to Soft Delete; no hard delete from the database via the normal UI | M |
| FR-CORE-022 | Audit Trail records every change to sensitive fields (old value, new value, who, when) | M |
| FR-CORE-023 | General Activity Log, filterable by user/screen/date | M |
| FR-CORE-024 | Optimistic locking via a Version field to prevent overwriting concurrent edits | M |

### 2.4 Internationalization (i18n) & Calendar
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-CORE-030 | All UI text is translatable (Arabic/English) via translation files, no hardcoded strings | M |
| FR-CORE-031 | Full RTL support when Arabic is selected, LTR for English, no layout breakage | M |
| FR-CORE-032 | Dates can be displayed/entered in Hijri or Gregorian per user preference, with unified storage (Gregorian/UTC) in the database | M |
| FR-CORE-033 | Numbers and currency are formatted per the selected language (thousand separators, symbol placement) | S |

### 2.5 Shared Master Data
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-CORE-040 | Company and branch management (CRUD) | M |
| FR-CORE-041 | User and role management | M |
| FR-CORE-042 | Unified contact record (Partner) usable as a customer and/or vendor on the same record | M |
| FR-CORE-043 | Currency and exchange rate management (manual entry in the nucleus, live integration later) | M |
| FR-CORE-044 | Unit of Measure (UoM) management and conversions | M |
| FR-CORE-045 | Basic Product Master (items/services) used across sales, purchasing, and inventory | M |

### 2.6 Cross-Cutting Concerns
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-CORE-050 | Attachments can be added to any main document (invoice, purchase order...) | M |
| FR-CORE-051 | In-app notifications for important events (approval needed, invoice due...) | M |
| FR-CORE-052 | Approval Workflow engine, single or multi-level, configurable by document type and amount | M |
| FR-CORE-053 | Global Search covering core documents at minimum (customers, vendors, invoices, items) | S |
| FR-CORE-054 | Every main list screen supports filtering, grouping, and Excel/PDF export | S |

---

## 3. FR-ACC — Core Accounting (M1)

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-ACC-001 | Hierarchical Chart of Accounts, customizable per company, with a ready-made Saudi default template | M |
| FR-ACC-002 | Manual and automatic Journal Entries (auto-generated from source documents like invoices) | M |
| FR-ACC-003 | No unbalanced entry can ever be saved (total debit = total credit) — enforced at the service layer before persistence | M |
| FR-ACC-004 | A Posted journal entry cannot be edited or deleted; corrections only via a Reversal entry | M |
| FR-ACC-005 | Multiple journals: Sales, Purchases, Bank, Cash, General | M |
| FR-ACC-006 | Cost Centers assignable to any journal entry line | S |
| FR-ACC-007 | Tax engine: multiple rates (15%, 0%, Exempt, Out of Scope), and Tax Groups for compound tax | M |
| FR-ACC-008 | Withholding Tax calculation on bills from specific vendors | S |
| FR-ACC-009 | Trial Balance report, filterable by period and branch | M |
| FR-ACC-010 | Basic Income Statement and Balance Sheet reports | M |
| FR-ACC-011 | Period Closing blocks any new entry dated within a closed period unless a special permission is held | S |

---

## 4. FR-SAL — Sales & E-Invoicing (M2)

### 4.1 Sales Cycle
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-SAL-001 | Create a Quotation linked to a customer, with items, prices, and taxes | M |
| FR-SAL-002 | Convert an approved quotation into a Sales Order | M |
| FR-SAL-003 | Create a Delivery from a sales order, which deducts inventory on confirmation | M |
| FR-SAL-004 | Issue a sales invoice from the delivery or directly from the sales order | M |
| FR-SAL-005 | Credit Note and Debit Note, both linked to an original invoice | M |
| FR-SAL-006 | Multiple Price Lists, linkable to a customer or customer category | S |
| FR-SAL-007 | Every stage transition (confirm, deliver, invoice) automatically creates the matching journal entry | M |

### 4.2 E-Invoicing (ZATCA)
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-ZATCA-001 | Distinguish invoice type: Tax (B2B/Standard) or Simplified (B2C), based on customer type | M |
| FR-ZATCA-002 | Generate the invoice as XML compliant with UBL 2.1 per ZATCA specifications | M |
| FR-ZATCA-003 | Generate a unique UUID per invoice and a strictly incrementing Invoice Counter Value (ICV) with no gaps | M |
| FR-ZATCA-004 | Hash Chain: each invoice carries the hash of the previous invoice | M |
| FR-ZATCA-005 | Cryptographic Stamp and digital signature using the device certificate (CSID) | M |
| FR-ZATCA-006 | Generate a QR Code (Base64-encoded TLV) containing the required fields (seller, VAT number, timestamp, total, VAT amount, hash) | M |
| FR-ZATCA-007 | Simplified invoices: stored locally and reported to ZATCA within 24 hours (Phase 2) | M |
| FR-ZATCA-008 | Tax invoices: sent for Clearance before being delivered to the customer (Phase 2), pending authority certification | M |
| FR-ZATCA-009 | Handle authority errors/rejections (error message displayed, invoice correctable and resubmittable) | M |
| FR-ZATCA-010 | Self-Billing invoice and Reverse Charge invoice for unregistered vendors | S |
| FR-ZATCA-011 | VAT Return report in the format required for authority submission | S |
| FR-ZATCA-012 | All ZATCA communication goes through an independent Adapter/Service, replaceable without affecting the rest of the system | M |

---

## 5. FR-INV — Inventory (M3)

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-INV-001 | Define hierarchical warehouses and storage locations (Warehouse → Location) | M |
| FR-INV-002 | Every item movement is recorded as a Stock Move (in/out/transfer) linked to a source document | M |
| FR-INV-003 | Transfer stock between warehouses/locations with tracked status (draft → in transit → done) | M |
| FR-INV-004 | Inventory valuation using one approved method per company: FIFO or Average Cost | M |
| FR-INV-005 | Every valuation movement creates a matching journal entry (inventory debit/credit per direction) | M |
| FR-INV-006 | Cycle counting: record discrepancies and post them as an approved inventory adjustment | S |
| FR-INV-007 | No item balance at any location can go negative unless a special Negative Stock Override permission is held | M |
| FR-INV-008 | Lot tracking, with optional serial number tracking at the item level | C |

---

## 6. FR-PUR — Purchasing (M4, Reduced Scope)

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-PUR-001 | Create a Purchase Order linked to a vendor, with items, prices, and taxes | M |
| FR-PUR-002 | Goods Receipt from a purchase order, increasing inventory on confirmation | M |
| FR-PUR-003 | Vendor Bill matched (3-Way Match) against the purchase order and receipt before approval | M |
| FR-PUR-004 | Debit Note to vendor on goods return | S |
| FR-PUR-005 | Every step creates the matching journal entry (liability accrual at receipt, payable at billing) | M |

---

## 7. FR-RPT — Reporting & Compliance (M5)

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-RPT-001 | Every main document screen supports professional-format PDF export | M |
| FR-RPT-002 | Every list screen supports Excel/CSV export | M |
| FR-RPT-003 | A basic dashboard shows: period sales, period purchases, receivables balance, upcoming due invoices | S |
| FR-RPT-004 | A filterable, exportable audit log report for compliance purposes | M |

---

## 8. Traceability Matrix (to Business Objectives)

| Business Objective (Phase 1) | Related Requirements |
|-------------------------------|------------------------|
| BO-1 ZATCA compliance | FR-ZATCA-001..012 |
| BO-2 Multi-company/branch | FR-CORE-001..004 |
| BO-3 Order-to-Cash | FR-SAL-001..007 |
| BO-4 Procure-to-Pay | FR-PUR-001..005 |
| BO-5 Accurate inventory tracking | FR-INV-001..008 |
| BO-6 Enterprise security | FR-CORE-010..024 |
| BO-7 Architectural scalability | Covered in Phase 8 (System Architecture) |

---

## 9. General Acceptance Criteria

- [ ] Project owner approves the requirements list and priorities (M/S/C), or requests specific changes.
- [ ] Any unclear Must-priority requirement is clarified before moving to the next phase.

---

*End of Phase 2. Awaiting approval to proceed to Phase 3: Non-Functional Requirements.*
