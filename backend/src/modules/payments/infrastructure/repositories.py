from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.payments.infrastructure.models import Payment, PaymentAllocation


class PaymentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, payment: Payment, allocations: list[PaymentAllocation]) -> Payment:
        self.session.add(payment)
        await self.session.flush()
        for allocation in allocations:
            allocation.payment_id = payment.id
            self.session.add(allocation)
        await self.session.flush()
        return payment

    async def get_by_id(self, payment_id: UUID) -> Payment | None:
        result = await self.session.execute(select(Payment).where(Payment.id == payment_id))
        return result.scalar_one_or_none()

    async def get_allocations(self, payment_id: UUID) -> list[PaymentAllocation]:
        result = await self.session.execute(
            select(PaymentAllocation).where(PaymentAllocation.payment_id == payment_id)
        )
        return list(result.scalars().all())

    async def list_by_company(
        self, company_id: UUID, *, payment_type: str | None = None, limit: int = 200
    ) -> list[Payment]:
        query = select(Payment).where(Payment.company_id == company_id)
        if payment_type is not None:
            query = query.where(Payment.payment_type == payment_type)
        result = await self.session.execute(query.order_by(Payment.payment_date.desc()).limit(limit))
        return list(result.scalars().all())

    async def next_number(self, company_id: UUID) -> str:
        result = await self.session.execute(select(func.count()).where(Payment.company_id == company_id))
        count = result.scalar_one()
        return f"PAY-{count + 1:06d}"

    async def sum_allocated_for_sales_invoice(self, sales_invoice_id: UUID) -> Decimal:
        result = await self.session.execute(
            select(func.coalesce(func.sum(PaymentAllocation.amount), 0)).where(
                PaymentAllocation.sales_invoice_id == sales_invoice_id
            )
        )
        return result.scalar_one()

    async def sum_allocated_for_vendor_bill(self, vendor_bill_id: UUID) -> Decimal:
        result = await self.session.execute(
            select(func.coalesce(func.sum(PaymentAllocation.amount), 0)).where(
                PaymentAllocation.vendor_bill_id == vendor_bill_id
            )
        )
        return result.scalar_one()
