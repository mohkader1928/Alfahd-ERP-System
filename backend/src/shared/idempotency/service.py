"""Reusable Idempotency-Key guard (docs/16b, Proposed Idempotency
Architecture). Usage at a route:

    guard = await begin_idempotent_request(
        repo, company_id=ctx.company_id, user_id=ctx.user_id,
        endpoint="POST /sales/invoices/{id}:credit-note",
        idempotency_key=idempotency_key_header, body=payload.model_dump(mode="json"),
    )
    if isinstance(guard, IdempotentReplay):
        return JSONResponse(status_code=guard.response_status, content=guard.response_body)
    # ... business logic ...
    if guard is not None:
        await repo.mark_completed(guard, response_status=201, response_body=response.model_dump(mode="json"))

`idempotency_key` being None (header omitted) is the default, backward-
compatible path: `begin_idempotent_request` returns None and the caller
proceeds exactly as before, no idempotency row created at all.
"""

import hashlib
import json
from typing import Any
from uuid import UUID

from src.shared.idempotency.models import IdempotencyKeyRecord
from src.shared.idempotency.repositories import (
    IdempotencyKeyAlreadyInserted,
    IdempotencyKeyRepository,
)


class IdempotencyKeyConflictError(Exception):
    """Same (company, key, endpoint) reused with a different request body."""


class IdempotentReplay:
    """Not an error — the stored response from a prior identical request,
    to be returned verbatim instead of re-running the business logic."""

    def __init__(self, response_status: int, response_body: dict[str, Any]):
        self.response_status = response_status
        self.response_body = response_body


def _hash_request(body: Any) -> str:
    canonical = json.dumps(body, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


async def begin_idempotent_request(
    repo: IdempotencyKeyRepository,
    *,
    company_id: UUID,
    user_id: UUID,
    endpoint: str,
    idempotency_key: str | None,
    body: Any,
) -> IdempotencyKeyRecord | IdempotentReplay | None:
    if idempotency_key is None:
        return None

    request_hash = _hash_request(body)
    row = await repo.get_for_update(company_id, idempotency_key, endpoint)

    if row is None:
        try:
            return await repo.create_in_progress(
                company_id=company_id, user_id=user_id, key=idempotency_key, endpoint=endpoint, request_hash=request_hash
            )
        except IdempotencyKeyAlreadyInserted:
            # The INSERT-side half of the same race the row lock above
            # can't cover (no row exists yet for FOR UPDATE to lock): our
            # insert only fails this way once the other transaction that
            # beat us to it has already committed in full — so re-reading
            # now is guaranteed to see its finished, completed row.
            row = await repo.get_for_update(company_id, idempotency_key, endpoint)
            if row is None:
                raise IdempotencyKeyConflictError(
                    "A request with this Idempotency-Key is already being processed"
                ) from None

    if row.request_hash != request_hash:
        raise IdempotencyKeyConflictError("Idempotency-Key already used with a different request")

    if row.status == "completed":
        return IdempotentReplay(row.response_status, row.response_body)

    # status == "in_progress": since get_for_update takes a row lock, a
    # genuinely concurrent duplicate blocks above until the first request's
    # transaction resolves. Reaching this branch after unblocking means the
    # first request is still mid-flight in a way that outlived its own
    # transaction (should not happen given the route always completes or
    # rolls back the row within one transaction) — surfaced as a conflict
    # rather than silently re-running the business logic twice.
    raise IdempotencyKeyConflictError("A request with this Idempotency-Key is already being processed")
