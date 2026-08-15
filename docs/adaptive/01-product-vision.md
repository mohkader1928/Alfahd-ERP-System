# 01 — Adaptive ERP: Product Vision

Stage 1 (Architecture & Product Specification). Documentation only — no code, schema, or runtime behavior changes anywhere in this document set. See [`12-architectural-principles.md`](12-architectural-principles.md) for the non-negotiable constraints this vision operates under.

## 1.1 The problem with today's ERP buying decision

A small Saudi company buying an ERP today faces a bad choice: buy something sized for a company much larger than them (pay for and drown in complexity they don't need yet), or buy something sized for exactly where they are today (and outgrow it in two years, forcing a full migration to a different system — new schema, new training, new integrations, new vendor relationship).

Both paths are expensive and both are avoidable. The underlying business logic of accounting, sales, purchasing, and inventory does not fundamentally change between a 5-person trading company and a 200-person multi-branch distributor — what changes is *how much of it is turned on*, *how many organizational dimensions exist* (branches, warehouses, cost centers, approval levels), and *how much configuration complexity* the business needs versus can absorb.

## 1.2 The vision

**One ERP Core. A Configuration Layer that adapts it to the customer's actual current business — and grows with them, without ever asking them to migrate to a different product.**

```
CUSTOMER PROFILE  ("who is this company, today, and where is it headed?")
        ↓
ERP BLUEPRINT     ("what should be turned on, and why?")
        ↓
CONFIGURATION     ("apply the Blueprint to a real running company")
        ↓
PROVISIONED COMPANY   (the customer's actual, working ERP instance)
```

The customer answers questions about their business once. The system proposes a configuration — enabled modules, organizational structure, approval levels, reporting package — and explains *why* it proposed that, not just what. The customer (or their reseller/implementer) reviews, adjusts, and approves. The company is provisioned. As the business grows, the same mechanism runs again against an updated profile, and the *same* ERP instance adapts — new branches, new warehouses, new approval complexity — without a migration project.

## 1.3 What this is not

- **Not a rewrite.** [`phase-one-v1.0.0`](02-current-state-assessment.md) (commit `6b6403c`) is the Golden Core. Adaptive ERP is a layer added on top of it, not a replacement for it. See Principle 1 in [`12-architectural-principles.md`](12-architectural-principles.md).
- **Not per-customer forks.** Every customer runs the same source code. What differs is *configuration data*, never a customer-specific code branch. See Principle 12.
- **Not an AI product.** AI is one optional, swappable input into the Sizing Engine and an advisory layer elsewhere — never the system of record, never a runtime dependency. See [`08-ai-opportunities.md`](08-ai-opportunities.md) and Principle 6.
- **Not a licensing gimmick.** [`07-editions-and-growth-model.md`](07-editions-and-growth-model.md) explicitly rejects "count the users" as the differentiator between editions — the differentiator is *functional and organizational complexity*, because that's what actually determines whether an ERP fits a business.

## 1.4 Why now, and why this order

[`02-current-state-assessment.md`](02-current-state-assessment.md) shows the Golden Core already has real, if partial, configuration seams: a `Company` entity with several already-configurable fields (VAT, valuation method, fiscal year start, PO approval threshold), a company-scoped permission catalog with seeded role templates, RLS-backed multi-tenancy, and a precedent (the ZATCA gateway `Protocol`) for provider abstraction. None of this was built with "Adaptive ERP" in mind — it was built to solve real Phase-One problems — but it means this initiative is an *extension* of the codebase's existing direction, not a foreign import.

The order matters: Golden Core stability first (Stage 0, already complete — backup/restore, CI, disaster recovery), architecture and specification second (this Stage 1), and only then implementation, staged so that the deterministic Configuration Engine exists and is proven *before* any AI advisory layer is added on top of it. AI recommending a configuration that a human never has to trust blindly, because the engine underneath it is deterministic and testable independent of AI, is the whole point — see [`06-configuration-engine-architecture.md`](06-configuration-engine-architecture.md) and [`08-ai-opportunities.md`](08-ai-opportunities.md).

## 1.5 The commercial thesis

If this works, the company doesn't sell "an ERP." It sells: *tell us your business, and get an ERP that fits it today and grows with you* — a claim most competitors in the Saudi SME/mid-market space cannot make credibly, because they either sell a fixed product or sell heavily customized (forked) implementations that become their own long-term maintenance burden. The v1.0.0 Company Profile marketing material already produced (`docs/marketing/company-profile/`, not part of this document set) established the honest baseline of what the product does today; this vision is what it becomes if Adaptive ERP succeeds. See [`07-editions-and-growth-model.md`](07-editions-and-growth-model.md) §"Marketing Differentiator" for the specific claim and what it would take to prove it in front of a real customer.
