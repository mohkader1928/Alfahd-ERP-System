# Phase 4 — Use Cases

**Status:** Draft for approval | **Version:** 0.1
**Builds on:** [02-functional-requirements.md](02-functional-requirements.md), [03-non-functional-requirements.md](03-non-functional-requirements.md)

---

## 1. Actors

| Actor | Description |
|-------|--------------|
| **System Admin** | Configures companies, branches, roles, and global settings. Full technical access. |
| **Company Admin** | Manages users, permissions, and master data within their company. |
| **Accountant / CFO** | Manages chart of accounts, journal entries, financial closing, VAT returns. |
| **Sales Manager / Sales Rep** | Runs the quotation-to-invoice cycle, manages price lists and customers. |
| **Warehouse Clerk** | Executes stock transfers, receipts, deliveries, and cycle counts. |
| **Purchasing Officer** | Runs the RFQ-to-bill cycle, manages vendors. |
| **Approver** | Any role granted approval authority in the Approval Workflow engine (can be Accountant, Company Admin, etc., depending on configuration). |
| **ZATCA Platform** *(external system actor)* | Receives invoice submissions (Clearance/Reporting), returns acceptance/rejection and cryptographic responses. |

---

## 2. UC-CORE — Foundation

### UC-CORE-01 — User Login with 2FA
- **Actor:** Any system user
- **Preconditions:** User account exists and is active; belongs to at least one Company/Branch.
- **Main Flow:**
  1. User submits email/username + password.
  2. System validates credentials against the stored hash.
  3. If 2FA is enabled (per user or enforced per company), system prompts for TOTP code.
  4. User submits valid TOTP code.
  5. System issues JWT access + refresh tokens scoped to the user's authorized companies/branches.
- **Alternate Flows:**
  - 2a. Invalid credentials → generic error (no indication of which field is wrong); failed attempt logged; rate-limited per NFR-SEC-006.
  - 4a. Invalid/expired TOTP → access denied, attempt logged.
- **Postconditions:** Active session created; login event recorded in Activity Log.
- **Related:** FR-CORE-010, FR-CORE-011, NFR-SEC-006

### UC-CORE-02 — Register Company & Branch
- **Actor:** System Admin
- **Preconditions:** Actor holds System Admin privileges.
- **Main Flow:**
  1. Admin creates a new Company record (legal name, VAT number, default currency, Saudi CoA template selection).
  2. Admin creates one or more Branches under the company.
  3. System initializes default master data scoped to the company (default journals, default warehouse).
- **Postconditions:** Company/Branch available for user assignment and transactions.
- **Related:** FR-CORE-001, FR-CORE-002, FR-CORE-040

### UC-CORE-03 — Assign Role & Permissions
- **Actor:** Company Admin
- **Preconditions:** Target user exists; acting admin has permission-management rights.
- **Main Flow:**
  1. Admin selects a user and a Company/Branch scope.
  2. Admin assigns one or more Roles (each a bundle of screen/field/record permissions).
  3. System applies Record Rules (e.g., restrict a Sales Rep role to only their own customers).
- **Postconditions:** User's effective permissions updated immediately for future requests.
- **Related:** FR-CORE-014..017

### UC-CORE-04 — Review Audit Trail
- **Actor:** System Admin / Company Admin (with permission)
- **Preconditions:** Actor holds audit-log view permission.
- **Main Flow:**
  1. Actor opens the Audit Trail screen, filters by user/date/document type.
  2. System displays before/after values for each change.
- **Postconditions:** None (read-only).
- **Related:** FR-CORE-022, FR-RPT-004

### UC-CORE-05 — Approve or Reject a Document
- **Actor:** Approver
- **Preconditions:** A document (e.g., Purchase Order, Journal Entry) is in "Pending Approval" status per a configured Approval Workflow rule (e.g., PO amount exceeds threshold).
- **Main Flow:**
  1. Approver receives an in-app notification.
  2. Approver opens the document, reviews details.
  3. Approver approves → document moves to the next state (e.g., "Confirmed") or the next approval level if multi-level.
- **Alternate Flows:**
  - 3a. Approver rejects with a mandatory comment → document returns to "Draft"; originator notified.
- **Postconditions:** Document state transition recorded in Audit Trail.
- **Related:** FR-CORE-052, FR-CORE-051

---

## 3. UC-ACC — Accounting

### UC-ACC-01 — Create and Post a Manual Journal Entry
- **Actor:** Accountant
- **Preconditions:** Chart of Accounts exists for the company; accounting period is open.
- **Main Flow:**
  1. Accountant creates a journal entry with two or more lines (accounts, debit/credit amounts, optional cost center).
  2. System validates total debit = total credit (FR-ACC-003).
  3. Accountant posts the entry.
  4. System locks the entry against edits; only a reversal is possible thereafter.
- **Alternate Flows:**
  - 2a. Unbalanced entry → save rejected with a clear error.
  - 1a. Period is closed → entry creation blocked unless actor holds override permission (FR-ACC-011).
- **Postconditions:** General Ledger updated; entry appears in Trial Balance.
- **Related:** FR-ACC-002..004

### UC-ACC-02 — Generate Trial Balance
- **Actor:** Accountant / CFO
- **Preconditions:** At least one posted journal entry exists in the selected period.
- **Main Flow:**
  1. Actor selects company, branch (optional), and date range.
  2. System aggregates posted entries per account.
  3. Report is displayed and exportable to PDF/Excel.
- **Postconditions:** None (read-only).
- **Related:** FR-ACC-009, FR-RPT-001, FR-RPT-002

---

## 4. UC-SAL — Sales & E-Invoicing

### UC-SAL-01 — Quotation to Sales Order
- **Actor:** Sales Rep
- **Preconditions:** Customer (Partner) and at least one Product exist.
- **Main Flow:**
  1. Sales Rep creates a Quotation with line items, quantities, and prices (from an applicable Price List).
  2. System calculates line/tax/total amounts.
  3. Customer approves (offline); Sales Rep confirms the Quotation, converting it to a Sales Order.
- **Postconditions:** Sales Order in "Confirmed" state, ready for delivery.
- **Related:** FR-SAL-001, FR-SAL-002, FR-SAL-006

### UC-SAL-02 — Deliver Goods
- **Actor:** Warehouse Clerk
- **Preconditions:** Sales Order confirmed; sufficient stock available (or Negative Stock Override held).
- **Main Flow:**
  1. Clerk opens the Delivery generated from the Sales Order.
  2. Clerk confirms picked quantities.
  3. System deducts stock via a Stock Move and computes cost of goods issued (FIFO/Average).
- **Alternate Flows:**
  - 3a. Insufficient stock and no override → delivery blocked.
- **Postconditions:** Inventory reduced; delivery marked "Done"; ready for invoicing.
- **Related:** FR-SAL-003, FR-INV-002, FR-INV-007

### UC-SAL-03 — Issue a Tax Invoice with ZATCA Clearance
- **Actor:** Sales Rep / Accountant; **external actor:** ZATCA Platform
- **Preconditions:** Delivery (or Sales Order) confirmed; customer classified as B2B (VAT-registered) → Standard/Tax invoice path.
- **Main Flow:**
  1. Actor issues the invoice from the delivery/order.
  2. System generates the invoice, assigns UUID + sequential ICV, computes hash against the previous invoice (Hash Chain).
  3. System generates UBL 2.1 XML and applies the Cryptographic Stamp using the device certificate.
  4. System submits the invoice to ZATCA for **Clearance** and waits for a synchronous response.
  5. ZATCA returns a cleared, stamped invoice.
  6. System embeds the returned QR code/stamp and marks the invoice "Cleared"; only then is it shared with the customer.
  7. System generates the matching journal entry (FR-SAL-007).
- **Alternate Flows:**
  - 4a. ZATCA rejects (validation error) → invoice returns to "Draft" with the authority's error message; correctable and resubmittable (FR-ZATCA-009).
  - 4b. ZATCA endpoint unreachable/timeout → invoice saved as "Pending Submission" and retried automatically (NFR-AVAIL-003); not blocking business flow but not yet legally valid until cleared.
- **Postconditions:** Legally valid tax invoice issued; audit trail and hash chain updated.
- **Related:** FR-ZATCA-001..009, FR-SAL-004, FR-SAL-007

### UC-SAL-04 — Issue a Simplified Invoice with ZATCA Reporting
- **Actor:** Sales Rep; **external actor:** ZATCA Platform
- **Preconditions:** Customer classified as B2C (or VAT-unregistered) → Simplified invoice path.
- **Main Flow:**
  1. Actor issues the simplified invoice; system generates it locally (UUID, ICV, hash chain, QR code, stamp) and delivers it to the customer immediately (no synchronous clearance required).
  2. System queues the invoice for asynchronous **Reporting** to ZATCA.
  3. Background job reports the invoice to ZATCA within the 24-hour compliance window (FR-ZATCA-007).
- **Alternate Flows:**
  - 3a. ZATCA reports back a post-hoc rejection → flagged for accountant review; does not retroactively invalidate the already-issued invoice, but must be resolved (e.g., via correction/credit note) per ZATCA guidance.
- **Postconditions:** Simplified invoice delivered to customer at point of sale; compliance reporting completed within SLA.
- **Related:** FR-ZATCA-001, FR-ZATCA-006, FR-ZATCA-007

### UC-SAL-05 — Issue a Credit Note
- **Actor:** Accountant / Sales Rep
- **Preconditions:** Original cleared/reported invoice exists.
- **Main Flow:**
  1. Actor creates a Credit Note referencing the original invoice, with reason and adjusted lines.
  2. System applies the same ZATCA generation/submission flow as the original invoice type (Clearance or Reporting).
  3. System generates the reversing journal entry.
- **Postconditions:** Customer balance and inventory (if returned) adjusted; ZATCA-compliant credit note issued.
- **Related:** FR-SAL-005, FR-ZATCA-001..009

---

## 5. UC-INV — Inventory

### UC-INV-01 — Transfer Stock Between Warehouses
- **Actor:** Warehouse Clerk
- **Preconditions:** Source location has sufficient stock (or override held).
- **Main Flow:**
  1. Clerk creates a transfer (source location → destination location), specifying items/quantities.
  2. Clerk confirms; transfer moves to "In Transit".
  3. Receiving clerk confirms receipt at destination; transfer moves to "Done".
- **Postconditions:** Stock moved between locations; two Stock Moves recorded (out/in), no valuation change (internal transfer).
- **Related:** FR-INV-001..003

### UC-INV-02 — Cycle Count / Inventory Adjustment
- **Actor:** Warehouse Clerk; **Approver:** Warehouse Manager
- **Preconditions:** A cycle count session is scheduled for a location.
- **Main Flow:**
  1. Clerk counts physical quantities and enters them against system quantities.
  2. System calculates discrepancies.
  3. Manager approves the adjustment.
  4. System posts a Stock Move for the discrepancy and the matching journal entry (valuation impact).
- **Postconditions:** Stock and accounting records reconciled.
- **Related:** FR-INV-006, FR-INV-005

---

## 6. UC-PUR — Purchasing

### UC-PUR-01 — Purchase Order to Vendor Bill (3-Way Match)
- **Actor:** Purchasing Officer; **Approver:** per approval workflow if PO exceeds threshold
- **Preconditions:** Vendor (Partner) and Product exist.
- **Main Flow:**
  1. Officer creates a Purchase Order with items, quantities, prices.
  2. If PO amount exceeds the configured threshold, it routes through UC-CORE-05 (Approve/Reject).
  3. Officer confirms the PO; system generates a liability accrual on Goods Receipt.
  4. Warehouse Clerk records the Goods Receipt against the PO; stock increases.
  5. Officer (or Accountant) registers the Vendor Bill; system performs 3-Way Match (PO ↔ Receipt ↔ Bill quantities/prices).
  6. On match, Bill is approved and posted; on mismatch, flagged for manual review.
- **Postconditions:** Vendor payable recorded; inventory increased at matched cost.
- **Related:** FR-PUR-001..005, FR-CORE-052

---

## 7. UC-RPT — Reporting

### UC-RPT-01 — Export a Report
- **Actor:** Any user with screen access
- **Preconditions:** User has view permission on the underlying data.
- **Main Flow:**
  1. User applies filters/grouping on a list or report screen.
  2. User selects Export (PDF or Excel/CSV).
  3. For datasets above the threshold (NFR-PERF-005), export runs as a background job and the user is notified when ready.
- **Postconditions:** File available for download, respecting the same row-level permissions as the screen.
- **Related:** FR-RPT-001, FR-RPT-002, NFR-PERF-005

---

## 8. Traceability Summary

Every use case above references its governing FR/NFR IDs inline. No use case introduces a requirement not already captured in Phase 2 or Phase 3 — if a gap is found during review, Phase 2/3 should be amended rather than letting an ungoverned use case stand.

---

## 9. General Acceptance Criteria

- [ ] Project owner confirms these use cases accurately represent the intended user workflows, or requests specific changes.
- [ ] Any missing critical workflow is identified before moving to Phase 5 (Business Flow), where these use cases are sequenced into end-to-end diagrams.

---

*End of Phase 4. Proceeding to Phase 5: Business Flow.*
