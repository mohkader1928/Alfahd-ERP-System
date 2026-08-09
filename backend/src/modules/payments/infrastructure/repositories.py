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
        result = await self.session.execute(
            query.order_by(Payment.payment_date.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def next_number(self, company_id: UUID, payment_type: str) -> str:
        # Customer receipts and vendor payments are visibly distinct
        # documents (Owner directive) -- each gets its own prefix and its
        # own sequence scoped to (company_id, payment_type), not one
        # shared counter that left gaps in either series wherever the
        # other type fell in between.
        result = await self.session.execute(
            select(func.count()).where(
                Payment.company_id == company_id, Payment.payment_type == payment_type
            )
        )
        count = result.scalar_one()
        prefix = "RCT" if payment_type == "customer" else "PAY"
        return f"{prefix}-{count + 1:06d}"

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

    async def list_allocations_for_partner(
        self, company_id: UUID, partner_id: UUID, payment_type: str
    ) -> list[dict]:
        """Milestone 1b — every allocation belonging to one partner's
        payments, each carrying its payment's own date/number/reference and
        which document (sales invoice or vendor bill) it settled -- the raw
        material for that partner's Subledger. Joined rather than fetched
        via `get_allocations` per-payment so a partner with many payments
        costs one query, not N+1."""
        result = await self.session.execute(
            select(
                PaymentAllocation.sales_invoice_id,
                PaymentAllocation.vendor_bill_id,
                PaymentAllocation.amount,
                Payment.id.label("payment_id"),
                Payment.number,
                Payment.payment_date,
                Payment.reference,
            )
            .join(Payment, Payment.id == PaymentAllocation.payment_id)
            .where(
                Payment.company_id == company_id,
                Payment.partner_id == partner_id,
                Payment.payment_type == payment_type,
            )
            .order_by(Payment.payment_date)
        )
        return [
            {
                "sales_invoice_id": row.sales_invoice_id,
                "vendor_bill_id": row.vendor_bill_id,
                "amount": Decimal(row.amount),
                "payment_id": row.payment_id,
                "number": row.number,
                "payment_date": row.payment_date,
                "reference": row.reference,
            }
            for row in result.all()
        ]

    async def list_unallocated_payments_for_partner(
        self, company_id: UUID, partner_id: UUID, payment_type: str
    ) -> list[dict]:
        """P0-3 live-testing finding (شركة المحمود): list_allocations_for_partner
        above INNER JOINs to payment_allocation, so a payment recorded fully
        or partially on-account -- a real, posted, GL-affecting payment with
        no (or not yet a full) invoice/bill allocation -- silently
        disappeared from the customer/vendor Subledger entirely, even
        though the Sales-by-Customer/Purchases-by-Supplier reports' own
        payment totals (summed directly from Payment.amount, not via
        allocations) already counted it correctly. Returns each such
        payment's un-allocated remainder so the Subledger can show it too."""
        remainder = Payment.amount - func.coalesce(func.sum(PaymentAllocation.amount), 0)
        result = await self.session.execute(
            select(
                Payment.id.label("payment_id"),
                Payment.number,
                Payment.payment_date,
                Payment.reference,
                remainder.label("remainder"),
            )
            .select_from(Payment)
            .outerjoin(PaymentAllocation, PaymentAllocation.payment_id == Payment.id)
            .where(
                Payment.company_id == company_id,
                Payment.partner_id == partner_id,
                Payment.payment_type == payment_type,
            )
            .group_by(Payment.id, Payment.number, Payment.payment_date, Payment.reference, Payment.amount)
            .having(remainder > 0)
            .order_by(Payment.payment_date)
        )
        return [
            {
                "payment_id": row.payment_id,
                "number": row.number,
                "payment_date": row.payment_date,
                "reference": row.reference,
                "remainder": Decimal(str(row.remainder)),
            }
            for row in result.all()
        ]
