"""TOTP-based Two-Factor Authentication (FR-CORE-011)."""

import pyotp


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def get_provisioning_uri(secret: str, email: str, issuer: str = "Saudi ERP") -> str:
    return pyotp.totp.TOTP(secret).provisioning_uri(name=email, issuer_name=issuer)


def verify_totp_code(secret: str, code: str) -> bool:
    return pyotp.totp.TOTP(secret).verify(code, valid_window=1)
