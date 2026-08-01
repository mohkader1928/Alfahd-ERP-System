"""Unit of Work — one transaction per application-service use case (Phase 8 §7)."""

from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession


class UnitOfWork:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            await self.session.rollback()
        # No implicit commit here — the calling application service commits
        # explicitly after all repository writes succeed, keeping the
        # transaction boundary visible at the use-case level, not hidden here.

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
