"""Application services (use-case orchestration) for Purchasing, Phase 8 §2.

Purchasing depends on Identity, Inventory, and Accounting per the Phase 8 §3
module map — same "legitimate direct dependency" pattern Sales uses.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from src.modules.accounting.application.services import JournalEntryService
from src.modules.accounting.infrastructure.repositories import AccountRepository
from src.modules.identity.infrastructure.repositories import (
    CompanyRepository,
    PartnerRepository,
    ProductRepository,
    RoleRepository,
)
from src.modules.inventory.application.services import InventoryValuationService
from src.modules.inventory.infrastructure.repositories import (
    LocationRepository,
    WarehouseRepository,
)
from src.modules.notifications.infrastructure.repositories import NotificationRepository
from src.modules.purchasing.domain.entities import (
    MatchLine,
    ThreeWayMatchError,
    check_three_way_match,
)
from src.modules.purchasing.infrastructure.models import (
    GoodsReceipt,
    GoodsReceiptLine,
    PurchaseOrder,
    PurchaseOrderLine,
    VendorBill,
    VendorBillLine,
)
from src.modules.purchasing.infrastructure.repositories import (
    GoodsReceiptRepository,
    PurchaseOrderRepository,
    VendorBillRepository,
)

APPROVE_PERMISSION_CODE = "purchasing.order.approve"

ACCOUNT_CODE_INVENTORY = "1300"
ACCOUNT_CODE_GRNI = "2300"  # Goods Received Not Invoiced
ACCOUNT_CODE_AP = "2100"
ACCOUNT_CODE_VAT = "2200"  # shared control account for output + input VAT


class PurchaseOrderService:
    """UC-PUR-01 (part 1) — create, confirm, approve and reject a Purchase
    Order.

    Approval Workflow (FR-CORE-052, "PO amount exceeds threshold"): if the
    company has set `po_approval_threshold` and this PO's total exceeds it,
    confirming routes the order to `pending_approval` instead of
    auto-confirming, and every user holding `purchasing.order.approve` in
    this company (except the PO's own creator) gets notified. Approving or
    rejecting notifies the creator back. A company with no threshold set
    keeps the original auto-confirm behavior unchanged — this is additive,
    not a breaking change to existing companies.
    """

    def __init__(
        self,
        order_repo: PurchaseOrderRepository,
        company_repo: CompanyRepository | None = None,
        role_repo: RoleRepository | None = None,
        notification_repo: NotificationRepository | None = None,
        product_repo: ProductRepository | None = None,
    ):
        self.order_repo = order_repo
        self.company_repo = company_repo
        self.role_repo = role_repo
        self.notification_repo = notification_repo
        self.product_repo = product_repo

    async def create_purchase_order(
        self,
        *,
        company_id: UUID,
        branch_id: UUID,
        partner_id: UUID,
        order_date: date,
        lines: list[dict],
        created_by: UUID | None = None,
    ) -> PurchaseOrder:
        if not lines:
            raise ValueError("A purchase order needs at least one line")
        number = await self.order_repo.next_number(company_id)
        total = sum((Decimal(str(line["qty"])) * Decimal(str(line["unit_price"])) for line in lines), Decimal("0"))

        order = PurchaseOrder(
            id=uuid.uuid4(),
            company_id=company_id,
            branch_id=branch_id,
            partner_id=partner_id,
            number=number,
            status="draft",
            order_date=order_date,
            total_amount=total,
            created_by_user_id=created_by,
        )
        orm_lines = [
            PurchaseOrderLine(
                id=uuid.uuid4(),
                company_id=company_id,
                product_id=line["product_id"],
                qty=Decimal(str(line["qty"])),
                unit_price=Decimal(str(line["unit_price"])),
                tax_rate_id=line["tax_rate_id"],
            )
            for line in lines
        ]
        try:
            created = await self.order_repo.add(order, orm_lines)
        except IntegrityError as e:
            # Belt-and-suspenders against the count(*)+1 numbering race
            # (docs/16b): the partial unique index is the actual guarantee
            # against a duplicate number; this only translates its
            # violation into a clean, retryable error instead of a raw 500.
            raise ValueError("A purchase order was created concurrently with the same number — please retry") from e

        # Owner-requested: the next Purchase Order for this product should
        # default to what was just paid for it, not start from 0 again.
        # A UI convenience cache (last write wins), not an audited figure.
        if self.product_repo is not None:
            for line in lines:
                product = await self.product_repo.get_by_id(line["product_id"])
                if product is not None and product.company_id == company_id:
                    product.last_purchase_price = Decimal(str(line["unit_price"]))
        return created

    async def confirm_purchase_order(self, *, order_id: UUID, company_id: UUID) -> PurchaseOrder:
        order = await self.order_repo.get_by_id(order_id)
        if order is None or order.company_id != company_id:
            raise ValueError("Purchase order not found")
        if order.status != "draft":
            raise ValueError("Only a draft purchase order can be confirmed")

        threshold = None
        if self.company_repo is not None:
            company = await self.company_repo.get_by_id(company_id)
            threshold = company.po_approval_threshold if company else None

        if threshold is not None and order.total_amount > threshold:
            order.status = "pending_approval"
            order.approval_status = "pending"
            await self._notify_approvers(order)
        else:
            order.status = "confirmed"
        return order

    async def approve_purchase_order(self, *, order_id: UUID, company_id: UUID, approved_by: UUID) -> PurchaseOrder:
        order = await self.order_repo.get_by_id(order_id)
        if order is None or order.company_id != company_id:
            raise ValueError("Purchase order not found")
        if order.status != "pending_approval":
            raise ValueError("Only a purchase order pending approval can be approved")
        order.status = "confirmed"
        order.approval_status = "approved"
        order.approved_by = approved_by
        order.approved_at = datetime.now(UTC).replace(tzinfo=None)
        await self._notify_creator(order, approved=True)
        return order

    async def reject_purchase_order(
        self, *, order_id: UUID, company_id: UUID, rejected_by: UUID, reason: str
    ) -> PurchaseOrder:
        order = await self.order_repo.get_by_id(order_id)
        if order is None or order.company_id != company_id:
            raise ValueError("Purchase order not found")
        if order.status != "pending_approval":
            raise ValueError("Only a purchase order pending approval can be rejected")
        order.status = "draft"
        order.approval_status = "rejected"
        order.approved_by = rejected_by
        order.approved_at = datetime.now(UTC).replace(tzinfo=None)
        order.rejection_reason = reason
        await self._notify_creator(order, approved=False)
        return order

    async def short_close_purchase_order(
        self, *, order_id: UUID, company_id: UUID, reason: str
    ) -> PurchaseOrder:
        """3-Day Brief P0-1: the user's answer to "will you receive the
        rest later?" was no — every line still short of its ordered qty
        is marked short_closed so it can never be received again without
        an explicit reopen, and the order itself moves to 'closed'
        (distinct from 'done', which means everything ordered actually
        arrived). Vendor billing is already bounded by qty_received
        (register_bill's 3-way match), so a short-closed line simply can
        never be billed for more than what actually arrived — no
        separate Payables-side change needed."""
        order = await self.order_repo.get_by_id(order_id)
        if order is None or order.company_id != company_id:
            raise ValueError("Purchase order not found")
        if order.status not in ("confirmed", "partially_received"):
            raise ValueError("Only a confirmed or partially-received purchase order can be short-closed")

        lines = await self.order_repo.get_lines(order_id)
        remaining_lines = [line for line in lines if line.qty_received < line.qty and not line.short_closed]
        if not remaining_lines:
            raise ValueError("This purchase order has nothing left to short-close")

        for line in remaining_lines:
            line.short_closed = True
        order.status = "closed"
        return order

    async def reopen_purchase_order_line(
        self, *, order_id: UUID, line_id: UUID, company_id: UUID
    ) -> PurchaseOrder:
        """Administrative-only counterpart to short_close_purchase_order
        (FR: "prevent receiving the closed qty except through a clear
        administrative action") — clears short_closed on one line and, if
        the order had moved to 'closed', restores whichever status
        honestly reflects the data (partially_received if anything's
        already arrived, confirmed if nothing has)."""
        order = await self.order_repo.get_by_id(order_id)
        if order is None or order.company_id != company_id:
            raise ValueError("Purchase order not found")
        line = await self.order_repo.get_line_by_id(line_id)
        if line is None or line.purchase_order_id != order_id:
            raise ValueError("Purchase order line not found on this order")
        if not line.short_closed:
            raise ValueError("This line is not short-closed")

        line.short_closed = False
        if order.status == "closed":
            all_lines = await self.order_repo.get_lines(order_id)
            order.status = (
                "partially_received" if any(ln.qty_received > 0 for ln in all_lines) else "confirmed"
            )
        return order

    async def _notify_approvers(self, order: PurchaseOrder) -> None:
        if self.role_repo is None or self.notification_repo is None:
            return
        approver_ids = await self.role_repo.list_user_ids_with_permission(order.company_id, APPROVE_PERMISSION_CODE)
        recipients = [uid for uid in approver_ids if uid != order.created_by_user_id]
        notifications = [
            self.notification_repo.build(
                company_id=order.company_id,
                recipient_user_id=uid,
                type="po_approval_requested",
                title=f"Purchase Order {order.number} needs approval",
                body=f"{order.number} totals {order.total_amount} and exceeds the approval threshold.",
                entity_type="purchase_order",
                entity_id=order.id,
                link=f"/purchasing/orders/{order.id}",
            )
            for uid in recipients
        ]
        await self.notification_repo.add_many(notifications)

    async def _notify_creator(self, order: PurchaseOrder, *, approved: bool) -> None:
        if self.notification_repo is None or order.created_by_user_id is None:
            return
        title = (
            f"Purchase Order {order.number} was approved"
            if approved
            else f"Purchase Order {order.number} was rejected"
        )
        body = (
            f"{order.number} is confirmed and ready to send to the vendor."
            if approved
            else f"{order.number} was sent back to draft: {order.rejection_reason}"
        )
        notification = self.notification_repo.build(
            company_id=order.company_id,
            recipient_user_id=order.created_by_user_id,
            type="po_approved" if approved else "po_rejected",
            title=title,
            body=body,
            entity_type="purchase_order",
            entity_id=order.id,
            link=f"/purchasing/orders/{order.id}",
        )
        await self.notification_repo.add_many([notification])


class GoodsReceiptService:
    """UC-PUR-01 (part 2) — Goods Receipt (FR-PUR-002).

    Increases inventory (through the same `InventoryValuationService` Sales
    uses to issue stock — Phase 8 §6's Adapter/shared-service pattern) and
    accrues the liability (Dr Inventory / Cr GRNI, Phase 5 §2) before the
    vendor bill even arrives.
    """

    def __init__(
        self,
        receipt_repo: GoodsReceiptRepository,
        order_repo: PurchaseOrderRepository,
        product_repo: ProductRepository,
        account_repo: AccountRepository,
        journal_entry_service: JournalEntryService,
        inventory_service: InventoryValuationService,
        warehouse_repo: WarehouseRepository,
        location_repo: LocationRepository,
        vendor_bill_service: "VendorBillService | None" = None,
    ):
        self.receipt_repo = receipt_repo
        self.order_repo = order_repo
        self.product_repo = product_repo
        self.account_repo = account_repo
        self.journal_entry_service = journal_entry_service
        self.inventory_service = inventory_service
        self.warehouse_repo = warehouse_repo
        self.location_repo = location_repo
        # Owner-requested: billing is no longer a separate manual step —
        # every receipt (partial or full) immediately produces its own
        # vendor bill for exactly what was received, at the PO's own
        # price. Optional only so existing tests/call sites that build
        # GoodsReceiptService directly without wiring VendorBillService
        # keep working unchanged (receipt-only, no auto-bill).
        self.vendor_bill_service = vendor_bill_service

    async def record_receipt(
        self,
        *,
        purchase_order_id: UUID,
        company_id: UUID,
        branch_id: UUID,
        created_by: UUID,
        valuation_method: str,
        lines: list[dict],
    ) -> GoodsReceipt:
        order = await self.order_repo.get_by_id(purchase_order_id)
        if order is None or order.company_id != company_id:
            raise ValueError("Purchase order not found")
        if order.status not in ("confirmed", "partially_received"):
            raise ValueError("Only a confirmed or partially-received purchase order can receive goods")

        warehouse = await self.warehouse_repo.get_default_for_company(company_id)
        if warehouse is None:
            raise ValueError("No default warehouse configured for this company")
        locations = await self.location_repo.list_by_warehouse(warehouse.id)
        if not locations:
            raise ValueError("Default warehouse has no location configured")
        location = locations[0]

        number = await self.receipt_repo.next_number(company_id)
        receipt = GoodsReceipt(
            id=uuid.uuid4(),
            company_id=company_id,
            purchase_order_id=order.id,
            warehouse_id=warehouse.id,
            number=number,
            status="done",
            receipt_date=date.today(),
        )
        receipt_lines: list[GoodsReceiptLine] = []
        total_value = Decimal("0")

        billed_lines: list[dict] = []
        for line in lines:
            po_line = await self.order_repo.get_line_by_id_for_update(line["purchase_order_line_id"])
            if po_line is None or po_line.purchase_order_id != order.id:
                raise ValueError("Purchase order line not found on this order")
            qty = Decimal(str(line["qty"]))
            if po_line.qty_received + qty > po_line.qty:
                raise ValueError(f"Receiving {qty} would exceed the ordered qty for product {po_line.product_id}")
            if po_line.short_closed:
                raise ValueError(
                    f"The remaining qty for product {po_line.product_id} was short-closed — "
                    "reopen the line before receiving against it"
                )

            product = await self.product_repo.get_by_id(po_line.product_id)
            if product is not None and product.is_stockable:
                await self.inventory_service.receive_stock(
                    company_id=company_id,
                    product_id=po_line.product_id,
                    location_id=location.id,
                    qty=qty,
                    unit_cost=po_line.unit_price,
                    valuation_method=valuation_method,
                    source_table="goods_receipt_line",
                    source_id=po_line.id,
                )
                total_value += qty * po_line.unit_price

            po_line.qty_received += qty
            receipt_lines.append(
                GoodsReceiptLine(
                    id=uuid.uuid4(),
                    company_id=company_id,
                    purchase_order_line_id=po_line.id,
                    product_id=po_line.product_id,
                    qty=qty,
                )
            )
            billed_lines.append(
                {"purchase_order_line_id": po_line.id, "qty": qty, "unit_price": po_line.unit_price}
            )

        try:
            await self.receipt_repo.add(receipt, receipt_lines)
        except IntegrityError as e:
            raise ValueError("A goods receipt was created concurrently with the same number — please retry") from e

        # Owner-requested: this receipt's own vendor bill, for exactly
        # what was just received, at the PO's own price — always a clean
        # 3-way match by construction, so it lands as "matched" the same
        # way a manually-entered identical bill would (approval/posting
        # stays a separate step, unchanged).
        if self.vendor_bill_service is not None and billed_lines:
            await self.vendor_bill_service.register_bill(
                purchase_order_id=order.id,
                company_id=company_id,
                branch_id=branch_id,
                vendor_reference=None,
                lines=billed_lines,
            )

        # 3-Day Brief P0-1 (revised per Owner feedback): the PO's status
        # must honestly reflect its data at all times, not sit in
        # "confirmed" through a partial receipt as if nothing happened.
        all_lines = await self.order_repo.get_lines(order.id)
        fully_resolved = all(line.qty_received >= line.qty or line.short_closed for line in all_lines)
        if fully_resolved and not any(line.short_closed for line in all_lines):
            order.status = "done"
        elif any(line.qty_received > 0 for line in all_lines):
            order.status = "partially_received"

        if total_value > 0:
            inventory_account = await self.account_repo.get_by_code(company_id, ACCOUNT_CODE_INVENTORY)
            grni_account = await self.account_repo.get_by_code(company_id, ACCOUNT_CODE_GRNI)
            if not (inventory_account and grni_account):
                raise ValueError("Default Chart of Accounts is not seeded for this company")

            entry = await self.journal_entry_service.create_draft_entry(
                company_id=company_id,
                branch_id=branch_id,
                journal_code="PURCH",
                entry_date=receipt.receipt_date,
                reference=receipt.number,
                lines=[
                    {"account_id": inventory_account.id, "debit": total_value, "credit": 0},
                    {"account_id": grni_account.id, "debit": 0, "credit": total_value},
                ],
                created_by=created_by,
                source_table="goods_receipt",
                source_id=receipt.id,
            )
            await self.journal_entry_service.post_entry(entry_id=entry.id, company_id=company_id)

        return receipt


class VendorBillService:
    """UC-PUR-01 (part 3) — Vendor Bill with 3-Way Match (FR-PUR-003)."""

    def __init__(
        self,
        bill_repo: VendorBillRepository,
        order_repo: PurchaseOrderRepository,
        receipt_repo: GoodsReceiptRepository,
        product_repo: ProductRepository,
        account_repo: AccountRepository,
        journal_entry_service: JournalEntryService,
        inventory_service: InventoryValuationService | None = None,
        warehouse_repo: WarehouseRepository | None = None,
        location_repo: LocationRepository | None = None,
        valuation_method: str | None = None,
        partner_repo: PartnerRepository | None = None,
    ):
        self.bill_repo = bill_repo
        self.order_repo = order_repo
        self.receipt_repo = receipt_repo
        self.product_repo = product_repo
        self.account_repo = account_repo
        self.journal_entry_service = journal_entry_service
        # Only issue_debit_note_for_lines needs this (a freeform Purchase
        # Return states its vendor directly, with no bill/PO to infer it
        # from) — register_bill/issue_debit_note both already get the
        # vendor from an existing PO/bill.
        self.partner_repo = partner_repo
        # Optional, same "not every caller needs it" pattern Sales'
        # InvoiceService already uses — only issue_debit_note's restock
        # path needs these; register_bill doesn't touch inventory at all.
        self.inventory_service = inventory_service
        self.warehouse_repo = warehouse_repo
        self.location_repo = location_repo
        self.valuation_method = valuation_method

    async def register_bill(
        self,
        *,
        purchase_order_id: UUID,
        company_id: UUID,
        branch_id: UUID,
        vendor_reference: str | None,
        lines: list[dict],
    ) -> VendorBill:
        order = await self.order_repo.get_by_id(purchase_order_id)
        if order is None or order.company_id != company_id:
            raise ValueError("Purchase order not found")

        number = await self.bill_repo.next_number(company_id)
        subtotal = Decimal("0")
        tax_total = Decimal("0")
        bill_lines: list[VendorBillLine] = []
        match_lines: list[MatchLine] = []

        for line in lines:
            po_line = await self.order_repo.get_line_by_id(line["purchase_order_line_id"])
            if po_line is None or po_line.purchase_order_id != order.id:
                raise ValueError("Purchase order line not found on this order")

            bill_qty = Decimal(str(line["qty"]))
            bill_unit_price = Decimal(str(line["unit_price"]))
            line_total = (bill_qty * bill_unit_price).quantize(Decimal("0.01"))
            tax_rate_percent = Decimal("15.00")
            line_tax = (line_total * tax_rate_percent / Decimal("100")).quantize(Decimal("0.01"))
            subtotal += line_total
            tax_total += line_tax

            bill_lines.append(
                VendorBillLine(
                    id=uuid.uuid4(),
                    company_id=company_id,
                    purchase_order_line_id=po_line.id,
                    product_id=po_line.product_id,
                    qty=bill_qty,
                    unit_price=bill_unit_price,
                    tax_rate_id=po_line.tax_rate_id,
                    tax_rate_percent=tax_rate_percent,
                    line_total=line_total,
                    tax_amount=line_tax,
                )
            )
            match_lines.append(
                MatchLine(
                    product_id=po_line.product_id,
                    po_qty=po_line.qty,
                    po_unit_price=po_line.unit_price,
                    received_qty=po_line.qty_received,
                    bill_qty=bill_qty,
                    bill_unit_price=bill_unit_price,
                )
            )

        mismatch_reasons = check_three_way_match(match_lines)
        status = "mismatched" if mismatch_reasons else "matched"

        bill = VendorBill(
            id=uuid.uuid4(),
            company_id=company_id,
            branch_id=branch_id,
            partner_id=order.partner_id,
            purchase_order_id=order.id,
            number=number,
            vendor_reference=vendor_reference,
            status=status,
            bill_date=date.today(),
            subtotal_amount=subtotal,
            tax_amount=tax_total,
            total_amount=subtotal + tax_total,
            mismatch_reasons="; ".join(mismatch_reasons) if mismatch_reasons else None,
        )
        try:
            await self.bill_repo.add(bill, bill_lines)
        except IntegrityError as e:
            raise ValueError("A vendor bill was created concurrently with the same number — please retry") from e

        for line in lines:
            po_line = await self.order_repo.get_line_by_id_for_update(line["purchase_order_line_id"])
            po_line.qty_billed += Decimal(str(line["qty"]))

        return bill

    async def approve_and_post(self, *, bill_id: UUID, company_id: UUID, created_by: UUID) -> VendorBill:
        bill = await self.bill_repo.get_by_id(bill_id)
        if bill is None or bill.company_id != company_id:
            raise ValueError("Vendor bill not found")
        if bill.status == "mismatched":
            raise ThreeWayMatchError(bill.mismatch_reasons or "Vendor bill failed 3-way match")
        if bill.status == "posted":
            raise ValueError("This bill is already posted")

        grni_account = await self.account_repo.get_by_code(company_id, ACCOUNT_CODE_GRNI)
        ap_account = await self.account_repo.get_by_code(company_id, ACCOUNT_CODE_AP)
        vat_account = await self.account_repo.get_by_code(company_id, ACCOUNT_CODE_VAT)
        if not (grni_account and ap_account and vat_account):
            raise ValueError("Default Chart of Accounts is not seeded for this company")

        # GRNI was accrued at receipt for the ex-tax goods value only
        # (Phase 5 §2: Dr Inventory / Cr GRNI, no VAT involved — the VAT
        # amount isn't known until the vendor's tax invoice arrives). So the
        # reversal here must clear exactly that ex-tax amount, not the
        # bill's tax-inclusive total; the VAT portion goes to the same VAT
        # control account sales output-VAT already uses (input VAT nets
        # against output VAT rather than needing a separate seeded account —
        # see Phase 1 §7 Saudi VAT context). Accounts Payable is credited
        # for the full amount actually owed to the vendor.
        lines = [{"account_id": grni_account.id, "debit": bill.subtotal_amount, "credit": 0}]
        if bill.tax_amount > 0:
            lines.append({"account_id": vat_account.id, "debit": bill.tax_amount, "credit": 0})
        lines.append({"account_id": ap_account.id, "debit": 0, "credit": bill.total_amount})

        entry = await self.journal_entry_service.create_draft_entry(
            company_id=company_id,
            branch_id=bill.branch_id,
            journal_code="PURCH",
            entry_date=bill.bill_date,
            reference=bill.number,
            lines=lines,
            created_by=created_by,
            source_table="vendor_bill",
            source_id=bill.id,
        )
        posted = await self.journal_entry_service.post_entry(entry_id=entry.id, company_id=company_id)

        bill.status = "posted"
        bill.journal_entry_id = posted.id
        return bill

    async def issue_debit_note(
        self,
        *,
        original_bill_id: UUID,
        company_id: UUID,
        branch_id: UUID,
        created_by: UUID,
        reason: str,
        restock: bool = True,
    ) -> VendorBill:
        """Product Owner audit finding: Sales has a Credit Note (reverses a
        posted invoice) but Purchasing had no equivalent for reversing a
        posted vendor bill (goods returned to the vendor, or a price
        correction) — a real asymmetry against SAP B1/Dynamics 365 BC/Odoo.
        Mirrors issue_credit_note: a full reversal of the original bill's
        own amounts and its own posting journal entry (GRNI/VAT/AP), not a
        partial-amount document. Product Owner follow-up request:
        `restock=True` (the default — a debit note usually means goods are
        physically going back to the vendor) additionally removes the
        returned qty from stock, turning this into a true Purchase Return
        rather than a financial-only correction."""
        original = await self.bill_repo.get_by_id(original_bill_id)
        if original is None or original.company_id != company_id:
            raise ValueError("Original vendor bill not found")
        if original.bill_type != "standard":
            raise ValueError("Debit notes can only be issued against a standard vendor bill")
        if original.status != "posted":
            raise ValueError("Debit notes can only be issued against a posted vendor bill")

        original_lines = await self.bill_repo.get_lines(original_bill_id)
        number = await self.bill_repo.next_number(company_id)

        debit_note_lines = [
            VendorBillLine(
                id=uuid.uuid4(),
                company_id=company_id,
                purchase_order_line_id=line.purchase_order_line_id,
                product_id=line.product_id,
                qty=line.qty,
                unit_price=line.unit_price,
                tax_rate_id=line.tax_rate_id,
                tax_rate_percent=line.tax_rate_percent,
                line_total=line.line_total,
                tax_amount=line.tax_amount,
            )
            for line in original_lines
        ]

        debit_note = VendorBill(
            id=uuid.uuid4(),
            company_id=company_id,
            branch_id=branch_id,
            partner_id=original.partner_id,
            purchase_order_id=original.purchase_order_id,
            original_bill_id=original.id,
            bill_type="debit_note",
            number=number,
            status="posted",
            bill_date=date.today(),
            subtotal_amount=original.subtotal_amount,
            tax_amount=original.tax_amount,
            total_amount=original.total_amount,
        )
        try:
            await self.bill_repo.add(debit_note, debit_note_lines)
        except IntegrityError as e:
            raise ValueError("A vendor bill was created concurrently with the same number — please retry") from e

        grni_account = await self.account_repo.get_by_code(company_id, ACCOUNT_CODE_GRNI)
        ap_account = await self.account_repo.get_by_code(company_id, ACCOUNT_CODE_AP)
        vat_account = await self.account_repo.get_by_code(company_id, ACCOUNT_CODE_VAT)
        if not (grni_account and ap_account and vat_account):
            raise ValueError("Default Chart of Accounts is not seeded for this company")

        # Exact opposite of approve_and_post's lines: reduces what's owed
        # to the vendor (Dr AP) and reverses the ex-tax/VAT split the
        # original bill posted.
        lines = [{"account_id": ap_account.id, "debit": debit_note.total_amount, "credit": 0}]
        lines.append({"account_id": grni_account.id, "debit": 0, "credit": debit_note.subtotal_amount})
        if debit_note.tax_amount > 0:
            lines.append({"account_id": vat_account.id, "debit": 0, "credit": debit_note.tax_amount})

        entry = await self.journal_entry_service.create_draft_entry(
            company_id=company_id,
            branch_id=branch_id,
            journal_code="PURCH",
            entry_date=debit_note.bill_date,
            reference=debit_note.number,
            description=reason,
            lines=lines,
            created_by=created_by,
            source_table="vendor_bill",
            source_id=debit_note.id,
        )
        posted = await self.journal_entry_service.post_entry(entry_id=entry.id, company_id=company_id)
        debit_note.journal_entry_id = posted.id

        if restock:
            await self._restock_for_debit_note(
                debit_note, lines=debit_note_lines, branch_id=branch_id, created_by=created_by
            )

        return debit_note

    async def issue_debit_note_for_lines(
        self,
        *,
        partner_id: UUID,
        company_id: UUID,
        branch_id: UUID,
        created_by: UUID,
        reason: str,
        lines: list[dict],
        original_bill_id: UUID | None = None,
        restock: bool = True,
    ) -> VendorBill:
        """Product Owner request: a Purchase Return does not have to
        correspond to one whole vendor bill (or even one purchase order) —
        it can be a freeform set of lines with the original bill number
        reduced to an OPTIONAL traceability field. Mirrors
        `issue_debit_note`'s GRNI/AP/VAT JE + restock pipeline, but each
        line is computed from scratch (same flat-15% VAT convention every
        other from-scratch line in this codebase uses) instead of being
        copied verbatim from a single original bill's own lines. Neither
        `purchase_order_id` nor any line's `purchase_order_line_id` is set
        (both nullable — see migration b3c4d5e6f7a8) since there may be no
        PO behind this return at all."""
        if self.partner_repo is None:
            raise ValueError("Vendor lookup is not configured for this company")
        if not lines:
            raise ValueError("A debit note must have at least one line")

        partner = await self.partner_repo.get_by_id(partner_id)
        if partner is None or partner.company_id != company_id:
            raise ValueError("Vendor not found")

        original: VendorBill | None = None
        if original_bill_id is not None:
            original = await self.bill_repo.get_by_id(original_bill_id)
            if original is None or original.company_id != company_id:
                raise ValueError("Original vendor bill not found")
            if original.bill_type != "standard":
                raise ValueError("A debit note can only reference a standard vendor bill")
            if original.partner_id != partner_id:
                raise ValueError("The original vendor bill does not belong to this vendor")

        number = await self.bill_repo.next_number(company_id)
        subtotal = Decimal("0")
        tax_total = Decimal("0")
        debit_note_lines: list[VendorBillLine] = []

        for line in lines:
            line_total = (line["qty"] * line["unit_price"]).quantize(Decimal("0.01"))
            tax_rate_percent = Decimal("15.00")  # nucleus default; per-line rate lookup is a follow-up
            line_tax = (line_total * tax_rate_percent / Decimal("100")).quantize(Decimal("0.01"))
            subtotal += line_total
            tax_total += line_tax
            debit_note_lines.append(
                VendorBillLine(
                    id=uuid.uuid4(),
                    company_id=company_id,
                    purchase_order_line_id=None,
                    product_id=line["product_id"],
                    qty=line["qty"],
                    unit_price=line["unit_price"],
                    tax_rate_id=line["tax_rate_id"],
                    tax_rate_percent=tax_rate_percent,
                    line_total=line_total,
                    tax_amount=line_tax,
                )
            )

        debit_note = VendorBill(
            id=uuid.uuid4(),
            company_id=company_id,
            branch_id=branch_id,
            partner_id=partner_id,
            purchase_order_id=None,
            original_bill_id=original.id if original is not None else None,
            bill_type="debit_note",
            number=number,
            status="posted",
            bill_date=date.today(),
            subtotal_amount=subtotal,
            tax_amount=tax_total,
            total_amount=subtotal + tax_total,
        )
        try:
            await self.bill_repo.add(debit_note, debit_note_lines)
        except IntegrityError as e:
            raise ValueError("A vendor bill was created concurrently with the same number — please retry") from e

        grni_account = await self.account_repo.get_by_code(company_id, ACCOUNT_CODE_GRNI)
        ap_account = await self.account_repo.get_by_code(company_id, ACCOUNT_CODE_AP)
        vat_account = await self.account_repo.get_by_code(company_id, ACCOUNT_CODE_VAT)
        if not (grni_account and ap_account and vat_account):
            raise ValueError("Default Chart of Accounts is not seeded for this company")

        je_lines = [{"account_id": ap_account.id, "debit": debit_note.total_amount, "credit": 0}]
        je_lines.append({"account_id": grni_account.id, "debit": 0, "credit": debit_note.subtotal_amount})
        if debit_note.tax_amount > 0:
            je_lines.append({"account_id": vat_account.id, "debit": 0, "credit": debit_note.tax_amount})

        entry = await self.journal_entry_service.create_draft_entry(
            company_id=company_id,
            branch_id=branch_id,
            journal_code="PURCH",
            entry_date=debit_note.bill_date,
            reference=debit_note.number,
            description=reason,
            lines=je_lines,
            created_by=created_by,
            source_table="vendor_bill",
            source_id=debit_note.id,
        )
        posted = await self.journal_entry_service.post_entry(entry_id=entry.id, company_id=company_id)
        debit_note.journal_entry_id = posted.id

        if restock:
            await self._restock_for_debit_note(
                debit_note, lines=debit_note_lines, branch_id=branch_id, created_by=created_by
            )

        return debit_note

    async def _restock_for_debit_note(
        self, debit_note: VendorBill, *, lines: list[VendorBillLine], branch_id: UUID, created_by: UUID
    ) -> None:
        """Purchase Return: removes the debit note's qty back out of stock
        (the current valuation-engine cost, same as any other outgoing
        move in this codebase — there is no single "original cost" to
        reverse here the way Sales' delivery moves record one, since a
        vendor bill's own unit_price already went into the moving-average/
        FIFO pool at receipt time alongside every other receipt for that
        product) and posts the exact-opposite of the goods-receipt entry
        (Dr GRNI / Cr Inventory) for whatever that computes to. Silently a
        no-op when inventory isn't configured for this company."""
        if self.inventory_service is None or self.warehouse_repo is None:
            return

        warehouse = await self.warehouse_repo.get_default_for_company(debit_note.company_id)
        if warehouse is None:
            return
        locations = await self.location_repo.list_by_warehouse(warehouse.id)
        if not locations:
            return
        location = locations[0]

        total_cost = Decimal("0")
        for line in lines:
            product = await self.product_repo.get_by_id(line.product_id)
            if product is None or not product.is_stockable:
                continue

            _move, cost = await self.inventory_service.issue_stock(
                company_id=debit_note.company_id,
                product_id=line.product_id,
                location_id=location.id,
                qty=line.qty,
                valuation_method=self.valuation_method or "average",
                source_table="vendor_bill",
                source_id=debit_note.id,
                move_type="return",
                allow_negative=True,
            )
            total_cost += cost

        if total_cost <= 0:
            return

        grni_account = await self.account_repo.get_by_code(debit_note.company_id, ACCOUNT_CODE_GRNI)
        inventory_account = await self.account_repo.get_by_code(debit_note.company_id, ACCOUNT_CODE_INVENTORY)
        if not (grni_account and inventory_account):
            raise ValueError("Default Chart of Accounts is not seeded for this company")

        entry = await self.journal_entry_service.create_draft_entry(
            company_id=debit_note.company_id,
            branch_id=branch_id,
            journal_code="PURCH",
            entry_date=debit_note.bill_date,
            reference=f"Inventory return for {debit_note.number}",
            lines=[
                {"account_id": grni_account.id, "debit": total_cost, "credit": 0},
                {"account_id": inventory_account.id, "debit": 0, "credit": total_cost},
            ],
            created_by=created_by,
            source_table="vendor_bill",
            source_id=debit_note.id,
        )
        await self.journal_entry_service.post_entry(entry_id=entry.id, company_id=debit_note.company_id)
