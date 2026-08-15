# 11 — Adaptive ERP Roadmap

Adjusted from the governing spec's example plan against what [`10-adaptive-gap-analysis.md`](10-adaptive-gap-analysis.md) actually found — notably, two small-but-blocking P0 gaps (Branch management API/UI, the wizard UI pattern) are pulled forward into Stage 2 rather than left implicit, because later stages depend on them concretely.

Every stage below is **subject to separate, explicit approval before implementation begins** — this roadmap is a plan, not a series of pre-authorized work orders. Stage 1 (this document set) authorizes nothing beyond itself.

| Stage | Goal | Depends on | Est. relative effort |
|---|---|---|---|
| **1 — Architecture & Specification** | This document set. Ground every later decision in the real Core, not assumption. | Stage 0 (Golden Baseline protection) | Done |
| **2 — Foundation** | Close the two small blocking gaps first: Branch management (CRUD API + Settings UI) and the first real wizard/multi-step UI component (built generically enough to serve the Customer Profile wizard later, not single-purpose). Also: `company_profile` table + basic profile CRUD, no Sizing/Blueprint yet. | Stage 1 | Small-Medium |
| **3 — Customer Profile** | Full A–J profile wizard (§03), using the Stage 2 wizard component. No scoring yet — just capture and review. | Stage 2 | Medium |
| **4 — Sizing Engine** | Deterministic scoring (§04), versioned rule sets, explainability. Fully unit-testable in isolation, no UI dependency beyond displaying its output. | Stage 3 | Medium |
| **5 — ERP Blueprint** | Blueprint generation, versioning, review/approval UI (§05). | Stage 4 | Medium |
| **6 — Configuration Engine & Provisioning** | Approved Blueprint → real Branch/Warehouse/Role/TaxRate rows via existing services (§06.1). This is the stage where the core "adapts and grows" claim (§07 §7.4) becomes demonstrable for the first time — the natural point to actually run the Growth Path worked example (§07 §7.3) end-to-end as an acceptance test. | Stage 5, and the Branch API gap from Stage 2 | Medium-Large |
| **7 — Editions & Commercial Packaging** | Edition labels over Configuration state (§07 §7.1), pricing/packaging work (commercial, not engineering) | Stage 6 | Small (engineering side) |
| **8 — AI Advisory Layer** | `AIProviderPort` + first adapter, starting with the lowest-risk NOW items from [`08-ai-opportunities.md`](08-ai-opportunities.md) (Company Setup Assistant, Configuration Recommendation narration). Rate limiting (flagged P1-contingent in the gap analysis) becomes a hard acceptance criterion here, not optional. | Stage 6 (must have a proven deterministic engine to be advisory *to*) | Medium |
| **9 — Hardening & Owner Handover** | Full regression, security review of the new modules specifically (RLS/RBAC extension correctness), documentation for owner-independent operation of the new pieces (extending `docs/20-developer-guide.md` the same way Stage 0 did) | All prior stages | Medium |

## Why AI is Stage 8, not earlier

Every governing document in this initiative (the original spec, this roadmap, [`12-architectural-principles.md`](12-architectural-principles.md)) makes the same point in different words: **AI advising on top of a deterministic system that already works is safe; AI as the thing that makes the system work is not.** Stage 8 exists only once Stages 4–6 have proven the Sizing Engine and Configuration Engine work correctly and deterministically without any AI involvement — at that point, AI is purely additive UX, exactly as designed. Building AI earlier would mean either (a) AI silently doing the Sizing Engine's job with no deterministic fallback to fall back to, which directly violates "ERP core must remain fully functional without AI," or (b) building throwaway AI scaffolding that gets replaced once the real engine exists — wasted work either way.

## What's explicitly out of scope for the foreseeable roadmap

Per [`03-customer-profile-spec.md`](03-customer-profile-spec.md) §J and [`10-adaptive-gap-analysis.md`](10-adaptive-gap-analysis.md): Department entities, a generic approval-workflow engine beyond PO, real multi-currency, payroll/HR, manufacturing, CRM, cross-customer AI recommendations. None of these are rejected forever — they're explicitly not committed to *this* roadmap, and should only enter it in response to real, aggregated demand signal surfaced through the Growth Review process (§09), the same discipline the Golden Core itself was built with (Phase-One's own "finish, don't expand" scope rule, documented in `docs/20-developer-guide.md` §22).
