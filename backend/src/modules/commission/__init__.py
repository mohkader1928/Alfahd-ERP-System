"""Commission ledger module (Commercial Performance Stage 3).

Per the same shape as the `zatca` module (Phase 8 §3): this module has no
public HTTP routes and is reachable only from Sales (sales commission,
recorded/reversed at invoice and credit-note issuance) and Payments
(collection commission, recorded at customer-receipt time) — nothing else
writes here. Reporting reads `CommissionTransaction` directly, the same way
it already reads Sales/Payments/Purchasing tables (FR-RPT-003). There is
therefore no `register()` and this module is not listed in
`ENABLED_MODULES`.
"""
