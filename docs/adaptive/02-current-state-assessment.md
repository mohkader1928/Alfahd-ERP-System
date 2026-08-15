# 02 — Current State Assessment

Golden Baseline: `phase-one-v1.0.0` → `6b6403cb4b4d75e1f53a5d86ff17e574cd37c881`. Everything below is grounded in direct repository inspection (file paths, class names, field names cited), not assumption. Where the current system has no answer to something Adaptive ERP needs, that's recorded here as a gap and carried forward into [`10-adaptive-gap-analysis.md`](10-adaptive-gap-analysis.md), not silently assumed away.

## 2.1 Architecture shape

Modular monolith. Clean Architecture layering (`domain/application/infrastructure/api`) repeats *inside each module* under `backend/src/modules/<name>/`, not as one global layering — `backend/src/shared/` is the cross-cutting kernel (config, DB session, security, i18n, media, messaging). One-way dependency rule: domain never imports infrastructure. 11 modules are registered in `backend/src/api/main.py`'s `ENABLED_MODULES` list: `identity, attachments, notifications, accounting, fixed_assets, inventory, sales, purchasing, payments, reporting`. `zatca` is the 11th — internal only, no own API router, invoked from `sales`.

Multi-tenancy: every company-scoped table mixes in `TenantScopedMixin` (`backend/src/shared/infrastructure/db/base.py`) — `tenant_id`, `company_id`, `branch_id` (nullable), audit columns, optimistic-lock `version`. Enforced twice ("belt and suspenders"): application-level `company_id` filters in repositories, *and* real PostgreSQL Row-Level Security (`CREATE POLICY ... FORCE ROW LEVEL SECURITY`), with the session variables (`app.current_tenant_id`, `app.current_company_id`) set once per request in `get_auth_context()` (`backend/src/shared/security/auth_context.py`) from the validated JWT + `X-Company-Id`/`X-Branch-Id` headers. 42 dedicated tests prove this (`tests/test_multi_tenancy_isolation.py`: 18, `tests/test_rls_enforcement.py`: 24).

Authorization: one dependency, `require_permission(code, require_branch=bool)` (`backend/src/modules/identity/api/deps.py`), used 156 times across every module's routes. Permission catalog: 79 entries (`PERMISSION_CATALOG` in `backend/src/shared/infrastructure/db/seed.py`), `screen`/`action`/`field` scoped (only `screen`/`action` actually seeded today — field-level and record rules are documented as "configured per-role at runtime," not built).

Audit: `AuditLogRepository.record()` (`backend/src/modules/identity/infrastructure/repositories.py`) — a manual, explicit call per write, used in 5 modules (`identity`, `sales`, `purchasing`, `accounting`, `fixed_assets`). Not framework-enforced; a new write path that forgets to call it produces no audit trail and no error.

Testing/CI/Recovery: 466 tests (`backend/tests/`), all currently green, verified on a from-scratch empty database as of Stage 0 Closure. CI (`.github/workflows/ci.yml`) runs backend tests + ruff + frontend tsc + eslint on every push to `main`, currently green. Backup/restore (`infra/backup/backup_db.sh`, `restore_db.sh`, `copy_offhost.sh`) and a disaster-recovery runbook (`docs/21-disaster-recovery-and-rollback.md`) exist and were proven end-to-end in Stage 0 (real backup, real restore into an isolated environment, full regression passed against the restored copy). None of this existed before Stage 0 — it's the foundation Adaptive ERP work stands on.

## 2.2 The `Company` entity — today's only real "profile"

`backend/src/modules/identity/infrastructure/models.py`, table `company`:

| Field | Configurable today? | Set at bootstrap? |
|---|---|---|
| `legal_name` / `legal_name_ar` | yes, editable via `/settings/company` | yes (required) |
| `vat_number` (exactly 15 digits) | yes | yes (required) |
| `base_currency_id` | yes (via `base_currency_code` at bootstrap) | yes (default `SAR`) |
| `valuation_method` (`fifo`\|`average`) | yes | yes (default `average`) |
| `zatca_environment` (`sandbox`\|`simulation`\|`production`) | yes | **no** — not set at bootstrap, defaults and is presumably changed later |
| `cr_number` | yes | **no** |
| `logo_path` | yes (upload) | **no** |
| `po_approval_threshold` | yes, nullable | **no** |
| `fiscal_year_start_month` (1–12) | yes | **no** (defaults to 1) |

This is the system's only per-company "profile" today, and it is narrow: compliance/accounting basics only. Nothing about company size, industry, organizational structure, or growth intent exists anywhere. This is the entire reason [`03-customer-profile-spec.md`](03-customer-profile-spec.md) needs to be designed, not assumed to already exist in some form.

## 2.3 Organizational structure — schema-ready, UI-absent

| Entity | Schema | Reality |
|---|---|---|
| `Branch` | `id, tenant_id, company_id, name, name_ar, is_main, address (JSONB), timestamps` | Backend fully supports multiple branches per company (auth context carries `branch_id`, sales/purchasing documents require `branch_id`). **No update/delete API** (only `POST`/`GET /companies/{id}/branches`). **Zero frontend UI** to manage branches. Bootstrap creates exactly one ("Main Branch"). In practice: every company today runs on one branch. |
| `Warehouse` | `id, company_id, branch_id (required), name, is_default` — no `name_ar` | Real CRUD exists, gated by `require_permission("inventory.warehouse.manage", require_branch=True)`. Functional multi-warehouse. |
| `Location` | `id, company_id, warehouse_id, parent_id (self-referencing), name, is_virtual` | Genuine hierarchy (bins/zones nestable) but no "location type" — just a name and a virtual flag. |
| `CostCenter` | `id, company_id, name` — nothing else | Wired into `journal_entry_line.cost_center_id` (optional dimension on journal lines) but **no dedicated CRUD API or UI at all** — populate-able only via direct DB/seed. A real but incomplete feature. |
| Department | **Does not exist.** No table, no concept, anywhere. |
| Employee | **Not a separate entity.** `Partner.is_employee: bool` + `Partner.job_title`, nothing else (no payroll, no department assignment, no reporting line). The `/master-data/employees` frontend page is a filtered view over the same Partner list UI used for customers/vendors. |

## 2.4 What's genuinely configurable today vs. hardcoded

| Area | State |
|---|---|
| Tax rates (`TaxRate`/`TaxGroup`) | Fully data-driven, per-company. Fixed in P0-1 (previously hardcoded 15%). |
| Fiscal periods | Fully data-driven, per-company (`FiscalPeriod`, create/close via API). |
| Chart of Accounts | Data-driven, 4-level hierarchy enforced (`Account.level`/`account_group`). |
| Roles/permissions | Data-driven per company. 4 seeded templates (Accountant, Sales, "Purchasing & Warehouse", Read-Only Viewer — the last auto-derived from all `screen`-scope catalog codes) + one system "Admin" role holding the entire 79-entry catalog. `seed_default_role_templates()` in `backend/src/modules/identity/application/services.py`. Non-Admin roles are freely editable/deletable by the customer. |
| Module enable/disable | **Global, code-level only** — `ENABLED_MODULES` in `main.py`, one list for the whole deployment. **No per-company module toggle exists.** This is the single biggest gap for Adaptive ERP (see §2.7 and the gap analysis). |
| Approval workflow | **Exactly one gate exists**: `Company.po_approval_threshold` on Purchase Orders only. Nothing analogous for vendor bills, sales orders, or journal entries. No generic/configurable approval-chain concept. |
| Multi-currency | **Schema placeholder only.** Every transaction table carries `currency_code` (default `SAR`), but there is no `exchange_rate` field anywhere in the codebase, `currency_code` isn't user-settable on sales/purchasing documents, and no conversion logic exists. Effectively single-currency (SAR) in practice today. |
| Product type | No explicit service/goods distinction — `Product.is_stockable: bool` is the only proxy. |
| Localization | Frontend: full `t()`-driven bilingual UI (`ar.json`/`en.json`, 836 keys each). Backend: **no localization layer** — only a `name`/`name_ar` field-pair pattern on `Company`, `Branch`, `Account`, `FixedAssetCategory`, `Partner`, `UnitOfMeasure`, `Product` (all except Company/Branch have `name_ar` nullable). Everything else (`CostCenter`, `TaxGroup`, `TaxRate`, `FiscalPeriod`, `ProductCategory`, `Warehouse`, `Location`, and every transactional document) is English-label-only. |

## 2.5 Frontend surface (what an "enabled/disabled module" would actually gate)

Stack: Next.js 16.2.12, React 19.2.4, shadcn/ui (`base-nova` style), TanStack Query, Zustand (`stores/auth-store.ts`), `react-hook-form`+`zod` **installed as dependencies but not used anywhere yet** (every current form is plain `useState` + manual HTML validation). **No wizard/stepper UI pattern exists anywhere in the codebase** — confirmed by exhaustive search. A Customer Profile / Blueprint wizard (§3, §5) is a wholly new frontend component category, not an extension of an existing one.

Route groups, from `frontend/lib/nav-config.ts` and actual folder structure: Dashboard; Sales (quotations/orders/invoices/returns/receipts/reports); Accounting (single page, tab-routed — accounts/journal-entries/trial-balance/income-statement/balance-sheet/general-ledger/vat-summary/subledgers/aging/fiscal-periods); Fixed Assets (categories/depreciation-schedule/card/reconciliation); Inventory (single page, tab-routed — warehouses/stock/moves/transfer/cycle-counts/cardex/valuation/low-stock); Purchasing (orders/bills/returns/payments/reports); Master Data (products/categories/uom/address-book/customers/vendors/employees — the last three are filtered Partner views, not separate entities); Settings (company/security/account/users); Payments (real folder, not yet in `NAV_CONFIG`).

Reusable pieces directly relevant to building Adaptive ERP UI: `FormView` (`components/erp/form-view/`, standardized page chrome), `<Can permission="...">` (`components/erp/permissions/can.tsx`, UX-only gate — real enforcement is always server-side via `require_permission`), `useMyPermissions()` (`hooks/use-permissions.ts`), and `NAV_CONFIG` itself as a config-driven nav array — the natural place to add permission/capability-based item visibility later, though it doesn't do that today.

## 2.6 Dashboard — already fiscal-year-aware, already a plausible home for Blueprint-driven visibility

`DashboardService.get_summary()` (`backend/src/modules/reporting/application/services.py`) returns period sales/purchases totals, AR/AP/cash balances (derived from fixed account codes `1200`/`2100`/`1100`), a monthly sales trend, pending-PO-approvals count, and up to 8 recent-activity items. The fiscal-year window is computed **client-side** in `frontend/app/(dashboard)/dashboard/page.tsx` from `company.fiscal_year_start_month`, then passed to the API as explicit `period_start`/`period_end` params — the backend has no built-in fiscal-year logic of its own. Worth noting for §12 (management-visibility Customer Profile dimension) and for any future "what does this company's dashboard need to show" configuration.

## 2.7 The central gap, stated plainly

The system has **no concept of a per-company, data-driven "what's turned on."** `ENABLED_MODULES` is a single global list edited in source code at deploy time. There is no feature-flag table, no per-company module-activation record, no "edition"/"package"/"plan"/"tier"/"license" concept anywhere in the codebase (confirmed by exhaustive search — false positives only: npm's `package.json`, deployment-architecture "tiers," ZATCA's unrelated "data package"). Everything Adaptive ERP needs — Customer Profile, Sizing Engine, ERP Blueprint, Configuration Engine — is genuinely new construction. What already exists (Company's partial profile fields, role templates, the ZATCA `Protocol` gateway precedent for provider abstraction, RLS/RBAC infrastructure, the fiscal-year-aware dashboard) is real and reusable groundwork, not a false start to undo.

## 2.8 Precedent worth calling out: the ZATCA gateway abstraction

`backend/src/modules/zatca/infrastructure/gateways/base.py` defines `IZatcaGateway` (a `Protocol`), with `SandboxZatcaGateway` as the current concrete implementation. The module's own docstring states the intent: *"Sales depends only on this Protocol; which concrete gateway is wired in is a DI/config concern keyed off `company.zatca_environment`."* **In practice this isn't fully wired** — `sales/api/deps.py` hardcodes `SandboxZatcaGateway()` regardless of `company.zatca_environment`. This is exactly the shape a future AI-provider abstraction should follow (see [`08-ai-opportunities.md`](08-ai-opportunities.md) §Provider Independence) — but it's honest to note the precedent hasn't proven itself end-to-end yet, so it should be treated as "a pattern to follow," not "a working example to copy verbatim."
