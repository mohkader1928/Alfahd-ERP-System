# 07 — Editions & Growth Model

## 7.1 Editions are labels over Configuration, never separate software

Confirmed in [`02-current-state-assessment.md`](02-current-state-assessment.md) §2.4: no "edition"/"package"/"plan"/"tier"/"license" concept exists anywhere in the codebase today — this is genuinely new ground, with no existing mechanism to protect or work around.

**Proposed initial edition names** (not final — a naming exercise for commercial/marketing to own, not this document):

| Working name | Rough shape | NOT the differentiator |
|---|---|---|
| Micro | 1 branch, 1 warehouse, ≤5 users, Accounting + Sales core only | User count is a side effect of complexity, never the label's definition |
| Small | Small multi-warehouse, Purchasing enabled, basic role separation | |
| SME | Multi-branch, cost centers active, deeper reporting package | |
| Mid-Market | Full module set, approval workflows (contingent on that gap being closed — see §10), custom role design | |
| Growth | Everything above plus active Growth Blueprint tracking, priority for new Core capability | |

**The actual differentiator, per the governing spec's explicit instruction, is functional + organizational complexity, not a user count.** Concretely: an edition label is *derived from* which `configuration_catalog_item` rows are active in a company's `configuration_profile` (§06), never a separate code path, database, or deployment. Two companies on "SME" and "Mid-Market" run the identical binary, identical schema, identical migrations — the only difference is which rows exist in their `configuration_profile`. This is the direct, literal enforcement of Principle 12 (No Customer-Specific Forks) applied to commercial packaging specifically.

## 7.2 Movement between editions requires zero migration to a different product

Because an edition is just a label over Configuration state, "upgrading" a customer from Small to SME is: generate a new Blueprint from an updated Customer Profile (via a Growth Review, §09), review, approve, apply. No data migration to a different schema, no export/import, no new login, no retraining on a different UI beyond whatever new nav items became visible. This is the concrete mechanism behind the marketing claim in §7.4 — without it, the claim would be empty.

## 7.3 Growth Path — worked example

Grounded against real current fields, not hypothetical ones:

**Year 0** (at provisioning): 1 branch (`Branch.is_main=true`, the only branch the Core creates at bootstrap today), 1 warehouse, 5 users (2 seeded role templates handed out: Admin + Accountant), Accounting + Sales enabled, Inventory off (services-only business).

**Year 2** (after a Growth Review, §09): profile updated — now wants 3 branches, 5 warehouses, 40 users, Purchasing and Inventory enabled, cost-center tracking active.

**What changes in Configuration** (no migration): new `configuration_profile` version activates Purchasing/Inventory module visibility; Sales, Purchasing & Warehouse role templates get provisioned for the new hires; PO approval threshold gets set (previously null/unused).

**What requires real provisioning work, not just a config flip** (using existing Core services, not new ones — see §06.1): creating 2 new `Branch` rows and 4 new `Warehouse` rows via the existing (if currently UI-less — see gap analysis) branch/warehouse services; this is real database writes, but through the same application services a human would use, triggered by the approved Blueprint.

**What requires an actual schema/feature gap to close first**: cost-center tracking becoming genuinely usable requires the `CostCenter` CRUD gap (§02 §2.3, §10) to be closed — the table and the JE-line wiring already exist, only the management surface is missing. This is exactly the kind of finding this growth-path exercise is *for*: it surfaces which gaps are load-bearing for a realistic customer journey, not abstract.

**What never needs a migration regardless of growth**: RLS, RBAC, the audit mechanism, the accounting engine itself — none of this scales *differently* for a bigger company, it's the same code running against more rows. This is the single most important property Adaptive ERP is built to prove: growth is a configuration and provisioning event, not a re-architecture event.

## 7.4 Marketing differentiator

Governing spec's example: *"ERP configured around your business — not your business forced into an ERP."*

**Alternative phrasings, each tied to a real, provable mechanism** (not chosen here — offered for commercial team to select from, each annotated with what it actually claims):

- *"من المعاملة إلى القرار — ونظام يتشكل حسب حجمك."* (extends the existing v1.0.0 tagline "من المعاملة إلى القيد... ومن القيد إلى القرار" rather than replacing it — continuity with material already shown to customers)
- *"One ERP. Sized to you today. Built to grow with you."*
- *"Tell us your business once. Get the ERP that fits it — and watch it grow with you, not away from you."*

**What must be true before any of these are said to a customer** (the actual proof burden, per §7.2): a live demonstration of a company moving from a smaller to a larger configuration *without* a data migration, using the mechanism in §6.1–§6.2. Until the Configuration Engine exists and this has been demonstrated once for real, these are aspirational phrasings for this document, not claims to put in front of a customer. See [`11-adaptive-roadmap.md`](11-adaptive-roadmap.md) for the minimum stage at which this claim becomes honestly provable, and the existing marketing material's own precedent (`docs/marketing/company-profile/`) for the standard of "never claim what isn't proven" this project already holds itself to.
