"""Repository implementations for Purchasing (Phase 8 §7)."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import case, delete, func, select
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

    async def replace_lines(self, order_id: UUID, lines: list[PurchaseOrderLine]) -> None:
        """Full replace, not a diff — only ever called against a still-draft
        order, where qty_received/qty_billed are guaranteed zero on every
        existing line (nothing can be received or billed before
        confirmation), so there's no downstream figure a line-level diff
        would need to preserve."""
        await self.session.execute(delete(PurchaseOrderLine).where(PurchaseOrderLine.purchase_order_id == order_id))
        for line in lines:
            line.purchase_order_id = order_id
            self.session.add(line)
        await self.session.flush()

    async def get_line_by_id(self, line_id: UUID) -> PurchaseOrderLine | None:
        result = await self.session.execute(select(PurchaseOrderLine).where(PurchaseOrderLine.id == line_id))
        return result.scalar_one_or_none()

    async def get_line_by_id_for_update(self, line_id: UUID) -> PurchaseOrderLine | None:
        """Same lookup as `get_line_by_id`, but row-locked — for the goods
        receipt / vendor bill registration paths that read `qty_received`/
        `qty_billed` and write it back in the same transaction. Without
        this, two concurrent receipts (or bills) against the same PO line
        can both read the same cumulative qty and both pass the
        not-over-ordered check, over-receiving/over-billing past what was
        actually ordered (docs/16b, finding #4).

        `populate_existing=True` is required, not optional: `register_bill`
        and `record_goods_receipt` both call `get_line_by_id` (unlocked) on
        this same line earlier in the same request, before reaching this
        locked call. Without `populate_existing`, SQLAlchemy's identity map
        returns that *earlier* Python object once the lock is acquired,
        with its stale pre-lock qty_received/qty_billed still attached —
        the lock itself blocks correctly, but the attribute values read
        back are wrong, silently under-counting qty_billed/qty_received
        under real concurrent load (a lost-update bug, found while adding
        the identical pattern to Sales — see the equivalent fix and its
        test in SalesOrderRepository.get_line_by_id_for_update)."""
        result = await self.session.execute(
            select(PurchaseOrderLine)
            .where(PurchaseOrderLine.id == line_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
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

    async def list_by_company_page(
        self,
        company_id: UUID,
        *,
        status: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[PurchaseOrder], int]:
        """List-view server-side filtering (Product Owner audit, same
        pattern established for Sales Invoices) — real LIMIT/OFFSET plus
        a matching COUNT(*) so the list screen is never silently capped
        as the company's order history grows."""
        conditions = [PurchaseOrder.company_id == company_id]
        if status is not None:
            conditions.append(PurchaseOrder.status == status)
        if date_from is not None:
            conditions.append(PurchaseOrder.order_date >= date_from)
        if date_to is not None:
            conditions.append(PurchaseOrder.order_date <= date_to)

        count_result = await self.session.execute(select(func.count()).select_from(PurchaseOrder).where(*conditions))
        total = count_result.scalar_one()

        rows_result = await self.session.execute(
            select(PurchaseOrder)
            .where(*conditions)
            .order_by(PurchaseOrder.order_date.desc(), PurchaseOrder.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(rows_result.scalars().all()), total


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

    async def numbers_for_lines(self, line_ids: list[UUID]) -> dict[UUID, str]:
        """Owner request (Product Cardex detail): a `stock_move` whose
        `source_table` is "goods_receipt_line" carries a GoodsReceiptLine id
        in `source_id`, not the receipt itself -- this joins through to the
        parent GoodsReceipt's own `number` in one batched query rather than
        one lookup per cardex line."""
        if not line_ids:
            return {}
        result = await self.session.execute(
            select(GoodsReceiptLine.id, GoodsReceipt.number)
            .join(GoodsReceipt, GoodsReceipt.id == GoodsReceiptLine.goods_receipt_id)
            .where(GoodsReceiptLine.id.in_(line_ids))
        )
        return {row[0]: row[1] for row in result.all()}


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

    async def numbers_for_ids(self, bill_ids: list[UUID]) -> dict[UUID, str]:
        """Owner request (Product Cardex detail): batch id->number lookup
        for a set of bills/debit notes, mirroring
        SalesInvoiceRepository.numbers_for_ids."""
        if not bill_ids:
            return {}
        result = await self.session.execute(select(VendorBill.id, VendorBill.number).where(VendorBill.id.in_(bill_ids)))
        return {row[0]: row[1] for row in result.all()}

    async def get_by_id_for_update(self, bill_id: UUID) -> VendorBill | None:
        """Phase 17D: row-locked read, used only by PaymentService's
        allocation check — see SalesInvoiceRepository.get_by_id_for_update
        for the concurrency rationale."""
        result = await self.session.execute(select(VendorBill).where(VendorBill.id == bill_id).with_for_update())
        return result.scalar_one_or_none()

    async def get_lines(self, bill_id: UUID) -> list[VendorBillLine]:
        result = await self.session.execute(select(VendorBillLine).where(VendorBillLine.vendor_bill_id == bill_id))
        return list(result.scalars().all())

    async def replace_lines(self, bill_id: UUID, lines: list[VendorBillLine]) -> None:
        """Full replace, not a diff — only ever called against a bill still
        in 'matched'/'mismatched' status (not yet approved/posted), so no
        JE or downstream figure depends on any existing line's own id."""
        await self.session.execute(delete(VendorBillLine).where(VendorBillLine.vendor_bill_id == bill_id))
        for line in lines:
            line.vendor_bill_id = bill_id
            self.session.add(line)
        await self.session.flush()

    async def next_number(self, company_id: UUID, bill_type: str = "standard") -> str:
        """Owner request: a Purchase Return must read as its own document
        type, not just another bill interleaved in the same series --
        mirrors the precedent already set for Payments (RCT-/PAY-, scoped
        by payment_type). A debit note gets its own DN- prefix; standard
        bills keep the BILL- prefix exactly as before.

        MUST be based on the highest existing NUMBER actually carrying
        this prefix, not a COUNT of same-type rows -- see
        SalesInvoiceRepository.next_number's docstring for the exact live
        collision (INV-000079) this same COUNT-based approach caused on a
        real company's interleaved historical data. Scanning existing
        BILL-prefixed numbers for their real max can never re-issue one
        that's already taken."""
        prefix = "DN" if bill_type == "debit_note" else "BILL"
        result = await self.session.execute(
            select(VendorBill.number).where(
                VendorBill.company_id == company_id, VendorBill.number.like(f"{prefix}-%")
            )
        )
        max_seq = 0
        for (number,) in result.all():
            suffix = number.split("-", 1)[1] if "-" in number else ""
            if suffix.isdigit():
                max_seq = max(max_seq, int(suffix))
        return f"{prefix}-{max_seq + 1:06d}"

    async def list_by_company(self, company_id: UUID, *, partner_id: UUID | None = None) -> list[VendorBill]:
        query = select(VendorBill).where(VendorBill.company_id == company_id)
        if partner_id is not None:
            query = query.where(VendorBill.partner_id == partner_id)
        result = await self.session.execute(query.order_by(VendorBill.bill_date.desc()))
        return list(result.scalars().all())

    async def list_by_company_page(
        self,
        company_id: UUID,
        *,
        partner_id: UUID | None = None,
        status: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        bill_type: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[VendorBill], int]:
        """List-view server-side filtering (Product Owner audit, same
        pattern established for Sales Invoices) — real LIMIT/OFFSET plus
        a matching COUNT(*) so the list screen is never silently capped
        as the company's bill history grows. `bill_type` (P0-9) backs
        the dedicated Purchase Returns screen, which asks for
        `bill_type=debit_note` only."""
        conditions = [VendorBill.company_id == company_id]
        if partner_id is not None:
            conditions.append(VendorBill.partner_id == partner_id)
        if status is not None:
            conditions.append(VendorBill.status == status)
        if date_from is not None:
            conditions.append(VendorBill.bill_date >= date_from)
        if date_to is not None:
            conditions.append(VendorBill.bill_date <= date_to)
        if bill_type is not None:
            conditions.append(VendorBill.bill_type == bill_type)

        count_result = await self.session.execute(select(func.count()).select_from(VendorBill).where(*conditions))
        total = count_result.scalar_one()

        rows_result = await self.session.execute(
            select(VendorBill)
            .where(*conditions)
            .order_by(VendorBill.bill_date.desc(), VendorBill.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(rows_result.scalars().all()), total

    async def sum_total_in_range(self, company_id: UUID, date_from: date, date_to: date) -> Decimal:
        """FR-RPT-003 — Dashboard's period/trend purchases KPI. Owner
        request: this must be NET purchases -- standard bills minus Vendor
        Debit Notes (returns to the vendor) issued in the same period. A
        debit note is stored with the same positive `total_amount` as the
        bill it reverses, so it is subtracted explicitly rather than
        simply excluded (an earlier version of this fix excluded debit
        notes entirely, which undercounts a period containing a return
        without also containing its original bill). Only posted bills
        count as a real purchase commitment (draft/mismatched bills
        aren't yet approved)."""
        result = await self.session.execute(
            select(
                func.coalesce(
                    func.sum(
                        case(
                            (VendorBill.bill_type == "debit_note", -VendorBill.total_amount),
                            else_=VendorBill.total_amount,
                        )
                    ),
                    0,
                )
            ).where(
                VendorBill.company_id == company_id,
                VendorBill.bill_date >= date_from,
                VendorBill.bill_date <= date_to,
                VendorBill.status == "posted",
            )
        )
        # Same COALESCE-scale quirk as Sales' sum_total_in_range — see that
        # method's comment.
        return Decimal(result.scalar_one()).quantize(Decimal("0.0001"))
