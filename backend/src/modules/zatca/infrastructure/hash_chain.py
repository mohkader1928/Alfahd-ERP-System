"""SHA-256 invoice hash chain (FR-ZATCA-004).

Real SHA-256 chaining — this part needs no ZATCA credentials and is
implemented to the actual algorithm: each invoice's hash covers its own
canonical content plus the previous invoice's hash, so tampering with any
invoice in the sequence breaks every hash after it.
"""

import base64
import hashlib

# ZATCA seeds the very first invoice's Previous Invoice Hash (PIH) with a
# well-known constant rather than an empty string. We use a clearly-marked
# placeholder genesis value with the same shape (base64 of a SHA-256 digest)
# rather than ZATCA's exact published constant, consistent with this
# module's "not byte-compatible with the real authority" disclaimer.
GENESIS_HASH = base64.b64encode(hashlib.sha256(b"ERP-NUCLEUS-ZATCA-GENESIS").digest()).decode("ascii")


def compute_invoice_hash(canonical_content: str, previous_hash: str) -> str:
    """Returns base64(SHA-256(previous_hash || canonical_content))."""
    digest_input = (previous_hash + canonical_content).encode("utf-8")
    digest = hashlib.sha256(digest_input).digest()
    return base64.b64encode(digest).decode("ascii")
