import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.idempotency.models import IdempotencyKeyRecord

EXPIRY_WINDOW = timedelta(hours=24)


class IdempotencyKeyAlreadyInserted(Exception):
    """Raised when the INSERT itself hit the unique constraint — a second
    concurrent request whose INSERT was blocked behind the first one's
    still-uncommitted row, and only failed once that first transaction
    committed. The `SELECT ... FOR UPDATE` row lock alone can't catch this
    case (there is no row to lock until someone inserts one); this is the
    INSERT-side half of the same race."""


class IdempotencyKeyRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_for_update(self, company_id: UUID, key: str, endpoint: str) -> IdempotencyKeyRecord | None:
        """SELECT ... FOR UPDATE within the caller's existing transaction —
        a genuinely concurrent second request with the same key blocks here
        until the first resolves, rather than racing past this check (see
        docs/16b, Proposed Idempotency Architecture)."""
        result = await self.session.execute(
            select(IdempotencyKeyRecord)
            .where(
                IdempotencyKeyRecord.company_id == company_id,
                IdempotencyKeyRecord.idempotency_key == key,
                IdempotencyKeyRecord.endpoint == endpoint,
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def create_in_progress(
        self, *, company_id: UUID, user_id: UUID, key: str, endpoint: str, request_hash: str
    ) -> IdempotencyKeyRecord:
        row = IdempotencyKeyRecord(
            id=uuid.uuid4(),
            company_id=company_id,
            user_id=user_id,
            idempotency_key=key,
            endpoint=endpoint,
            request_hash=request_hash,
            status="in_progress",
            expires_at=datetime.now(UTC).replace(tzinfo=None) + EXPIRY_WINDOW,
        )
        try:
            # SAVEPOINT: this request's overall transaction (the same
            # session the route commits once at the end) must stay usable
            # even if this one INSERT fails — a plain flush() failure here
            # would otherwise poison the entire outer transaction.
            async with self.session.begin_nested():
                self.session.add(row)
                await self.session.flush()
        except IntegrityError as e:
            # The nested transaction (SAVEPOINT) rollback above already
            # reverts this row's insert and detaches it from the session.
            raise IdempotencyKeyAlreadyInserted(
                "Another request already inserted this Idempotency-Key"
            ) from e
        return row

    async def mark_completed(self, row: IdempotencyKeyRecord, *, response_status: int, response_body: dict[str, Any]) -> None:
        row.status = "completed"
        row.response_status = response_status
        row.response_body = response_body
        await self.session.flush()
