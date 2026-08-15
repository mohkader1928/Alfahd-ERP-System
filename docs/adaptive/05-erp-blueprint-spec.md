# 05 — ERP Blueprint Specification

The **output of profiling**: a concrete, reviewable, versioned statement of what a company's ERP configuration should be. The customer (or their implementer) reviews and approves a Blueprint before it's ever applied — see [`06-configuration-engine-architecture.md`](06-configuration-engine-architecture.md) for how an approved Blueprint becomes a running configuration, and [`09-sales-and-onboarding-flow.md`](09-sales-and-onboarding-flow.md) for where "Review → Approve" sits in the customer journey.

## 5.1 What a Blueprint contains

| Field group | Content | Grounded in |
|---|---|---|
| **Enabled modules** | Which of the 11 Core modules are active for this company (`accounting`, `sales`, `purchasing`, `inventory`, `payments`, `fixed_assets`, `reporting`, plus always-on `identity`/`notifications`/`attachments`; `zatca` follows `sales`) | Today, module activation is a single *global* code list (`ENABLED_MODULES` in `main.py`) — see [`02-current-state-assessment.md`](02-current-state-assessment.md) §2.4 and §2.7. A Blueprint needs *per-company* module visibility, which is new (§06). |
| **Enabled features within a module** | E.g., within Accounting: is cost-center tracking surfaced; within Purchasing: is PO-threshold approval active and at what value | Maps directly onto real, already-configurable fields (`Company.po_approval_threshold`) plus new per-company feature flags for gaps like cost centers |
| **Organizational structure** | Recommended branch count, warehouse count, initial cost centers | `Branch`/`Warehouse` already exist as real entities (§02 §2.3); a Blueprint's org-structure section is a *provisioning plan* against them, not a new data model |
| **Roles provisioned** | Which of the 4 seeded role templates (or custom roles) get created for this company | Directly maps to `seed_default_role_templates()` — already real |
| **Tax configuration** | Which `TaxRate`/`TaxGroup` rows get seeded, ZATCA environment | Maps to existing entities |
| **Accounting configuration** | CoA starting depth, fiscal year start month | `Company.fiscal_year_start_month` already exists; CoA depth is a seeding decision, not a schema change |
| **Reporting package** | Which existing reports/dashboard sections are surfaced prominently | Cosmetic nav-visibility layer over an already-complete report set (§02 §2.6) |
| **Expected scale** | The Customer Profile's current-state numbers, snapshotted | Provenance — lets a later Growth Review compare "what did we plan for" against "what's actually true now" |
| **Growth path** | The Customer Profile's Growth section (§03 §G), carried as a separate, clearly-labeled *forward-looking* section — never conflated with the current Configuration | See [`07-editions-and-growth-model.md`](07-editions-and-growth-model.md) |
| **Recommended edition/package label** | A human-readable name (see [`07-editions-and-growth-model.md`](07-editions-and-growth-model.md)) — a *label*, never a code branch or a licensing gate baked into business logic | Principle 12 |

## 5.2 What a Blueprint is not

- Not executable code. It's data — a structured record that the Configuration Engine (§06) reads to provision or update a company.
- Not a guess. Every recommendation in it traces back to a specific Sizing Engine reason (§04 §4.4) — a Blueprint without traceable reasons is not a valid Blueprint.
- Not final until approved. A generated Blueprint is a *proposal* (`status: draft`) until an authorized human approves it (`status: approved`) — see Principle 5 and the governing spec's non-negotiable AI rule (AI must not directly mutate production configuration without explicit approval, which applies equally to the deterministic engine's own output, not just AI-assisted output).

## 5.3 Versioning — the core requirement

> "We need to know: what configuration was this customer on at a given point in time?"

Every Blueprint is an **immutable, versioned record**, never edited in place. A new Blueprint version is created whenever:
- A Growth Review produces a new recommendation (§09),
- The customer's actual usage diverges materially from what was provisioned and the configuration is deliberately updated,
- The Sizing Engine's rule set changes and someone chooses to re-run profiling for an existing customer.

Each Blueprint version records: which Customer Profile version it was generated from, which Sizing Engine rule version produced it, who approved it and when, and (once applied) a link to the resulting Configuration Profile record (§06). This gives a complete, auditable chain: *Profile → Blueprint → Configuration*, each step versioned, none of them mutated after the fact — directly serving Principle 4 (Versioned Configuration), Principle 9 (Auditability), and Principle 10 (Reproducibility) in [`12-architectural-principles.md`](12-architectural-principles.md).

## 5.4 Reversibility

"Reversible where appropriate" (Principle 4) means: rolling back to a previous Blueprint version is always safe for *configuration* (which modules/features are visible, which roles exist as templates) but is explicitly **not** a way to undo real business data. A company that had Fixed Assets enabled, recorded real depreciation entries, and then has that module hidden by a later Blueprint does not lose the historical entries — they remain in the database, visible in reports, just not surfaced as an active work area in navigation. This mirrors the existing Core's own principle already proven in production: fiscal period closing doesn't delete anything, JE cancellation doesn't delete anything, Sales/Purchase Returns don't delete the original documents. Configuration changes must never silently alter historical accounting or transactions — this is a hard constraint, not a preference (see [`10-adaptive-gap-analysis.md`](10-adaptive-gap-analysis.md) for how this interacts with the "disable a module" case specifically).

## 5.5 Relationship to Growth Blueprint

A **Blueprint** describes the company's configuration *now*. A **Growth Blueprint** (detailed in [`07-editions-and-growth-model.md`](07-editions-and-growth-model.md)) describes where the Customer Profile's Growth section says the company is headed. They are stored and versioned separately — a Growth Blueprint is advisory and forward-looking; it never gets "applied" the way a Blueprint does. When a Growth Review confirms growth has actually happened, that's when a *new* Blueprint version gets generated and (after approval) applied — the Growth Blueprint informs that moment, it doesn't substitute for the approval step.
