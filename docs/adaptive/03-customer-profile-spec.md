# 03 — Customer Profile Specification

Answers: **"Who is this company?"** — captured once at onboarding, revisited at every Growth Review (see [`09-sales-and-onboarding-flow.md`](09-sales-and-onboarding-flow.md)). Feeds the [Sizing Engine](04-erp-sizing-engine-spec.md) to produce an [ERP Blueprint](05-erp-blueprint-spec.md).

**Legend** used throughout: **EXISTING** = a real field on the Golden Core today (cited); **NEW** = genuinely new data this Stage adds; **FUTURE CAPABILITY** = the profile can ask about it, but the ERP Core has no feature behind it yet — asking now is fine (it feeds Growth Blueprint intent), building it is not in scope until the corresponding module exists.

Every item below is included because it maps to a concrete decision the Sizing Engine or Blueprint makes — see the "Drives" column. Nothing is here "because a typical ERP profile has it."

## A. Company Identity

| Field | Status | Drives |
|---|---|---|
| Legal name (en/ar) | EXISTING (`Company.legal_name`/`_ar`) | Blueprint document headers, print templates |
| VAT number (15-digit) | EXISTING (`Company.vat_number`) | Tax configuration validity |
| CR number | EXISTING (`Company.cr_number`, not set at bootstrap today) | Compliance record only |
| Industry/activity | NEW | Which role-template set and CoA starting structure get recommended (§04 dimension "Industry Complexity") |
| Legal form (est./LLC/etc.) | NEW | Informational; may affect recommended CoA equity structure later |
| Primary location (city/region) | NEW | No functional effect today (single timezone/locale) — recorded for Growth Blueprint, not sizing |
| GCC/Saudi-specific considerations (e.g., is this a branch of a foreign entity, Zakat vs. income tax status) | NEW | Informational only today — the Core has no Zakat-specific logic; flagged FUTURE CAPABILITY if that ever changes |

## B. Organization

| Field | Status | Drives |
|---|---|---|
| Number of employees (today) | NEW | Sizing dimension "Organizational Complexity" |
| Number of branches (today / planned) | NEW | Whether Branch management UI needs to be built before this customer's Blueprint can be provisioned — see gap in [`02-current-state-assessment.md`](02-current-state-assessment.md) §2.3 |
| Number of cost centers needed | NEW | Whether `CostCenter` CRUD (currently missing — see gap analysis) must exist before provisioning |
| Departments | FUTURE CAPABILITY — no `Department` entity exists at all today. Ask, don't build yet. |

## C. Operations

| Field | Status | Drives |
|---|---|---|
| Sells physical goods / services / both | NEW (Core has no `is_service` flag — closest proxy is `Product.is_stockable`) | Whether Inventory module is enabled in the Blueprint at all |
| Number of warehouses (today / planned) | NEW | Sizing dimension "Inventory Complexity"; `Warehouse` CRUD already exists (EXISTING) |
| Stock valuation approach | EXISTING (`Company.valuation_method`: fifo/average) | Direct Blueprint field, no translation needed |
| Approximate monthly sales order volume | NEW | Sizing dimension "Transaction Volume" |
| Approximate monthly purchase order volume | NEW | Sizing dimension "Transaction Volume" |
| Number of active SKUs (rough) | NEW | Informational — no current feature gates on catalog size |

## D. Finance

| Field | Status | Drives |
|---|---|---|
| Fiscal year start month | EXISTING (`Company.fiscal_year_start_month`) | Direct Blueprint field |
| Chart of Accounts complexity (flat vs. multi-level) | NEW, but the Core already supports up to 4 levels (`Account.level`) | Whether the Blueprint recommends starting flat or pre-seeding a deeper structure |
| Cost center tracking needed | NEW | See B above |
| Payment methods used (cash/bank/card/cheque) | NEW | Informational — `Payment` already supports arbitrary methods as data, no gating needed |
| Receivables/payables complexity (single vs. aging-managed) | NEW | AR/AP aging reports already exist (EXISTING) — this decides whether they're surfaced prominently in the Blueprint's reporting package |
| Multi-currency need | NEW — **must be answered honestly against a real gap**: the Core has no functioning multi-currency (no exchange rate, no per-document currency selection — see [`02-current-state-assessment.md`](02-current-state-assessment.md) §2.4). If a customer says yes, this is FUTURE CAPABILITY, not something the Blueprint can turn on today. |

## E. Tax

| Field | Status | Drives |
|---|---|---|
| VAT registration status | EXISTING (`Company.vat_number`) | |
| Applicable tax rates (standard/zero-rated/exempt) | EXISTING (`TaxRate`/`TaxGroup`, already company-scoped and data-driven — P0-1) | Which `TaxRate` rows get seeded for this company |
| Withholding tax needs | EXISTING (`TaxRate.is_withholding` flag already in schema) | |
| ZATCA e-invoicing phase/environment | EXISTING (`Company.zatca_environment`: sandbox/simulation/production — not set at bootstrap today) | Direct Blueprint field. **Do not claim ZATCA certification beyond what's actually implemented** — see [`08-ai-opportunities.md`](08-ai-opportunities.md) and the existing marketing material's own honesty rule. |

## F. Assets

| Field | Status | Drives |
|---|---|---|
| Owns fixed assets requiring depreciation tracking | EXISTING module (Fixed Assets: categories, depreciation, disposal, asset card, GL reconciliation) | Whether Fixed Assets module is enabled in the Blueprint |
| Approximate asset count | NEW | Informational |

## G. Growth (the "Growth Blueprint" input — see [`07-editions-and-growth-model.md`](07-editions-and-growth-model.md))

| Field | Status | Drives |
|---|---|---|
| Expected branches in 1 / 3 years | NEW | Growth Blueprint, not current Configuration |
| Expected warehouses in 1 / 3 years | NEW | Growth Blueprint |
| Expected employees/users in 1 / 3 years | NEW | Growth Blueprint |
| Expected transaction volume growth | NEW | Growth Blueprint — informs whether performance-relevant defaults (indexing, reporting scope) should be set ahead of need |
| Planned expansion into new business lines | NEW | Feeds §J Future Needs, not current Blueprint |

## H. Management Visibility

| Field | Status | Drives |
|---|---|---|
| Required reports (which of the existing report set matters to this customer) | NEW selection over an EXISTING catalog (Trial Balance, Income Statement, Balance Sheet, General Ledger, VAT Summary, AR/AP Aging/Subledgers, Sales/Purchasing reports — all real today) | Which reports the Blueprint's "reporting package" surfaces prominently in nav |
| Dashboard KPI priorities | NEW selection over an EXISTING dashboard (`DashboardService.get_summary()` already returns sales/purchases/AR/AP/cash/trend/pending-approvals/recent-activity — see [`02-current-state-assessment.md`](02-current-state-assessment.md) §2.6) | Cosmetic ordering only — the dashboard's actual data isn't customer-configurable today |
| Approval complexity needed | NEW, against a **real gap**: only PO-threshold approval exists today (`Company.po_approval_threshold`). Sales-order, vendor-bill, and journal-entry approval chains are FUTURE CAPABILITY. |

## I. Security

| Field | Status | Drives |
|---|---|---|
| Number of system users (today / planned) | NEW | Sizing dimension |
| Role separation needs (do they want the 4 seeded templates as-is, or custom roles) | NEW selection over EXISTING (`Accountant`, `Sales`, `Purchasing & Warehouse`, `Read-Only Viewer`, system `Admin`) | Which roles get provisioned for the first admin to hand out |
| 2FA requirement | EXISTING (TOTP 2FA already implemented, opt-in per user today) | Whether the Blueprint recommends/enforces 2FA for admin roles |

## J. Future Needs (explicitly not current-Core features — recorded for product-roadmap signal only, never claimed as available)

- API/integration access (no public partner API exists today beyond the internal REST API)
- E-commerce connection
- Payroll (no HR/payroll module exists)
- Manufacturing (no BOM/production module exists)
- CRM (no lead/opportunity tracking exists — Partner is master data only)

These are asked about **so the business can prioritize its real roadmap from real demand signal**, not because Adaptive ERP Stage 1 is promising any of them. See [`11-adaptive-roadmap.md`](11-adaptive-roadmap.md) for where, if ever, these might appear.

## Data model implication (design only — see [`06-configuration-engine-architecture.md`](06-configuration-engine-architecture.md) for the actual entity proposal)

The Customer Profile is **not** a set of new columns bolted onto `Company`. `Company` is used in every RLS policy and every auth path in the Golden Core — the profile belongs in a separate, company-linked table (`company_profile`, 1:1 with `company.id`) precisely so this entire initiative can be additive and never touch the high-traffic `company` table's shape. This is elaborated in §06.
