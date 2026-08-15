# 04 — ERP Sizing Engine Specification

Answers: **"Given this Customer Profile, what configuration complexity does this business actually need?"** Not a Small/Medium/Large label — a scored, explainable recommendation. Design only; nothing here is implemented. See [`06-configuration-engine-architecture.md`](06-configuration-engine-architecture.md) for where this engine sits architecturally.

## 4.1 Why not just three buckets

"Small/Medium/Large" collapses two independent things that don't move together: a 3-person consultancy with complex multi-jurisdiction tax needs is not "small" in the way a 40-person single-branch retailer is "small." A scored, multi-dimensional model lets the engine recommend *specific* configuration decisions and explain *each one*, which a size label cannot do. The explainability requirement (§4.4) is not a nice-to-have — it's what lets a salesperson or implementer stand in front of a customer and say "here is why we recommend this," which is the whole commercial point of Adaptive ERP (see [`01-product-vision.md`](01-product-vision.md)).

## 4.2 Dimensions (initial proposal — every threshold below is illustrative, not final)

Each dimension scores 0–100 from one or more Customer Profile fields (§ references to [`03-customer-profile-spec.md`](03-customer-profile-spec.md)).

| Dimension | Profile inputs | What a high score means |
|---|---|---|
| **Organizational Complexity** | Employees, branches, cost centers needed (§B) | More roles needed beyond the 4 seeded templates, more branch/warehouse structure to provision |
| **Transaction Volume** | Monthly SO/PO volume, SKU count (§C) | Reporting/dashboard emphasis on volume-handling views (aging, subledgers) over simple totals |
| **Inventory Complexity** | Goods vs. services, warehouse count, valuation method (§C) | Whether Inventory module is enabled at all, and how many warehouses get pre-provisioned |
| **Financial Complexity** | CoA depth desired, cost center tracking, multi-currency ask (§D) | Deeper CoA seed, cost-center Blueprint flag (contingent on the CoA gap in §10), honest FUTURE CAPABILITY flag if multi-currency requested |
| **Tax/Compliance Complexity** | VAT status, withholding needs, ZATCA phase (§E) | Which `TaxRate` rows get seeded; ZATCA environment set correctly |
| **Asset Complexity** | Fixed asset ownership, count (§F) | Whether Fixed Assets module is enabled |
| **Approval/Governance Complexity** | Desired approval rigor (§H) | Whether PO threshold is set low (tight control) or high/null (loose); flags the approval-workflow gap honestly if the customer wants more than PO-level approval exists today |
| **Security/Access Complexity** | User count, role separation needs (§I) | How many of the seeded role templates are provisioned; whether custom roles are recommended |

**Composite score is *not* a single overall number the customer sees as "your score."** It's an internal vector; the *reasons* (§4.4) are what get shown. A single number invites exactly the "Small/Medium/Large" flattening this design explicitly rejects.

## 4.3 Weights and thresholds — configuration, not code

Every weight and every threshold used to map a dimension score to a Blueprint decision (e.g., "Organizational Complexity ≥ 60 → recommend provisioning a second branch template") must live in a versioned configuration record, never as a magic number inside application service code. This directly serves Principle 5 (Explainable Decisions) and Principle 10 (Reproducibility) in [`12-architectural-principles.md`](12-architectural-principles.md): re-running the engine against the same profile and the same rule version must always produce the same Blueprint, and changing a threshold must be an auditable configuration change, not a code deploy.

Proposed (not final) storage shape: a `sizing_rule_set` concept, versioned by a simple string (e.g., `sizing-rules-v1`), containing the dimension weight table and threshold table as data. See [`06-configuration-engine-architecture.md`](06-configuration-engine-architecture.md) for how this relates to the Configuration Engine's `configuration_rule_version` concept — they may end up being the same versioning mechanism; that's an implementation decision for a later stage, not this one.

## 4.4 Explainability — the actual product requirement

The engine's output must let a human say, for every material recommendation, one sentence in the shape: *"We recommend `X` because your profile indicated `Y`, which maps to `Z` in rule version `V`."* Concretely, each Blueprint recommendation carries:

- `decision` (e.g., "Enable Fixed Assets module")
- `reason` (the specific profile answer(s) that triggered it, in plain business language, not a dimension-score number)
- `rule_version` (which sizing rule set produced this)
- `confidence` or `certainty` marker — some recommendations are unambiguous (customer said "yes, we own fixed assets" → enable the module is not really a judgment call), others are genuinely a judgment call (organizational complexity sitting near a threshold boundary) and should be presented as such, not with false precision.

This is deterministic, testable business logic — no AI is required to produce it. See [`08-ai-opportunities.md`](08-ai-opportunities.md) for where AI *can* add value on top of this (turning the reason list into more natural prose, or proposing profile answers the customer didn't think to give) without ever being the thing that decides the configuration.

## 4.5 Conflict handling

Two dimensions can point in different directions for the same decision (e.g., low Transaction Volume but high Tax Complexity both touch how prominent the VAT Summary report is in the Blueprint's reporting package). Conflict resolution is itself a configuration concern: each rule carries a priority, and the engine's job is to apply the highest-priority rule that fires and record *which other rules were considered and why they lost*, not to silently pick one. This mirrors the Configuration Engine's own conflict-handling requirement in [`06-configuration-engine-architecture.md`](06-configuration-engine-architecture.md) — they are the same kind of problem at two different points in the pipeline.

## 4.6 What the Sizing Engine explicitly does not do

- It does not write to the database. Its output (a set of scored recommendations) is an input to the ERP Blueprint (§05), which is what gets reviewed and approved.
- It does not require AI to function. A deterministic, rules-based version is the baseline; an AI-assisted version (proposing profile answers, explaining recommendations in more natural language) is strictly additive and optional — see Principle 6.
- It does not recommend anything the Configuration Catalog doesn't actually support. If a dimension score would suggest recommending a feature that doesn't exist in the Core yet (e.g., multi-currency, department hierarchy, sales-order approval chains), the engine's output must say so honestly as a FUTURE CAPABILITY note, never silently omit it or silently pretend to support it.
