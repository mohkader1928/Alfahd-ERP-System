import uuid
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.commission.infrastructure.models import CommissionTransaction


class CommissionTransactionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, txn: CommissionTransaction) -> None:
        self.session.add(txn)
        await self.session.flush()

    async def get_by_source(
        self, *, company_id: UUID, source_table: str, source_id: uuid.UUID, commission_type: str
    ) -> CommissionTransaction | None:
        stmt = select(CommissionTransaction).where(
            CommissionTransaction.company_id == company_id,
            CommissionTransaction.source_table == source_table,
            CommissionTransaction.source_id == source_id,
            CommissionTransaction.commission_type == commission_type,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
