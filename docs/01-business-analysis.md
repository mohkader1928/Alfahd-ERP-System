# Phase 1 — Business Analysis

**Project:** Enterprise Resource Planning (ERP) System — Kingdom of Saudi Arabia Market
**Status:** Draft for approval
**Version:** 0.1

---

## 1. Executive Summary

The goal is to build a production-ready ERP system for companies operating in Saudi Arabia, using a Modular Monolith architecture that can evolve into microservices later, fully compliant with ZATCA (Zakat, Tax and Customs Authority) e-invoicing requirements, and supporting multi-company, multi-branch, multi-currency, and multi-language operation.

Given the enormous scope of the full project (20+ business modules), it was agreed with the project owner to use an **incremental Milestone-based strategy**: start with a production-quality **Core Nucleus**, then add the remaining modules (CRM, POS, Manufacturing, Construction, HR, Projects, Fixed Assets, Maintenance, Help Desk, DMS, E-Commerce, advanced BI/AI...) each as an independent sub-project **without modifying the nucleus**.

This document defines the scope of the **Core Nucleus (Milestones 0–5)** only. Other modules are documented as a future backlog in Section 8.

---

## 2. Problem & Opportunity

Saudi companies (especially SMEs) face:

- High licensing costs for systems like SAP B1 / Dynamics 365, with limited customization.
- Locally-built systems that don't fully comply with ZATCA Phase 2 (Integration/Clearance) requirements.
- Difficulty scaling (multi-branch, multi-currency) in traditional accounting systems.
- Lack of a modern user experience (Kanban, Smart Buttons, Global Search) compared to Odoo.

Opportunity: a system that combines **full local compliance (ZATCA)** with a **modern UX** and a **scalable architecture**, without the commercial constraints of SAP/Dynamics.

---

## 3. Business Objectives

| # | Objective | Success Metric |
|---|-----------|-----------------|
| BO-1 | Full ZATCA e-invoicing compliance (Phase 1 + Phase 2) | Pass ZATCA Integration Sandbox simulation with zero errors |
| BO-2 | Multi-company/multi-branch support from day one | Create two companies + 3 branches and run isolated transactions with zero data leakage |
| BO-3 | Complete, auditable Order-to-Cash cycle | Quotation → Sales Order → Delivery → Invoice → automatic balanced journal entry |
| BO-4 | Basic Procure-to-Pay cycle | Purchase Order → Receipt → Vendor Bill → journal entry |
| BO-5 | Accurate inventory tracking with an approved valuation method | Stock report matches the journal entry (FIFO or Average) |
| BO-6 | Enterprise-grade security | RBAC + 2FA + full audit trail on every CRUD operation |
| BO-7 | Architectural scalability readiness | Every module can be split into an independent service without restructuring the database |

---

## 4. Stakeholders

| Role | Primary Interest |
|------|-------------------|
| Project Owner / Senior Management | Tax compliance, accurate financial reporting, access control |
| Accountant / CFO | Journal accuracy, tax invoices, VAT returns |
| Sales Manager | Full sales cycle, price lists, order tracking |
| Inventory/Warehouse Manager | Stock accuracy, transfers, cycle counts |
| IT Administrator | Permissions, audit log, backups, performance |
| Development team (later phases) | Clean, maintainable, scalable architecture |
| ZATCA (external compliance party) | E-invoice validity and integration with the Fatoora platform |

---

## 5. Core Nucleus Scope

The nucleus is split into independent Milestones, each testable before moving to the next:

### M0 — Architectural Foundation
- Multi-Tenant/Company/Branch structure (Tenant ID, Company ID, Branch ID on every record).
- Authentication: JWT + OAuth2 + 2FA + Session Management.
- RBAC: Permission Matrix (Screen / Field / Record Rules).
- A unified framework for every table: UUID, Created/Updated/Deleted By & At, Soft Delete, Version.
- Audit Trail + Activity Log.
- Bilingual support (Arabic/English) + RTL/LTR + Hijri/Gregorian calendar.
- Shared master data: companies, branches, users, currencies, units of measure, contacts (unified Customer/Vendor Partner).

### M1 — Core Accounting
- Company-customizable, hierarchical Chart of Accounts.
- Journal Entries and General Ledger.
- Basic Cost Centers.
- VAT: 15%, 0%, Exempt, Out of Scope, compound Tax Groups.
- Basic financial statements: Trial Balance, Income Statement, Balance Sheet.

### M2 — Sales + ZATCA E-Invoicing
- Quotation → Sales Order → Delivery → Invoice → Credit/Debit Note.
- Tax invoice (B2B) and simplified invoice (B2C).
- QR Code, UUID, Cryptographic Stamp, Hash Chain, XML (UBL 2.1).
- ZATCA Phase 1 (Generation) and Phase 2 (Integration/Clearance/Reporting) integration, sandbox first.

### M3 — Inventory
- Warehouses and storage locations.
- Stock moves and internal transfers.
- Inventory valuation: FIFO or Average Cost (architectural decision to be finalized in the design phase).
- Basic cycle counting.

### M4 — Purchasing (Reduced Scope)
- Request for Quotation (RFQ) → Purchase Order (PO) → Receipt → Vendor Bill.
- Debit note to vendor.
- Reverse Charge for unregistered vendors (a ZATCA/VAT requirement).

### M5 — Basic Reporting & Compliance
- PDF/Excel export for every main document screen.
- Filterable, exportable audit log.
- Basic dashboard (KPIs: sales, purchases, receivables, upcoming due invoices).

> **Nucleus Definition of Done:** A Saudi company can register a company and branch, create a customer and vendor, run a full sales cycle with a valid ZATCA invoice, run a basic purchase cycle, and have the inventory report match the accounting entry — with effective RBAC and a complete audit log.

---

## 6. Explicitly Out of Scope for the Nucleus

These modules are documented as a Backlog (Section 8) and will only be built after the nucleus is approved, each as an independent sub-project:

CRM, POS (Retail/Restaurant), Manufacturing (BOM/MRP), Construction/BOQ, Human Resources & Payroll, Projects & Timesheets, Fixed Assets, Maintenance (CMMS), Help Desk, DMS/OCR, E-Commerce, advanced BI (Drill Down/Pivot), AI (Chat/Voice/Forecast/Fraud Detection), extended external integrations (WhatsApp/Email/SMS/Power BI/S3...), GraphQL API (nucleus starts REST-only), Celery/RabbitMQ (added only when a real need for heavy background jobs arises).

---

## 7. Assumptions & Constraints

- SAR is the default currency, with structural multi-currency support from M0, but live exchange-rate integration is deferred.
- Real integration with the ZATCA API requires a genuine CSID certificate from the authority; it will be built and tested first against the Sandbox environment — moving to production requires an action from the system owner outside the scope of the code (device/certificate onboarding with ZATCA).
- Single database (PostgreSQL) for the entire nucleus — no actual microservices at this stage, only clean module boundaries that allow future separation.
- The nucleus frontend covers only the core screens for in-scope modules (no screens built for out-of-scope modules).
- No fixed delivery deadline is committed; execution proceeds milestone by milestone with project-owner approval after each phase.

---

## 8. Future Backlog (post-nucleus approval)

Will be re-prioritized based on actual need when reached:

1. CRM (Leads/Opportunities/Pipeline)
2. POS (Retail/Restaurant + Offline Mode)
3. Manufacturing (BOM/MRP/Work Orders)
4. Construction (BOQ/Site Management/Progress Billing)
5. Human Resources (Attendance/Payroll/Recruitment)
6. Projects (Tasks/Timesheets/Billing)
7. Fixed Assets (Register/Depreciation/Disposal)
8. Maintenance (Preventive/Corrective)
9. Help Desk (Tickets/SLA/Knowledge Base)
10. DMS (Documents/OCR/Versioning)
11. E-Commerce
12. Advanced BI + AI
13. Extended external integrations (Microsoft 365, Google Workspace, Power BI...)

---

## 9. Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| ZATCA technical requirements change during development | Medium | High | Isolate ZATCA logic in an independent layer/service (Adapter Pattern) |
| Scope creep — adding modules before the nucleus is complete | High | High | Strict adherence to the nucleus boundaries defined in this document |
| Complexity of Saudi accounting rules (Withholding Tax, Retention) | Medium | Medium | Design a flexible chart of accounts and tax engine from the start (Tax Groups) |
| No real ZATCA certificate available for full testing | High | Medium | Rely on ZATCA Sandbox + Fatoora Simulation Portal |

---

## 10. General Acceptance Criteria for This Phase

- [ ] Project owner approves the nucleus scope (M0–M5) as-is, or requests specific changes.
- [ ] Work does not proceed to Phase 2 (Functional Requirements) until this approval is given.

---

*End of Phase 1. Awaiting approval to proceed to Phase 2: Functional Requirements.*
