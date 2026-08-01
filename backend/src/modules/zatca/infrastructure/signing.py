"""Cryptographic Stamp placeholder (FR-ZATCA-005).

A real Cryptographic Stamp is an ECDSA (secp256k1) signature produced with
a device private key whose public key is certified by ZATCA via a CSID
issued through the Fatoora onboarding flow — none of which exists in this
environment (see Phase 1 §7, module docstring). `DevSigningService` below
produces a deterministic HMAC-SHA256 "stamp" over the canonical XML instead,
satisfying the code's interface (something that changes if the document
changes, verifiable with a known key) but is NOT a real Cryptographic Stamp
and must never be treated as one outside local development/testing.
"""

import base64
import hashlib
import hmac
from typing import Protocol


class ISigningService(Protocol):
    def stamp(self, canonical_xml: str) -> str: ...


class DevSigningService:
    """NOT PRODUCTION-SAFE. Replace with a real ZATCA CSID-based signer
    before any production use."""

    def __init__(self, dev_signing_key: bytes = b"erp-nucleus-dev-signing-key-do-not-use-in-prod"):
        self._key = dev_signing_key

    def stamp(self, canonical_xml: str) -> str:
        mac = hmac.new(self._key, canonical_xml.encode("utf-8"), hashlib.sha256).digest()
        return base64.b64encode(mac).decode("ascii")
