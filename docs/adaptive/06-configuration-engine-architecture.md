# 06 — Configuration Engine Architecture

Answers: **"How does an approved Blueprint become a real, working company configuration — and where, precisely, does all of this live in the existing codebase?"** Architecture only. No migrations, models, or endpoints are created by this document — see [`10-adaptive-gap-analysis.md`](10-adaptive-gap-analysis.md) and [`11-adaptive-roadmap.md`](11-adaptive-roadmap.md) for when implementation would actually happen, contingent on separate approval.

## 6.1 The pipeline and where each stage lives

```
Customer Profile          (new module: company_profile)
        │  read-only input
        ▼
Sizing Engine              (application-layer service inside company_profile,
        │  pure function, no DB writes)                deterministic, unit-testable in isolation)
        ▼
ERP Blueprint (draft)      (new table: erp_blueprint, status=draft)
        │
        ▼
Human review + approval    (require_permission("configuration.blueprint.approve") —
        │                   same RBAC mechanism the Core already uses 156 times elsewhere)
        ▼
ERP Blueprint (approved)   (immutable from this point; a later change = new version)
        │
        ▼
Configuration Engine        (applies the approved Blueprint's decisions)
        │
        ▼
Configuration Profile      (new table: configuration_profile — the resolved,
                             active "what's on" record for this company)
        │
        ▼
Provisioned Company         (real rows in real Core tables: Branch, Warehouse,
                             Role, TaxRate, etc. — created via the SAME
                             application services the Core already uses for
                             manual setup, never a parallel write path)
```

**Critical architectural decision**: the Configuration Engine does not invent a new way to create a `Branch` or a `Role`. It calls the *same* `BranchService`, `RoleService`, `TaxRateService`, etc. that a human clicking through Settings would trigger. This is what keeps "Configuration Engine" from becoming a second, parallel business-logic layer that drifts out of sync with the real one — it's an orchestrator over existing application services, not a reimplementation of what they do. This directly answers §09 of the governing spec ("what must stay in code vs. move to configuration"): **all business rules stay exactly where they are today, in application services; only the *decision of which calls to make* moves to configuration.**

## 6.2 Where this lives in the module structure

Following the Golden Core's own established pattern (module-per-directory, `domain/application/infrastructure/api`), a new module: `backend/src/modules/company_profile/`.

**Why a new module and not an extension of `identity`** (where `Company` already lives): `identity` is already the largest, most security-critical module in the Core (auth, 2FA, RBAC, audit). Bolting Customer Profile / Sizing / Blueprint / Configuration onto it would inflate the highest-risk-to-touch module in the system for a feature that is conceptually distinct (business profiling, not identity/access). The new module *depends on* `identity` (reads `Company`, calls its services) exactly the way `sales` depends on `inventory` today — a normal one-way module dependency, not a special case.

```
backend/src/modules/company_profile/
  domain/        — CompanyProfile, SizingResult, Blueprint entities (pure, no ORM)
  application/    — SizingEngineService, BlueprintService, ConfigurationEngineService
  infrastructure/ — ORM models, repositories (same TenantScopedMixin + RLS pattern as every other table)
  api/            — wizard endpoints, RBAC-gated exactly like every other module's routes
```

## 6.3 Proposed data model (names illustrative, not final — see §06.6)

| Table | Purpose | Design note |
|---|---|---|
| `company_profile` | The Customer Profile (§03), 1:1 with `company.id` | **Separate table, not new columns on `company`.** `Company` is touched by every RLS policy and every auth path in the Core — keeping profile data in its own table means this entire initiative can be additive and never risk the shape of the highest-traffic table in the system. |
| `configuration_catalog_item` | The fixed, code-and-migration-managed list of "things that can be turned on" (modules, features, limits) | Seeded data, evolves via normal migrations — not a dynamically-editable-by-admins table in v1, exactly as the Core's own `PERMISSION_CATALOG` works today |
| `sizing_rule_set` | Versioned weights/thresholds for the Sizing Engine (§04 §4.3) | Data, not code — this is the literal mechanism that makes thresholds "configurable, not hardcoded" |
| `erp_blueprint` | Each Blueprint version (§05), `status: draft\|approved\|superseded` | Immutable once approved |
| `configuration_profile` | The resolved, currently-active "what's on" for a company | One active row per company (others `superseded_by_id`-linked, never deleted) |
| `growth_blueprint` | The forward-looking Growth section (§03 §G, §07) | Explicitly never "applied" — advisory only |
| `ai_recommendation` | If/when AI assists Sizing (§08): the raw AI output, linked to the human decision made on it | Exists independently of whether AI is enabled — a full audit trail of "AI suggested X, a human did Y" |

All of the above use `TenantScopedMixin` and get the same RLS `company_isolation` policy as every other Core table — no new isolation mechanism, the existing one (§02 §2.1) already covers this correctly.

`AuditLog` (already real, already used in 5 modules) is the audit mechanism for every write this engine makes — **not** a new `configuration_audit` table. Reusing what exists is itself a demonstration of the "configuration over custom code" principle (§10 of the governing spec) applied to this project's own construction.

## 6.4 What stays in code vs. what moves to configuration

| Stays in code (application services) | Moves to configuration (data) |
|---|---|
| How a journal entry balances, how VAT is computed, how stock valuation works, how a PO threshold gates approval — every actual business rule | *Which* modules are visible, *which* roles get provisioned, *which* tax rates get seeded, *what* the PO threshold's value is |
| The Sizing Engine's scoring *mechanism* (how a score is computed from inputs) | The Sizing Engine's weights and thresholds (§04 §4.3) |
| RLS policies, RBAC enforcement mechanism | Which permission codes belong to which seeded role template (already configuration today — `seed_default_role_templates()`'s template list could itself become data-driven later, though it's fine as code for v1) |

This is the literal answer to "CONFIGURATION > CUSTOM CODE": the *boundary* is that business behavior is always code (testable, versioned in git, reviewed like any other code change) and *selection/parameterization* of that behavior is always data (versioned in the database, auditable, changeable without a deploy). See [`12-architectural-principles.md`](12-architectural-principles.md) Principle 2.

## 6.5 STANDARD / CONFIGURABLE / EXTENSIBLE / CUSTOM DEVELOPMENT

Four tiers, each with a different cost/risk profile — this is the commercial boundary the governing spec asked for explicitly (§10):

1. **STANDARD** — works identically for every customer, not configurable at all (e.g., how double-entry balancing works, how RLS isolates companies). Changing this means changing the Core, reviewed and released like any Phase-One work.
2. **CONFIGURABLE** — a Blueprint/Configuration Profile decision (which modules are on, tax rates, role templates, approval threshold value). Zero code risk to change per-customer; this is the entire point of Adaptive ERP.
3. **EXTENSIBLE** — the Core has a real extension point but using it requires implementation work specific to a customer's need (e.g., a new report built on the existing `shared/reporting/` export pipeline, using data that already exists). Bounded, lower-risk custom work — not a fork, built using existing patterns.
4. **CUSTOM DEVELOPMENT** — genuinely new Core capability (a new module, a new entity). This is Core roadmap work, prioritized like Phase-One work was, never done as an unreviewed one-off for a single customer — this is the direct enforcement mechanism for Principle 12 (No Customer-Specific Forks).

Every gap identified in [`10-adaptive-gap-analysis.md`](10-adaptive-gap-analysis.md) is explicitly tagged with which of these four tiers it belongs to.

## 6.6 Security implications (answering the governing spec's explicit ask)

- **RLS**: no new mechanism — new tables get the same `company_isolation` policy pattern used by every table added since Phase 16A. Tested the same way (`tests/test_multi_tenancy_isolation.py`-style tests, extended to cover the new tables).
- **RBAC**: new permission codes only (`configuration.profile.manage`, `configuration.blueprint.approve`, etc.), added to the existing 79-entry catalog — the enforcement mechanism (`require_permission`) is unchanged.
- **AI data access** (if/when Stage 7 happens): any AI-assisted Sizing call inherits the *same* `AuthContext` as the human request that triggered it — it never opens an independent DB session, so RLS's existing default-deny-on-missing-context behavior (already tested: `test_missing_context_default_deny_across_all_five_tables`) is the safety net automatically, not something new to build. See [`08-ai-opportunities.md`](08-ai-opportunities.md) §Provider Independence for the full boundary.
- **New risk to actually manage**: none of this exists in the Core today, so there's no existing rate-limiting to extend — a genuinely new gap (the Core has zero rate limiting anywhere) becomes directly relevant the moment any AI-assisted, cost-incurring endpoint is added. Flagged in [`10-adaptive-gap-analysis.md`](10-adaptive-gap-analysis.md) as a P1, not something to defer indefinitely once Stage 7 is real.

## 6.7 Migration and backward-compatibility posture (design intent, not executed here)

All new tables, purely additive (`CREATE TABLE`, never `ALTER` on an existing high-traffic table) — matching the Core's own migration history, which has been additive-only for its entire 50-migration life (confirmed in Stage 0). Existing companies (every company created before this feature ships) get **no** `configuration_profile` row by default — absence of a row means "behaves exactly as v1.0.0 does today," never a computed default that changes existing behavior. Migrating an existing company onto Adaptive Configuration is always an explicit, approved action (a Blueprint generated from that company's *actual current* settings, reviewed, then approved) — never automatic. See Principle 7 (Backward Compatibility) in [`12-architectural-principles.md`](12-architectural-principles.md).
