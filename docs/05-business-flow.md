# Phase 5 — Business Flow

**Status:** Draft for approval | **Version:** 0.1
**Builds on:** [04-use-cases.md](04-use-cases.md)

Diagrams use Mermaid syntax (renders on GitHub/most Markdown viewers). Each flow references the use cases it sequences.

---

## 1. Order-to-Cash (O2C)

Sequences UC-SAL-01, UC-SAL-02, UC-SAL-03/04, UC-SAL-05.

```mermaid
flowchart TD
    A[Quotation Created] --> B{Customer Approves?}
    B -- No --> A
    B -- Yes --> C[Sales Order Confirmed]
    C --> D[Delivery Created]
    D --> E{Stock Available?}
    E -- No, no override --> D
    E -- Yes --> F[Stock Deducted - FIFO/Average]
    F --> G[Delivery Done]
    G --> H{Customer Type?}
    H -- B2B --> I[Generate Tax Invoice]
    H -- B2C --> J[Generate Simplified Invoice]
    I --> K[ZATCA Clearance - synchronous]
    K -- Rejected --> L[Return to Draft, show error]
    L --> I
    K -- Cleared --> M[Deliver Invoice to Customer]
    J --> N[Deliver Invoice to Customer immediately]
    N --> O[Queue ZATCA Reporting - async, within 24h]
    M --> P[Post Journal Entry: Dr Receivable / Cr Revenue+VAT]
    O --> P
    P --> Q{Return/Adjustment Needed?}
    Q -- Yes --> R[Credit Note - repeats Clearance/Reporting]
    Q -- No --> S[Cycle Complete]
```

**Key control points:**
- Stock cannot go negative without an explicit override (FR-INV-007).
- A Tax Invoice is not legally valid until ZATCA clearance succeeds; a Simplified Invoice is valid at issuance but must still be reported within 24h.
- Every state transition (confirm/deliver/invoice) creates its own journal entry — never a single entry at the end (FR-SAL-007).

---

## 2. Procure-to-Pay (P2P)

Sequences UC-PUR-01, UC-CORE-05 (conditional approval).

```mermaid
flowchart TD
    A[Purchase Order Drafted] --> B{Amount > Approval Threshold?}
    B -- Yes --> C[Route to Approver]
    C -- Rejected --> D[Return to Draft with comment]
    D --> A
    C -- Approved --> E[PO Confirmed]
    B -- No --> E
    E --> F[Goods Receipt Recorded]
    F --> G[Stock Increased]
    G --> H[Journal Entry: Dr Inventory / Cr Goods Received Not Invoiced]
    H --> I[Vendor Bill Registered]
    I --> J{3-Way Match: PO = Receipt = Bill?}
    J -- Mismatch --> K[Flag for Manual Review]
    K --> I
    J -- Match --> L[Bill Approved & Posted]
    L --> M[Journal Entry: Dr GRNI / Cr Accounts Payable]
    M --> N[Cycle Complete - awaiting payment, out of nucleus scope]
```

**Note:** Payment execution (bank reconciliation, payment runs) is not part of the nucleus FR list; the flow ends at Accounts Payable posting. If needed sooner than the Backlog priority suggests, this should be raised explicitly rather than added silently.

---

## 3. ZATCA Invoice Submission — Detailed Adapter Flow

Expands UC-SAL-03/UC-SAL-04 at the technical/adapter level (informs Phase 8 architecture: this entire flow lives behind a single ZATCA Adapter interface).

```mermaid
sequenceDiagram
    participant App as Sales/Invoicing Service
    participant Adapter as ZATCA Adapter Service
    participant Sign as Signing/Stamping Component
    participant ZATCA as ZATCA Platform

    App->>Adapter: Invoice data (draft)
    Adapter->>Adapter: Assign UUID + ICV, compute Hash Chain link
    Adapter->>Sign: Build UBL 2.1 XML
    Sign->>Sign: Apply Cryptographic Stamp (device CSID)
    Sign-->>Adapter: Signed XML + QR payload
    alt Standard Tax Invoice (B2B)
        Adapter->>ZATCA: Clearance request (synchronous)
        ZATCA-->>Adapter: Cleared invoice + authority stamp OR rejection
        alt Cleared
            Adapter-->>App: Cleared invoice, ready to deliver
        else Rejected
            Adapter-->>App: Error details, invoice reverted to Draft
        else Timeout/Unreachable
            Adapter-->>App: Status = Pending Submission (retry scheduled)
        end
    else Simplified Invoice (B2C)
        Adapter-->>App: Invoice delivered immediately (no wait)
        Adapter->>Adapter: Enqueue for async Reporting
        Adapter->>ZATCA: Reporting request (within 24h, background job)
        ZATCA-->>Adapter: Acknowledgement OR post-hoc rejection
        alt Post-hoc rejection
            Adapter-->>App: Flag invoice for accountant review
        end
    end
```

**Architectural implication carried to Phase 8:** the rest of the system never talks to ZATCA directly — only through the Adapter's stable interface (`submitInvoice(invoice) -> SubmissionResult`). This satisfies NFR-COMPLY-001 and FR-ZATCA-012 and keeps ZATCA protocol churn contained to one module.

---

## 4. Inventory Valuation Flow (FIFO / Average)

Sequences UC-SAL-02, UC-PUR-01 (receipt), UC-INV-02, informing FR-INV-004/005.

```mermaid
flowchart TD
    A[Stock-affecting Event] --> B{Direction?}
    B -- Inbound - Receipt/Adjustment+ --> C[Add Layer: qty, unit cost, timestamp]
    B -- Outbound - Delivery/Adjustment- --> D{Valuation Method}
    D -- FIFO --> E[Consume oldest layer(s) first, compute weighted cost of issued qty]
    D -- Average --> F[Recompute moving average cost, apply to issued qty]
    E --> G[Stock Move recorded with computed unit cost]
    F --> G
    C --> H[Stock Move recorded with received unit cost]
    G --> I[Journal Entry: Dr COGS / Cr Inventory]
    H --> J[Journal Entry: Dr Inventory / Cr GRNI or Adjustment account]
```

**Design decision required in Phase 7 (Database Design):** the valuation method (FIFO vs Average) is a per-company setting; FIFO requires a stock-layer table, Average requires a running moving-average field per item/location. Both structures should exist in the schema, but only the configured method is active per company (see FR-INV-004).

---

## 5. Approval Workflow (Generic Engine)

Used by UC-CORE-05, invoked conditionally from O2C and P2P flows.

```mermaid
flowchart TD
    A[Document Submitted] --> B{Approval Rule Matches?<br/>e.g. doc type + amount}
    B -- No rule matches --> C[Auto-approved, proceed]
    B -- Rule matches --> D[Status = Pending Approval, Level 1]
    D --> E[Notify Approver]
    E --> F{Decision}
    F -- Approve, more levels remain --> G[Advance to Level N+1]
    G --> E
    F -- Approve, final level --> H[Status = Approved, proceed]
    F -- Reject --> I[Status = Draft, notify originator with reason]
    F -- Delegate --> J[Reassign to delegate, notify]
    J --> F
```

---

## 6. Traceability

| Flow | Governing Use Cases | Governing FRs |
|------|----------------------|-----------------|
| Order-to-Cash | UC-SAL-01..05 | FR-SAL-*, FR-ZATCA-* |
| Procure-to-Pay | UC-PUR-01, UC-CORE-05 | FR-PUR-*, FR-CORE-052 |
| ZATCA Submission | UC-SAL-03, UC-SAL-04 | FR-ZATCA-001..012 |
| Inventory Valuation | UC-INV-01, UC-INV-02, UC-SAL-02, UC-PUR-01 | FR-INV-004, FR-INV-005 |
| Approval Workflow | UC-CORE-05 | FR-CORE-052 |

---

## 7. General Acceptance Criteria

- [ ] Project owner confirms these flows match real-world operating procedure (especially ZATCA Clearance vs Reporting split, and the P2P cutoff at Accounts Payable).
- [ ] Any missing control point or exception path is raised before Phase 6 (ER Diagram), since the ER model is derived directly from these flows' data touchpoints.

---

*End of Phase 5. Proceeding to Phase 6: ER Diagram.*
