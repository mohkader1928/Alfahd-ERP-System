"""Application services (use-case orchestration) for Purchasing, Phase 8 §2.

Purchasing depends on Identity, Inventory, and Accounting per the Phase 8 §3
module map — same "legitimate direct dependency" pattern Sales uses.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from src.modules.accounting.application.services import JournalEntryService
from src.modules.accounting.infrastructure.repositories import AccountRepository
from src.modules.identity.infrastructure.repositories import (
    CompanyRepository,
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
    ):
        self.order_repo = order_repo
        self.company_repo = company_repo
        self.role_repo = role_repo
        self.notification_repo = notification_repo

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
        return await self.order_repo.add(order, orm_lines)

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
    ):
        self.receipt_repo = receipt_repo
        self.order_repo = order_repo
        self.product_repo = product_repo
        self.account_repo = account_repo
        self.journal_entry_service = journal_entry_service
        self.inventory_service = inventory_service
        self.warehouse_repo = warehouse_repo
        self.location_repo = location_repo

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
        if order.status != "confirmed":
            raise ValueError("Only a confirmed purchase order can receive goods")

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

        for line in lines:
            po_line = await self.order_repo.get_line_by_id(line["purchase_order_line_id"])
            if po_line is None or po_line.purchase_order_id != order.id:
                raise ValueError("Purchase order line not found on this order")
            qty = Decimal(str(line["qty"]))
            if po_line.qty_received + qty > po_line.qty:
                raise ValueError(f"Receiving {qty} would exceed the ordered qty for product {po_line.product_id}")

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

        await self.receipt_repo.add(receipt, receipt_lines)

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
    ):
        self.bill_repo = bill_repo
        self.order_repo = order_repo
        self.receipt_repo = receipt_repo
        self.product_repo = product_repo
        self.account_repo = account_repo
        self.journal_entry_service = journal_entry_service

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
        await self.bill_repo.add(bill, bill_lines)

        for line in lines:
            po_line = await self.order_repo.get_line_by_id(line["purchase_order_line_id"])
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
