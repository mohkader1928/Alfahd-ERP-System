# 09 — Sales / Onboarding Flow

The customer's actual journey, from first contact to an active, growing ERP relationship. Each stage names what's real today, what's new, and what could plausibly be automated later — automation is noted, not assumed.

```
Lead → Discovery → Company Profile → Assessment → ERP Blueprint →
Configuration → Demo → Approval → Provisioning → Training → Go-live → Growth Review
```

## 9.1 Stage by stage

| Stage | What happens | Grounded in | Future automation potential |
|---|---|---|---|
| **Lead** | Prospect identified (sales/marketing activity, entirely outside this system) | N/A | Not this system's concern |
| **Discovery** | A salesperson or implementer has an initial conversation about the business | N/A — human conversation | AI Company Setup Assistant (§08) could turn discovery notes into a Customer Profile draft |
| **Company Profile** | The prospect (or the implementer on their behalf) fills the profile wizard — [`03-customer-profile-spec.md`](03-customer-profile-spec.md)'s A–J sections | New UI, built on existing reusable pieces (`FormView`, `<Can>`) — see [`02-current-state-assessment.md`](02-current-state-assessment.md) §2.5. **This is also, not coincidentally, a richer version of the existing `/setup` bootstrap flow** — the current 11-field `BootstrapRequest` (§02 §2.5, §9) is effectively a minimal, single-step version of what this stage becomes | The wizard itself is the automation of what used to be a manual spreadsheet/conversation |
| **Assessment** | The Sizing Engine (§04) scores the profile | Deterministic, no AI required | AI can narrate the reasons (§08) once the deterministic engine is proven |
| **ERP Blueprint** | Draft Blueprint (§05) generated, presented with reasons | Deterministic | — |
| **Configuration** | Implementer/customer reviews and adjusts the draft Blueprint before approval | New UI over the Blueprint data model | — |
| **Demo** | The *actual* provisioned-preview or a representative demo company is shown against the proposed Blueprint | Existing demo-data seeding pattern (`backend/src/scripts/seed_general_demo_data.py`, `seed_owner_acceptance_m1a.py`) is a real precedent for "build a demo company that matches a profile" — not identical, but the closest existing analog | Could eventually spin up a live, throwaway preview company from the draft Blueprint |
| **Approval** | Authorized human approves the Blueprint (`require_permission("configuration.blueprint.approve")`, §06.1) | RBAC mechanism already exists; only the specific permission code is new | Never fully automated — approval is a deliberate human gate by design (governing spec: "AI must not directly mutate production configuration without explicit approval," which extends to any automated approval of the deterministic engine's own output) |
| **Provisioning** | Configuration Engine applies the approved Blueprint via existing application services (§06.1) — real `Branch`/`Warehouse`/`Role`/`TaxRate` rows created | New orchestration, old services | This *is* the automation — replacing what today would be a person manually clicking through Settings for each new customer |
| **Training** | Customer's team is trained on their specific, now-configured instance | N/A — human activity, but the training scope is now *derived from the Blueprint* (only the modules/features actually enabled need covering), which is itself valuable and new | Could generate a tailored training checklist from the approved Blueprint |
| **Go-live** | Customer starts real operations | Existing Core, already production-proven (v1.0.0) | — |
| **Growth Review** | Periodic (e.g., annual, or triggered by the customer) re-visit of the Customer Profile — did reality diverge from what was planned? | New process, reusing the same Profile → Sizing → Blueprint pipeline | This is the literal mechanism behind the Growth Path in [`07-editions-and-growth-model.md`](07-editions-and-growth-model.md) — "growth" is not a separate feature, it's this same flow run again |

## 9.2 What's genuinely new vs. what extends something real

The **Company Profile stage directly supersedes and extends the existing `/bootstrap` flow** — not a parallel thing. Today, `/bootstrap` (§02 §2.5, §9) creates a tenant + one company + one branch + one admin user from 11 fields, with no profiling, no sizing, no Blueprint. A faithful Stage 2+ implementation should treat the richer Customer Profile wizard as `/bootstrap`'s natural successor (collecting the same required compliance fields — VAT number, legal names, valuation method — plus everything in §03), not a second, disconnected onboarding path. This matters for the roadmap ([`11-adaptive-roadmap.md`](11-adaptive-roadmap.md)): building a whole second onboarding flow alongside the existing one would itself violate "no customer-specific forks" in spirit, by creating two divergent ways a company comes into existence.

## 9.3 Explicit non-goal for this stage

None of the automation notes above are commitments — they're documented because the governing spec asked "what can plausibly be automated later," and answering that honestly (mostly: not much, safely, until the deterministic pipeline underneath it is proven) is itself useful signal for [`11-adaptive-roadmap.md`](11-adaptive-roadmap.md) sequencing.
