"""ZATCA e-invoicing adapter module.

Per Phase 8 §3, this module has no public HTTP routes and is reachable only
from the Sales module — nothing else may call it, and it does not call back
into Sales beyond returning a result. There is therefore no `register()`
call wired into `src/api/main.py`; it is imported directly by
`modules/sales/application/services.py`.

IMPORTANT — production readiness boundary (see Phase 1 §7 and the M2 kickoff
note): this module implements the real, spec-shaped mechanics that don't
require ZATCA-issued credentials — UUID/ICV sequencing, SHA-256 hash
chaining, TLV/Base64 QR encoding, UBL-lite XML shape. It does NOT implement
a real Cryptographic Stamp (requires a ZATCA CSID certificate from the
Fatoora onboarding portal) and its "Sandbox" gateway does not call the real
ZATCA API — it simulates acceptance so the rest of the system has a working,
swappable integration point. Replace `DevSigningService` and
`SandboxZatcaGateway` with real implementations before any production use.
"""
