"""JWT issuance/validation (FR-CORE-010)."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt

from src.shared.config.settings import get_settings

settings = get_settings()


class TokenError(Exception):
    pass


def create_access_token(*, user_id: UUID, tenant_id: UUID, authorized_companies: list[str]) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "authorized_companies": authorized_companies,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(*, user_id: UUID) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(days=settings.jwt_refresh_token_expire_days),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as e:
        raise TokenError("Token expired") from e
    except jwt.InvalidTokenError as e:
        raise TokenError("Invalid token") from e
