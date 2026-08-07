"""Repository implementations for Purchasing (Phase 8 §7)."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.purchasing.infrastructure.models import (
    GoodsReceipt,
    GoodsReceiptLine,
    PurchaseOrder,
    PurchaseOrderLine,
    VendorBill,
    VendorBillLine,
)


class PurchaseOrderRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, order: PurchaseOrder, lines: list[PurchaseOrderLine]) -> PurchaseOrder:
        self.session.add(order)
        await self.session.flush()
        for line in lines:
            line.purchase_order_id = order.id
            self.session.add(line)
        await self.session.flush()
        return order

    async def get_by_id(self, order_id: UUID) -> PurchaseOrder | None:
        result = await self.session.execute(select(PurchaseOrder).where(PurchaseOrder.id == order_id))
        return result.scalar_one_or_none()

    async def get_lines(self, order_id: UUID) -> list[PurchaseOrderLine]:
        result = await self.session.execute(
            select(PurchaseOrderLine).where(PurchaseOrderLine.purchase_order_id == order_id)
        )
        return list(result.scalars().all())

    async def get_line_by_id(self, line_id: UUID) -> PurchaseOrderLine | None:
        result = await self.session.execute(select(PurchaseOrderLine).where(PurchaseOrderLine.id == line_id))
        return result.scalar_one_or_none()

    async def next_number(self, company_id: UUID) -> str:
        result = await self.session.execute(select(func.count()).where(PurchaseOrder.company_id == company_id))
        count = result.scalar_one()
        return f"PO-{count + 1:06d}"

    async def list_by_company(self, company_id: UUID, *, status: str | None = None) -> list[PurchaseOrder]:
        query = select(PurchaseOrder).where(PurchaseOrder.company_id == company_id)
        if status is not None:
            query = query.where(PurchaseOrder.status == status)
        result = await self.session.execute(query.order_by(PurchaseOrder.order_date.desc()))
        return list(result.scalars().all())


class GoodsReceiptRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, receipt: GoodsReceipt, lines: list[GoodsReceiptLine]) -> GoodsReceipt:
        self.session.add(receipt)
        await self.session.flush()
        for line in lines:
            line.goods_receipt_id = receipt.id
            self.session.add(line)
        await self.session.flush()
        return receipt

    async def get_by_id(self, receipt_id: UUID) -> GoodsReceipt | None:
        result = await self.session.execute(select(GoodsReceipt).where(GoodsReceipt.id == receipt_id))
        return result.scalar_one_or_none()

    async def get_lines(self, receipt_id: UUID) -> list[GoodsReceiptLine]:
        result = await self.session.execute(
            select(GoodsReceiptLine).where(GoodsReceiptLine.goods_receipt_id == receipt_id)
        )
        return list(result.scalars().all())

    async def sum_received_qty_for_po_line(self, po_line_id: UUID) -> Decimal:
        result = await self.session.execute(
            select(func.coalesce(func.sum(GoodsReceiptLine.qty), 0)).where(
                GoodsReceiptLine.purchase_order_line_id == po_line_id
            )
        )
        return result.scalar_one()

    async def next_number(self, company_id: UUID) -> str:
        result = await self.session.execute(select(func.count()).where(GoodsReceipt.company_id == company_id))
        count = result.scalar_one()
        return f"GR-{count + 1:06d}"


class VendorBillRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, bill: VendorBill, lines: list[VendorBillLine]) -> VendorBill:
        self.session.add(bill)
        await self.session.flush()
        for line in lines:
            line.vendor_bill_id = bill.id
            self.session.add(line)
        await self.session.flush()
        return bill

    async def get_by_id(self, bill_id: UUID) -> VendorBill | None:
        result = await self.session.execute(select(VendorBill).where(VendorBill.id == bill_id))
        return result.scalar_one_or_none()

    async def get_by_id_for_update(self, bill_id: UUID) -> VendorBill | None:
        """Phase 17D: row-locked read, used only by PaymentService's
        allocation check — see SalesInvoiceRepository.get_by_id_for_update
        for the concurrency rationale."""
        result = await self.session.execute(select(VendorBill).where(VendorBill.id == bill_id).with_for_update())
        return result.scalar_one_or_none()

    async def get_lines(self, bill_id: UUID) -> list[VendorBillLine]:
        result = await self.session.execute(select(VendorBillLine).where(VendorBillLine.vendor_bill_id == bill_id))
        return list(result.scalars().all())

    async def next_number(self, company_id: UUID) -> str:
        result = await self.session.execute(select(func.count()).where(VendorBill.company_id == company_id))
        count = result.scalar_one()
        return f"BILL-{count + 1:06d}"

    async def list_by_company(self, company_id: UUID, *, partner_id: UUID | None = None) -> list[VendorBill]:
        query = select(VendorBill).where(VendorBill.company_id == company_id)
        if partner_id is not None:
            query = query.where(VendorBill.partner_id == partner_id)
        result = await self.session.execute(query.order_by(VendorBill.bill_date.desc()))
        return list(result.scalars().all())

    async def sum_total_in_range(self, company_id: UUID, date_from: date, date_to: date) -> Decimal:
        """FR-RPT-003 — period purchases KPI. Only posted bills count as a
        real purchase commitment (draft/mismatched bills aren't yet approved)."""
        result = await self.session.execute(
            select(func.coalesce(func.sum(VendorBill.total_amount), 0)).where(
                VendorBill.company_id == company_id,
                VendorBill.bill_date >= date_from,
                VendorBill.bill_date <= date_to,
                VendorBill.status == "posted",
            )
        )
        # Same COALESCE-scale quirk as Sales' sum_total_in_range — see that
        # method's comment.
        return Decimal(result.scalar_one()).quantize(Decimal("0.0001"))
