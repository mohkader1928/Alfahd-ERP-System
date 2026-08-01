"""ZATCA QR code payload: TLV (Tag-Length-Value) encoding, Base64-wrapped
(FR-ZATCA-006). This is the one piece of the ZATCA spec implementable
byte-correctly without any authority-issued credentials — the published
TLV tag numbers and structure are public.

Tags 1-6 (Phase 1 fields) are populated for real. Tags 7-9 (ECDSA
signature, public key, CA signature over the public key — Phase 2 fields)
require a real CSID certificate and are emitted as zero-length placeholders,
clearly marked, rather than omitted, so a future real-cert implementation
only needs to fill in the value bytes.
"""

import base64
from decimal import Decimal

TAG_SELLER_NAME = 1
TAG_VAT_NUMBER = 2
TAG_TIMESTAMP = 3
TAG_INVOICE_TOTAL = 4
TAG_VAT_AMOUNT = 5
TAG_INVOICE_HASH = 6
TAG_ECDSA_SIGNATURE = 7  # Phase 2 — placeholder, requires CSID
TAG_ECDSA_PUBLIC_KEY = 8  # Phase 2 — placeholder, requires CSID
TAG_CA_SIGNATURE = 9  # Phase 2 — placeholder, requires CSID


def _tlv(tag: int, value: bytes) -> bytes:
    if len(value) > 255:
        raise ValueError(f"TLV value for tag {tag} exceeds 255 bytes ({len(value)})")
    return bytes([tag, len(value)]) + value


def build_qr_payload(
    *,
    seller_name: str,
    vat_number: str,
    timestamp_iso: str,
    invoice_total: Decimal,
    vat_amount: Decimal,
    invoice_hash_b64: str,
    include_phase2_placeholders: bool = False,
) -> str:
    tlvs = [
        _tlv(TAG_SELLER_NAME, seller_name.encode("utf-8")),
        _tlv(TAG_VAT_NUMBER, vat_number.encode("utf-8")),
        _tlv(TAG_TIMESTAMP, timestamp_iso.encode("utf-8")),
        _tlv(TAG_INVOICE_TOTAL, str(invoice_total).encode("utf-8")),
        _tlv(TAG_VAT_AMOUNT, str(vat_amount).encode("utf-8")),
        _tlv(TAG_INVOICE_HASH, invoice_hash_b64.encode("utf-8")),
    ]
    if include_phase2_placeholders:
        tlvs += [
            _tlv(TAG_ECDSA_SIGNATURE, b""),
            _tlv(TAG_ECDSA_PUBLIC_KEY, b""),
            _tlv(TAG_CA_SIGNATURE, b""),
        ]

    payload = b"".join(tlvs)
    return base64.b64encode(payload).decode("ascii")
