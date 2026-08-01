"""Password hashing (Argon2, per NFR-SEC-002) and policy checks (FR-CORE-012)."""

import re

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_hasher = PasswordHasher()

MIN_LENGTH = 10
_COMPLEXITY_PATTERN = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^\w\s]).+$")


class WeakPasswordError(ValueError):
    pass


def validate_password_policy(plain_password: str) -> None:
    if len(plain_password) < MIN_LENGTH:
        raise WeakPasswordError(f"Password must be at least {MIN_LENGTH} characters long")
    if not _COMPLEXITY_PATTERN.match(plain_password):
        raise WeakPasswordError(
            "Password must include uppercase, lowercase, a digit, and a symbol"
        )


def hash_password(plain_password: str) -> str:
    return _hasher.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, plain_password)
    except VerifyMismatchError:
        return False
