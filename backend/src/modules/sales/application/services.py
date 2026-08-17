"""Application services (use-case orchestration) for Sales, Phase 8 §2.

Sales legitimately depends on both Accounting and ZATCA per the Phase 8 §3
module map (unlike Identity->Accounting, which is decoupled via domain
events because Identity must have zero downstream dependencies) — so this
module calls those two directly rather than through the event bus.
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from src.modules.accounting.application.services import JournalEntryService
from src.modules.accounting.infrastructure.repositories import AccountRepository, TaxRepository
from src.modules.identity.infrastructure.repositories import (
    CompanyRepository,
    PartnerRepository,
    ProductRepository,
)
from src.modules.inventory.application.services import InventoryValuationService
from src.modules.inventory.infrastructure.repositories import (
    LocationRepository,
    WarehouseRepository,
)
from src.modules.sales.infrastructure.models import (
    Quotation,
    QuotationLine,
    SalesInvoice,
    SalesInvoiceLine,
    SalesOrder,
    SalesOrderLine,
    ZatcaSubmission,
)
from src.modules.sales.infrastructure.repositories import (
    QuotationRepository,
    SalesInvoiceRepository,
    SalesOrderRepository,
    ZatcaSubmissionRepository,
)
from src.modules.zatca.application.zatca_service import ZatcaInvoiceProcessor, now_iso
from src.modules.zatca.domain.entities import InvoiceData, InvoiceLineData, SubmissionResult
from src.modules.zatca.infrastructure.hash_chain import GENESIS_HASH
from src.shared.documents.invoice_pdf import InvoiceDocument, InvoiceLineRow, render_invoice_pdf
from src.shared.documents.quotation_pdf import (
    QuotationDocument,
    QuotationLineRow,
    render_quotation_pdf,
)
from src.shared.email.mailer import EmailAttachment
from src.shared.email.mailer import send_email as default_send_email

# Chart-of-account codes seeded by Accounting's default Saudi CoA (M1) that
# the Sales journal entry posts against.
ACCOUNT_CODE_AR = "1200"
ACCOUNT_CODE_SALES_REVENUE = "4100"
ACCOUNT_CODE_VAT_PAYABLE = "2200"
ACCOUNT_CODE_INVENTORY = "1300"
ACCOUNT_CODE_COGS = "5100"


class QuotationService:
    """UC-SAL-01 — Quotation to Sales Order."""

    def __init__(
        self,
        quotation_repo: QuotationRepository,
        order_repo: SalesOrderRepository,
        *,
        partner_repo: PartnerRepository,
        product_repo: ProductRepository,
        seller_name: str,
        seller_name_ar: str | None = None,
        seller_logo_path: str | None = None,
    ):
        self.quotation_repo = quotation_repo
        self.order_repo = order_repo
        self.partner_repo = partner_repo
        self.product_repo = product_repo
        self.seller_name = seller_name
        self.seller_name_ar = seller_name_ar
        self.seller_logo_path = seller_logo_path

    async def create_quotation(
        self,
        *,
        company_id: UUID,
        branch_id: UUID,
        partner_id: UUID,
        quote_date: date,
        lines: list[dict],
        warehouse_id: UUID | None = None,
        cost_center_id: UUID | None = None,
        payment_terms: str | None = None,
    ) -> Quotation:
        if not lines:
            raise ValueError("A quotation needs at least one line")
        number = await self.quotation_repo.next_number(company_id)
        total = sum((Decimal(str(line["qty"])) * Decimal(str(line["unit_price"])) for line in lines), Decimal("0"))

        quotation = Quotation(
            id=uuid.uuid4(),
            company_id=company_id,
            branch_id=branch_id,
            partner_id=partner_id,
            number=number,
            status="draft",
            quote_date=quote_date,
            total_amount=total,
            warehouse_id=warehouse_id,
            cost_center_id=cost_center_id,
            payment_terms=payment_terms,
        )
        orm_lines = [
            QuotationLine(
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
            return await self.quotation_repo.add(quotation, orm_lines)
        except IntegrityError as e:
            raise ValueError("A quotation was created concurrently with the same number — please retry") from e

    async def update_quotation(
        self,
        *,
        quotation_id: UUID,
        company_id: UUID,
        partner_id: UUID,
        quote_date: date,
        lines: list[dict],
        warehouse_id: UUID | None = None,
        cost_center_id: UUID | None = None,
        payment_terms: str | None = None,
    ) -> Quotation:
        """Product Owner request: allow editing a transaction before it's
        posted/confirmed. A Quotation is the one genuinely pre-commitment
        stage in the Sales flow (a SalesOrder is created already
        'confirmed' — see `confirm_to_sales_order` — and a SalesInvoice is
        created, ZATCA-submitted, and journaled in one atomic call with no
        draft window of its own), so this is the edit surface for the
        whole quote-to-order stage. Full line replace, matching
        `create_quotation`'s own computation."""
        if not lines:
            raise ValueError("A quotation needs at least one line")
        quotation = await self.quotation_repo.get_by_id(quotation_id)
        if quotation is None or quotation.company_id != company_id:
            raise ValueError("Quotation not found")
        if quotation.status != "draft":
            raise ValueError("Only a draft quotation can be edited")

        total = sum((Decimal(str(line["qty"])) * Decimal(str(line["unit_price"])) for line in lines), Decimal("0"))
        orm_lines = [
            QuotationLine(
                id=uuid.uuid4(),
                company_id=company_id,
                product_id=line["product_id"],
                qty=Decimal(str(line["qty"])),
                unit_price=Decimal(str(line["unit_price"])),
                tax_rate_id=line["tax_rate_id"],
            )
            for line in lines
        ]
        await self.quotation_repo.replace_lines(quotation_id, orm_lines)
        quotation.partner_id = partner_id
        quotation.quote_date = quote_date
        quotation.total_amount = total
        quotation.warehouse_id = warehouse_id
        quotation.cost_center_id = cost_center_id
        quotation.payment_terms = payment_terms
        return quotation

    async def confirm_to_sales_order(self, *, quotation_id: UUID, company_id: UUID) -> SalesOrder:
        quotation = await self.quotation_repo.get_by_id(quotation_id)
        if quotation is None or quotation.company_id != company_id:
            raise ValueError("Quotation not found")
        if quotation.status != "draft":
            raise ValueError("Only a draft quotation can be confirmed")

        lines = await self.quotation_repo.get_lines(quotation_id)
        number = await self.order_repo.next_number(company_id)

        order = SalesOrder(
            id=uuid.uuid4(),
            company_id=company_id,
            branch_id=quotation.branch_id,
            partner_id=quotation.partner_id,
            quotation_id=quotation.id,
            number=number,
            status="confirmed",
            # Preserve the quotation's own date rather than the order's
            # creation date — was previously date.today(), which silently
            # discarded whatever date the quotation actually carried (there
            # is no ZATCA or accounting reason to force this one; unlike
            # invoice_date, order_date is never reported to ZATCA).
            order_date=quotation.quote_date,
            total_amount=quotation.total_amount,
            warehouse_id=quotation.warehouse_id,
            cost_center_id=quotation.cost_center_id,
        )
        order_lines = [
            SalesOrderLine(
                id=uuid.uuid4(),
                company_id=company_id,
                product_id=line.product_id,
                description="",
                qty=line.qty,
                unit_price=line.unit_price,
                tax_rate_id=line.tax_rate_id,
            )
            for line in lines
        ]
        try:
            await self.order_repo.add(order, order_lines)
        except IntegrityError as e:
            raise ValueError("A sales order was created concurrently with the same number — please retry") from e

        quotation.status = "confirmed"
        return order

    async def update_order(
        self,
        *,
        order_id: UUID,
        company_id: UUID,
        partner_id: UUID,
        order_date: date,
        lines: list[dict],
        warehouse_id: UUID | None = None,
        cost_center_id: UUID | None = None,
    ) -> SalesOrder:
        """Product Owner-reported blocker (SO-000035): a confirmed order
        for more than what's currently in stock had no way to be
        corrected — a Sales Order previously had zero edit path at all,
        unlike Quotation/Purchase Order/Vendor Bill. Gated on nothing
        having been invoiced yet (`qty_invoiced == 0` on every line): once
        even a partial invoice exists, the order's own numbers are no
        longer just a plan — they're tied to a real posted document, so
        correction from there on is via the order's remaining balance
        (invoice less, or cancel what wasn't shipped), not a silent
        rewrite. Full line replace, matching `confirm_to_sales_order`'s
        own computation."""
        if not lines:
            raise ValueError("A sales order needs at least one line")
        order = await self.order_repo.get_by_id(order_id)
        if order is None or order.company_id != company_id:
            raise ValueError("Sales order not found")
        if order.status not in ("draft", "confirmed"):
            raise ValueError("Only an order with nothing invoiced yet can be edited")
        existing_lines = await self.order_repo.get_lines(order_id)
        if any(line.qty_invoiced > 0 for line in existing_lines):
            raise ValueError("This order has already been partially invoiced and can no longer be edited")

        total = sum((Decimal(str(line["qty"])) * Decimal(str(line["unit_price"])) for line in lines), Decimal("0"))
        orm_lines = [
            SalesOrderLine(
                id=uuid.uuid4(),
                company_id=company_id,
                product_id=line["product_id"],
                description="",
                qty=Decimal(str(line["qty"])),
                unit_price=Decimal(str(line["unit_price"])),
                tax_rate_id=line["tax_rate_id"],
            )
            for line in lines
        ]
        await self.order_repo.replace_lines(order_id, orm_lines)
        order.partner_id = partner_id
        order.order_date = order_date
        order.total_amount = total
        order.warehouse_id = warehouse_id
        order.cost_center_id = cost_center_id
        return order

    async def cancel_order(self, *, order_id: UUID, company_id: UUID, reason: str) -> SalesOrder:
        order = await self.order_repo.get_by_id(order_id)
        if order is None or order.company_id != company_id:
            raise ValueError("Sales order not found")
        if order.status not in ("draft", "confirmed"):
            raise ValueError("Only an order with nothing invoiced yet can be cancelled")
        existing_lines = await self.order_repo.get_lines(order_id)
        if any(line.qty_invoiced > 0 for line in existing_lines):
            raise ValueError("This order has already been partially invoiced and can no longer be cancelled")
        if not reason.strip():
            raise ValueError("A cancellation reason is required")

        order.status = "cancelled"
        order.cancellation_reason = reason
        return order

    async def build_quotation_pdf(self, *, quotation_id: UUID, company_id: UUID, lang: str = "ar") -> bytes:
        """Document Delivery for Quotations (Owner request): the same
        letterhead/line-items/totals document approach as invoices, but
        with each line's product image and the quotation's payment terms
        instead of any VAT/ZATCA content — a quotation is a pre-sale
        document, not a tax document."""
        quotation = await self.quotation_repo.get_by_id(quotation_id)
        if quotation is None or quotation.company_id != company_id:
            raise ValueError("Quotation not found")
        lines = await self.quotation_repo.get_lines(quotation_id)
        partner = await self.partner_repo.get_by_id(quotation.partner_id, include_archived=True)

        line_rows = []
        for line in lines:
            product = await self.product_repo.get_by_id(line.product_id)
            line_rows.append(
                QuotationLineRow(
                    product_name=product.name if product else "",
                    product_image_path=product.image_path if product else None,
                    qty=line.qty,
                    unit_price=line.unit_price,
                    line_total=line.qty * line.unit_price,
                )
            )

        doc = QuotationDocument(
            number=quotation.number,
            quote_date=quotation.quote_date,
            total_amount=quotation.total_amount,
            lines=line_rows,
            company_name=self.seller_name,
            company_name_ar=self.seller_name_ar or self.seller_name,
            company_logo_path=self.seller_logo_path,
            partner_name=partner.name if partner else "",
            payment_terms=quotation.payment_terms,
            lang=lang,
        )
        return render_quotation_pdf(doc)

    async def send_quotation_email(
        self,
        *,
        quotation_id: UUID,
        company_id: UUID,
        to_email: str | None = None,
        lang: str = "ar",
        mailer: Callable[..., Awaitable[None]] = default_send_email,
    ) -> Quotation:
        """Document Delivery for Quotations (Owner request). Defaults to
        the customer's Partner.email on file; an explicit `to_email`
        overrides it — mirrors SalesInvoiceService.send_invoice_email."""
        quotation = await self.quotation_repo.get_by_id(quotation_id)
        if quotation is None or quotation.company_id != company_id:
            raise ValueError("Quotation not found")
        partner = await self.partner_repo.get_by_id(quotation.partner_id, include_archived=True)
        recipient = to_email or (partner.email if partner else None)
        if not recipient:
            raise ValueError(
                "No email address on file for this customer, and none was provided for this send."
            )

        pdf_bytes = await self.build_quotation_pdf(quotation_id=quotation_id, company_id=company_id, lang=lang)
        subject = f"{self.seller_name} — Quotation {quotation.number}"
        body = (
            f"Dear {partner.name if partner else 'Customer'},\n\n"
            f"Please find attached price quotation {quotation.number} dated {quotation.quote_date.isoformat()}, "
            f"totaling {quotation.total_amount} {quotation.currency_code}.\n\n"
            f"Regards,\n{self.seller_name}"
        )
        await mailer(
            to=recipient,
            subject=subject,
            body=body,
            attachments=[EmailAttachment(filename=f"{quotation.number}.pdf", content=pdf_bytes)],
        )

        quotation.last_emailed_at = datetime.now(UTC).replace(tzinfo=None)
        quotation.last_emailed_to = recipient
        return quotation


class SalesInvoiceService:
    """UC-SAL-03/04/05 — Issue Tax/Simplified Invoice, Credit Note.

    Orchestrates: ZATCA package generation (+ synchronous Clearance for
    B2B, or local generation only for B2C with async Reporting enqueued by
    the caller — see Phase 5 §3), then the matching journal entry (FR-SAL-007).
    """

    def __init__(
        self,
        invoice_repo: SalesInvoiceRepository,
        order_repo: SalesOrderRepository,
        zatca_submission_repo: ZatcaSubmissionRepository,
        partner_repo: PartnerRepository,
        product_repo: ProductRepository,
        account_repo: AccountRepository,
        tax_repo: TaxRepository,
        journal_entry_service: JournalEntryService,
        zatca_processor: ZatcaInvoiceProcessor,
        seller_name: str,
        seller_vat_number: str,
        inventory_service: InventoryValuationService | None = None,
        warehouse_repo: WarehouseRepository | None = None,
        location_repo: LocationRepository | None = None,
        valuation_method: str | None = None,
        seller_name_ar: str | None = None,
        seller_logo_path: str | None = None,
        company_repo: CompanyRepository | None = None,
    ):
        self.company_repo = company_repo
        self.invoice_repo = invoice_repo
        self.order_repo = order_repo
        self.zatca_submission_repo = zatca_submission_repo
        self.partner_repo = partner_repo
        self.product_repo = product_repo
        self.account_repo = account_repo
        self.tax_repo = tax_repo
        self.journal_entry_service = journal_entry_service
        self.zatca_processor = zatca_processor
        self.seller_name = seller_name
        self.seller_vat_number = seller_vat_number
        self.seller_name_ar = seller_name_ar
        self.seller_logo_path = seller_logo_path
        # Inventory integration is optional (Phase 8 §3: Sales -> Inventory
        # is an allowed dependency, but not every company has inventory set
        # up — service-only companies invoice without any warehouse ever
        # existing). If a default warehouse exists, stock is deducted and a
        # COGS entry posted (FR-SAL-003/FR-INV-005); if not, the sale
        # proceeds as financial-only, matching M2's original behavior.
        self.inventory_service = inventory_service
        self.warehouse_repo = warehouse_repo
        self.location_repo = location_repo
        self.valuation_method = valuation_method

    async def _next_icv_and_previous_hash(self, company_id: UUID) -> tuple[int, str]:
        # Row-level lock on the company (docs/16b, finding #3): a plain
        # unlocked "ORDER BY icv DESC LIMIT 1" lets two concurrent invoice
        # issuances for the same company both read the same tail and
        # compute the same next ICV, breaking the hash chain's required
        # total order — a ZATCA-compliance defect, not just bookkeeping.
        # Locking the company row (rather than the tail submission row
        # itself) is what actually serializes this: a second transaction
        # blocked on this same lock re-reads the ICV query fresh once
        # unblocked, rather than replaying a stale snapshot of the old tail.
        if self.company_repo is not None:
            await self.company_repo.get_for_update(company_id)
        latest = await self.invoice_repo.latest_zatca_submission_for_company(company_id)
        if latest is None:
            return 1, GENESIS_HASH
        return latest.icv + 1, latest.invoice_hash

    async def _resolve_tax_rate_percent(self, tax_rate_id: UUID, company_id: UUID) -> Decimal:
        """P0-1 (Phase-One VAT hardening): the real, configured rate for
        `tax_rate_id`, not an assumed constant. Falls back to this
        company's own configured *standard* rate — rather than a bare
        hardcoded `Decimal("15.00")` — when `tax_rate_id` doesn't resolve to
        a real row for this company (RLS already prevents a genuine
        cross-company leak here; the explicit company_id check is
        defense-in-depth matching this module's existing style). This keeps
        every pre-existing caller that predates real per-rate lookups
        working unchanged (still the company's real seeded Standard VAT
        rate, not a magic number) while a genuinely selected rate —
        including zero-rated/exempt — is always honored exactly."""
        rate = await self.tax_repo.get_rate_by_id(tax_rate_id)
        if rate is not None and rate.company_id == company_id:
            return rate.rate_percent
        rates = await self.tax_repo.list_by_company(company_id)
        standard = next((r for r in rates if r.kind == "standard"), None)
        if standard is None:
            raise ValueError("No tax rate configuration exists for this company")
        return standard.rate_percent

    async def issue_invoice_from_order(
        self,
        *,
        sales_order_id: UUID,
        company_id: UUID,
        branch_id: UUID,
        created_by: UUID,
        lines: list[dict] | None = None,
    ) -> tuple[SalesInvoice, ZatcaSubmission]:
        """`lines=None` invoices everything still remaining on the order
        (the original, backward-compatible all-in-one-shot path). Passing
        `lines=[{sales_order_line_id, qty}, ...]` invoices only that
        subset/quantity — Product Owner-reported blocker: an order for
        more than what's currently in stock (e.g. SO-000035: 1000 units
        ordered, 0 on hand, a matching Purchase Order for the shortfall
        already confirmed but not yet received) had no path forward,
        since invoicing was all-or-nothing. Standard ERP practice
        (SAP/Oracle/Odoo): invoice what's available now, leave the rest
        open as a backorder — `SalesOrderLine.qty_invoiced` tracks how
        much of each line has been invoiced so far, and the order's own
        status reflects whether it's fully or only partially fulfilled."""
        order = await self.order_repo.get_by_id(sales_order_id)
        if order is None or order.company_id != company_id:
            raise ValueError("Sales order not found")
        if order.status not in ("confirmed", "partially_invoiced"):
            raise ValueError("Only a confirmed sales order can be invoiced")

        order_lines = await self.order_repo.get_lines(sales_order_id)
        partner = await self.partner_repo.get_by_id(order.partner_id)
        if partner is None:
            raise ValueError("Customer not found")

        # Row-locked selection: without this, two concurrent partial-
        # invoice requests against the same line can both read the same
        # qty_invoiced and both pass the not-over-invoiced check (same
        # race Purchasing already closes for qty_received/qty_billed via
        # get_line_by_id_for_update). This replaces the old DB-level
        # ux_sales_invoice_sales_order_id uniqueness, which assumed only
        # one invoice would ever exist per order — no longer true now
        # that partial/backorder invoicing is a legitimate, repeated shape.
        selected: list[tuple[SalesOrderLine, Decimal]] = []
        if lines is None:
            for line in order_lines:
                locked = await self.order_repo.get_line_by_id_for_update(line.id)
                remaining = locked.qty - locked.qty_invoiced
                if remaining > 0:
                    selected.append((locked, remaining))
        else:
            order_line_ids = {line.id for line in order_lines}
            for item in lines:
                line_id = item["sales_order_line_id"]
                if line_id not in order_line_ids:
                    raise ValueError("Sales order line not found on this order")
                locked = await self.order_repo.get_line_by_id_for_update(line_id)
                qty = Decimal(str(item["qty"]))
                if qty <= 0:
                    continue
                remaining = locked.qty - locked.qty_invoiced
                if qty > remaining:
                    raise ValueError(
                        f"Cannot invoice {qty} — only {remaining} remains un-invoiced on this line"
                    )
                selected.append((locked, qty))

        if not selected:
            raise ValueError("Nothing to invoice — every line is already fully invoiced, or none was selected")

        # FR-ZATCA-001: B2B (VAT-registered) -> Tax invoice + Clearance;
        # B2C/unregistered -> Simplified invoice + Reporting.
        invoice_type = "tax" if partner.vat_number else "simplified"
        submission_mode = "clearance" if invoice_type == "tax" else "reporting"

        number = await self.invoice_repo.next_number(company_id)
        subtotal = Decimal("0")
        tax_total = Decimal("0")
        invoice_lines: list[SalesInvoiceLine] = []
        zatca_lines: list[InvoiceLineData] = []

        for line, qty in selected:
            product = await self.product_repo.get_by_id(line.product_id)
            # Quantized to currency precision immediately — qty (scale 6) *
            # unit_price (scale 4) otherwise retains full arithmetic
            # precision in Python (e.g. "2300.0000000000") even though the
            # NUMERIC(18,4) column would round it on storage, so an
            # unquantized value returned straight from the in-memory ORM
            # object (no round-trip SELECT) would leak that mismatch to the API.
            line_total = (qty * line.unit_price).quantize(Decimal("0.01"))
            tax_rate_percent = await self._resolve_tax_rate_percent(line.tax_rate_id, company_id)
            line_tax = (line_total * tax_rate_percent / Decimal("100")).quantize(Decimal("0.01"))
            subtotal += line_total
            tax_total += line_tax
            invoice_lines.append(
                SalesInvoiceLine(
                    id=uuid.uuid4(),
                    company_id=company_id,
                    product_id=line.product_id,
                    description=product.name if product else "",
                    qty=qty,
                    unit_price=line.unit_price,
                    tax_rate_id=line.tax_rate_id,
                    tax_rate_percent=tax_rate_percent,
                    line_total=line_total,
                    tax_amount=line_tax,
                )
            )
            zatca_lines.append(
                InvoiceLineData(
                    description=product.name if product else "",
                    quantity=qty,
                    unit_price=line.unit_price,
                    tax_rate_percent=tax_rate_percent,
                    line_total=line_total,
                    tax_amount=line_tax,
                )
            )

        invoice = SalesInvoice(
            id=uuid.uuid4(),
            company_id=company_id,
            branch_id=branch_id,
            partner_id=order.partner_id,
            sales_order_id=order.id,
            invoice_type=invoice_type,
            number=number,
            status="draft",
            # Inherits the order's own date rather than date.today() — was
            # previously forced to today on the mistaken assumption that
            # ZATCA's IssueDate requires it; it doesn't, the ZATCA payload
            # generates its own independent timestamp via now_iso() in
            # _run_zatca_pipeline below, completely decoupled from this
            # field. Forcing this silently discarded the order's date with
            # zero indication to the user (Owner-reported, confirmed via
            # SO-000020/INV-000015: order dated 2026-01-01, invoice dated
            # today with no way to tell why).
            invoice_date=order.order_date,
            subtotal_amount=subtotal,
            tax_amount=tax_total,
            total_amount=subtotal + tax_total,
            warehouse_id=order.warehouse_id,
            cost_center_id=order.cost_center_id,
        )
        try:
            await self.invoice_repo.add(invoice, invoice_lines)
        except IntegrityError as e:
            # ux_sales_invoice_number is the only unique constraint left
            # that can land here — multiple invoices per order are now a
            # legitimate shape (one per backorder release), so there is no
            # more "already invoiced" case to translate; a next_number()
            # collision between two different orders invoiced concurrently
            # is the only realistic cause.
            constraint = getattr(getattr(e.orig, "__cause__", None), "constraint_name", None)
            if constraint == "ux_sales_invoice_number":
                raise ValueError(
                    "An invoice was created concurrently with the same number — please retry"
                ) from e
            raise

        # The row locks taken during line selection above are what actually
        # prevent two concurrent requests from over-invoicing the same
        # line; this qty_invoiced update and the order-status recompute
        # just record the result once that's already guaranteed safe.
        for line, qty in selected:
            line.qty_invoiced += qty
        order.status = "done" if all(line.qty_invoiced >= line.qty for line in order_lines) else "partially_invoiced"

        submission = await self._run_zatca_pipeline(
            invoice=invoice,
            partner_name=partner.name,
            partner_vat=partner.vat_number,
            submission_mode=submission_mode,
            lines=zatca_lines,
            subtotal=subtotal,
            tax_total=tax_total,
            call_gateway_now=(submission_mode == "clearance"),
        )

        invoice.status = submission.status if submission_mode == "clearance" else "pending_submission"

        await self._post_journal_entry(invoice, branch_id=branch_id, created_by=created_by)
        await self._deduct_stock_for_lines(invoice, invoice_lines, created_by=created_by)

        return invoice, submission

    async def _deduct_stock_for_lines(self, invoice: SalesInvoice, lines, *, created_by: UUID) -> None:
        """FR-SAL-003 (deduct stock) wired directly at invoice time — M2
        deferred the standalone Delivery document, so this is where physical
        issue actually happens. Issues from the SalesOrder's own
        `warehouse_id` (chosen once, back at Quotation creation) when set;
        pre-existing orders created before that field existed fall back to
        the company's default warehouse, same as before. Skipped entirely
        if the company has no usable warehouse at all (service-only
        companies never set one up) or a line's product isn't stockable;
        per-line insufficient-stock errors propagate as a 422, matching
        FR-INV-007.
        """
        if self.inventory_service is None or self.warehouse_repo is None:
            return

        warehouse = None
        if invoice.warehouse_id is not None:
            warehouse = await self.warehouse_repo.get_by_id(invoice.warehouse_id)
        if warehouse is None:
            warehouse = await self.warehouse_repo.get_default_for_company(invoice.company_id)
        if warehouse is None:
            return

        locations = await self.location_repo.list_by_warehouse(warehouse.id)
        if not locations:
            return
        location = locations[0]

        cogs_account = await self.account_repo.get_by_code(invoice.company_id, ACCOUNT_CODE_COGS)
        inventory_account = await self.account_repo.get_by_code(invoice.company_id, ACCOUNT_CODE_INVENTORY)
        if not (cogs_account and inventory_account):
            raise ValueError("Default Chart of Accounts is not seeded for this company")

        for line in lines:
            product = await self.product_repo.get_by_id(line.product_id)
            if product is None or not product.is_stockable:
                continue

            move, cost = await self.inventory_service.issue_stock(
                company_id=invoice.company_id,
                product_id=line.product_id,
                location_id=location.id,
                qty=line.qty,
                valuation_method=self.valuation_method or "average",
                source_table="sales_invoice",
                source_id=invoice.id,
                move_type="delivery",
            )
            if cost <= 0:
                continue

            entry = await self.journal_entry_service.create_draft_entry(
                company_id=invoice.company_id,
                branch_id=invoice.branch_id,
                journal_code="GEN",
                entry_date=invoice.invoice_date,
                reference=f"COGS for {invoice.number}",
                lines=[
                    {"account_id": cogs_account.id, "debit": cost, "credit": 0},
                    {"account_id": inventory_account.id, "debit": 0, "credit": cost},
                ],
                created_by=created_by,
                source_table="sales_invoice",
                source_id=invoice.id,
            )
            await self.journal_entry_service.post_entry(entry_id=entry.id, company_id=invoice.company_id)

    async def issue_credit_note(
        self,
        *,
        original_invoice_id: UUID,
        company_id: UUID,
        branch_id: UUID,
        created_by: UUID,
        reason: str,
        restock: bool = True,
    ) -> tuple[SalesInvoice, ZatcaSubmission]:
        """UC-SAL-05 — a Credit Note follows the same ZATCA path (Clearance
        vs Reporting) as the original invoice it corrects (FR-SAL-005,
        FR-ZATCA-001..009). Product Owner request: `restock=True` (the
        default — a credit note usually means the goods are physically
        coming back) additionally reverses the original delivery, turning
        this into a true Sales Return rather than a financial-only
        correction."""
        original = await self.invoice_repo.get_by_id(original_invoice_id)
        if original is None or original.company_id != company_id:
            raise ValueError("Original invoice not found")
        if original.invoice_type not in ("tax", "simplified"):
            raise ValueError("Credit notes can only be issued against a tax or simplified invoice")

        original_lines = await self.invoice_repo.get_lines(original_invoice_id)
        partner = await self.partner_repo.get_by_id(original.partner_id)
        if partner is None:
            raise ValueError("Customer not found")

        submission_mode = "clearance" if original.invoice_type == "tax" else "reporting"
        number = await self.invoice_repo.next_number(company_id)

        credit_lines = [
            SalesInvoiceLine(
                id=uuid.uuid4(),
                company_id=company_id,
                product_id=line.product_id,
                description=line.description,
                qty=line.qty,
                unit_price=line.unit_price,
                tax_rate_id=line.tax_rate_id,
                tax_rate_percent=line.tax_rate_percent,
                line_total=line.line_total,
                tax_amount=line.tax_amount,
            )
            for line in original_lines
        ]
        zatca_lines = [
            InvoiceLineData(
                description=line.description,
                quantity=line.qty,
                unit_price=line.unit_price,
                tax_rate_percent=line.tax_rate_percent,
                line_total=line.line_total,
                tax_amount=line.tax_amount,
            )
            for line in original_lines
        ]

        credit_note = SalesInvoice(
            id=uuid.uuid4(),
            company_id=company_id,
            branch_id=branch_id,
            partner_id=original.partner_id,
            original_invoice_id=original.id,
            invoice_type="credit_note",
            number=number,
            status="draft",
            invoice_date=date.today(),
            subtotal_amount=original.subtotal_amount,
            tax_amount=original.tax_amount,
            total_amount=original.total_amount,
        )
        await self.invoice_repo.add(credit_note, credit_lines)

        submission = await self._run_zatca_pipeline(
            invoice=credit_note,
            partner_name=partner.name,
            partner_vat=partner.vat_number,
            submission_mode=submission_mode,
            lines=zatca_lines,
            subtotal=original.subtotal_amount,
            tax_total=original.tax_amount,
            call_gateway_now=(submission_mode == "clearance"),
        )
        credit_note.status = submission.status if submission_mode == "clearance" else "pending_submission"

        await self._post_journal_entry(credit_note, branch_id=branch_id, created_by=created_by, is_credit_note=True)

        if restock:
            await self._restock_for_credit_note(
                credit_note, original_invoice_id=original.id, branch_id=branch_id, created_by=created_by
            )

        return credit_note, submission

    async def issue_credit_note_for_lines(
        self,
        *,
        partner_id: UUID,
        company_id: UUID,
        branch_id: UUID,
        created_by: UUID,
        reason: str,
        lines: list[dict],
        original_invoice_id: UUID | None = None,
        restock: bool = True,
    ) -> tuple[SalesInvoice, ZatcaSubmission]:
        """Product Owner request: a Sales Return does not have to correspond
        to one whole invoice — it can be a freeform set of lines (possibly
        spanning several invoices, or none at all) with the original
        invoice number reduced to an OPTIONAL traceability field. Mirrors
        `issue_credit_note`'s ZATCA/JE/restock pipeline, but each line is
        computed from scratch (same flat-15% VAT convention already used by
        every other from-scratch line in this codebase, e.g.
        `issue_invoice_from_order`) instead of being copied verbatim from a
        single original invoice's own lines."""
        if not lines:
            raise ValueError("A credit note must have at least one line")

        partner = await self.partner_repo.get_by_id(partner_id)
        if partner is None or partner.company_id != company_id:
            raise ValueError("Customer not found")

        original: SalesInvoice | None = None
        if original_invoice_id is not None:
            original = await self.invoice_repo.get_by_id(original_invoice_id)
            if original is None or original.company_id != company_id:
                raise ValueError("Original invoice not found")
            if original.invoice_type not in ("tax", "simplified"):
                raise ValueError("A credit note can only reference a tax or simplified invoice")
            if original.partner_id != partner_id:
                raise ValueError("The original invoice does not belong to this customer")

        # Same B2B/B2C split as a brand-new invoice (FR-ZATCA-001) — there is
        # no single original invoice to inherit invoice_type/submission_mode
        # from here.
        submission_mode = "clearance" if partner.vat_number else "reporting"
        number = await self.invoice_repo.next_number(company_id)

        subtotal = Decimal("0")
        tax_total = Decimal("0")
        credit_lines: list[SalesInvoiceLine] = []
        zatca_lines: list[InvoiceLineData] = []

        for line in lines:
            product = await self.product_repo.get_by_id(line["product_id"])
            line_total = (line["qty"] * line["unit_price"]).quantize(Decimal("0.01"))
            tax_rate_percent = await self._resolve_tax_rate_percent(line["tax_rate_id"], company_id)
            line_tax = (line_total * tax_rate_percent / Decimal("100")).quantize(Decimal("0.01"))
            subtotal += line_total
            tax_total += line_tax
            credit_lines.append(
                SalesInvoiceLine(
                    id=uuid.uuid4(),
                    company_id=company_id,
                    product_id=line["product_id"],
                    description=product.name if product else "",
                    qty=line["qty"],
                    unit_price=line["unit_price"],
                    tax_rate_id=line["tax_rate_id"],
                    tax_rate_percent=tax_rate_percent,
                    line_total=line_total,
                    tax_amount=line_tax,
                )
            )
            zatca_lines.append(
                InvoiceLineData(
                    description=product.name if product else "",
                    quantity=line["qty"],
                    unit_price=line["unit_price"],
                    tax_rate_percent=tax_rate_percent,
                    line_total=line_total,
                    tax_amount=line_tax,
                )
            )

        credit_note = SalesInvoice(
            id=uuid.uuid4(),
            company_id=company_id,
            branch_id=branch_id,
            partner_id=partner_id,
            original_invoice_id=original.id if original is not None else None,
            invoice_type="credit_note",
            number=number,
            status="draft",
            invoice_date=date.today(),
            subtotal_amount=subtotal,
            tax_amount=tax_total,
            total_amount=subtotal + tax_total,
        )
        try:
            await self.invoice_repo.add(credit_note, credit_lines)
        except IntegrityError as e:
            raise ValueError("An invoice was created concurrently with the same number — please retry") from e

        submission = await self._run_zatca_pipeline(
            invoice=credit_note,
            partner_name=partner.name,
            partner_vat=partner.vat_number,
            submission_mode=submission_mode,
            lines=zatca_lines,
            subtotal=subtotal,
            tax_total=tax_total,
            call_gateway_now=(submission_mode == "clearance"),
        )
        credit_note.status = submission.status if submission_mode == "clearance" else "pending_submission"

        await self._post_journal_entry(credit_note, branch_id=branch_id, created_by=created_by, is_credit_note=True)

        if restock:
            await self._restock_for_credit_note_lines(
                credit_note,
                lines=credit_lines,
                original_invoice_id=original.id if original is not None else None,
                branch_id=branch_id,
                created_by=created_by,
            )

        return credit_note, submission

    async def _restock_for_credit_note(
        self, credit_note: SalesInvoice, *, original_invoice_id: UUID, branch_id: UUID, created_by: UUID
    ) -> None:
        """Sales Return: reverses the original delivery's stock moves at
        the exact same unit_cost those moves recorded (not the current
        average/FIFO cost, which may have drifted since the sale) — the
        same delivery StockMove rows already carry that cost per product
        (`unit_cost=result.unit_cost` set in `_deduct_stock_for_lines`),
        so this is a lookup, not a recompute. Silently a no-op when
        inventory isn't configured for this company, or the original sale
        never touched stock (e.g. a service-only invoice) — same guard
        `_deduct_stock_for_lines` itself uses."""
        if self.inventory_service is None or self.warehouse_repo is None:
            return

        original_moves = await self.inventory_service.list_moves_for_source(
            credit_note.company_id, "sales_invoice", original_invoice_id
        )
        delivery_moves = [m for m in original_moves if m.move_type == "delivery"]
        if not delivery_moves:
            return

        total_cost = Decimal("0")
        for move in delivery_moves:
            await self.inventory_service.receive_stock(
                company_id=credit_note.company_id,
                product_id=move.product_id,
                location_id=move.source_location_id,
                qty=move.qty,
                unit_cost=move.unit_cost,
                valuation_method=self.valuation_method or "average",
                source_table="sales_invoice",
                source_id=credit_note.id,
                move_type="return",
            )
            total_cost += (move.qty * move.unit_cost).quantize(Decimal("0.0001"))

        if total_cost <= 0:
            return

        cogs_account = await self.account_repo.get_by_code(credit_note.company_id, ACCOUNT_CODE_COGS)
        inventory_account = await self.account_repo.get_by_code(credit_note.company_id, ACCOUNT_CODE_INVENTORY)
        if not (cogs_account and inventory_account):
            raise ValueError("Default Chart of Accounts is not seeded for this company")

        entry = await self.journal_entry_service.create_draft_entry(
            company_id=credit_note.company_id,
            branch_id=branch_id,
            journal_code="GEN",
            entry_date=credit_note.invoice_date,
            reference=f"Inventory return for {credit_note.number}",
            lines=[
                {"account_id": inventory_account.id, "debit": total_cost, "credit": 0},
                {"account_id": cogs_account.id, "debit": 0, "credit": total_cost},
            ],
            created_by=created_by,
            source_table="sales_invoice",
            source_id=credit_note.id,
        )
        await self.journal_entry_service.post_entry(entry_id=entry.id, company_id=credit_note.company_id)

    async def _restock_for_credit_note_lines(
        self,
        credit_note: SalesInvoice,
        *,
        lines: list[SalesInvoiceLine],
        original_invoice_id: UUID | None,
        branch_id: UUID,
        created_by: UUID,
    ) -> None:
        """Freeform-lines counterpart of `_restock_for_credit_note`: each
        returned line may or may not correspond to a delivery on the
        (optional) original invoice, so the cost basis is resolved
        per-product rather than by replaying that invoice's own moves
        wholesale. When `original_invoice_id` is given, a product's exact
        original delivery unit_cost is used if that product was actually
        delivered on it (looked up once, kept in a dict); any other
        product — either because there is no original invoice at all, or
        this particular product wasn't on it — falls back to the location's
        current moving-average cost (the same cost basis a brand-new
        receipt with no unit_cost override would use elsewhere in this
        codebase). Silently a no-op when inventory isn't configured for
        this company."""
        if self.inventory_service is None or self.warehouse_repo is None:
            return

        # Owner request: restock into the same warehouse the original sale
        # was issued from — not always the company default — so a return
        # against a non-default warehouse actually lands back where it
        # left from. Falls back to the company default when there's no
        # traceable original invoice, or it predates warehouse_id.
        warehouse = None
        if original_invoice_id is not None:
            original_invoice = await self.invoice_repo.get_by_id(original_invoice_id)
            if original_invoice is not None and original_invoice.warehouse_id is not None:
                warehouse = await self.warehouse_repo.get_by_id(original_invoice.warehouse_id)
        if warehouse is None:
            warehouse = await self.warehouse_repo.get_default_for_company(credit_note.company_id)
        if warehouse is None:
            return
        locations = await self.location_repo.list_by_warehouse(warehouse.id)
        if not locations:
            return
        location = locations[0]

        original_cost_by_product: dict[UUID, Decimal] = {}
        if original_invoice_id is not None:
            original_moves = await self.inventory_service.list_moves_for_source(
                credit_note.company_id, "sales_invoice", original_invoice_id
            )
            for move in original_moves:
                if move.move_type == "delivery":
                    original_cost_by_product[move.product_id] = move.unit_cost

        total_cost = Decimal("0")
        any_restocked = False
        for line in lines:
            product = await self.product_repo.get_by_id(line.product_id)
            if product is None or not product.is_stockable:
                continue

            unit_cost = original_cost_by_product.get(line.product_id)
            if unit_cost is None:
                quant = await self.inventory_service.quant_repo.get(line.product_id, location.id)
                unit_cost = quant.moving_avg_cost if quant is not None else Decimal("0")
            if unit_cost <= 0:
                continue

            await self.inventory_service.receive_stock(
                company_id=credit_note.company_id,
                product_id=line.product_id,
                location_id=location.id,
                qty=line.qty,
                unit_cost=unit_cost,
                valuation_method=self.valuation_method or "average",
                source_table="sales_invoice",
                source_id=credit_note.id,
                move_type="return",
            )
            total_cost += (line.qty * unit_cost).quantize(Decimal("0.0001"))
            any_restocked = True

        if not any_restocked or total_cost <= 0:
            return

        cogs_account = await self.account_repo.get_by_code(credit_note.company_id, ACCOUNT_CODE_COGS)
        inventory_account = await self.account_repo.get_by_code(credit_note.company_id, ACCOUNT_CODE_INVENTORY)
        if not (cogs_account and inventory_account):
            raise ValueError("Default Chart of Accounts is not seeded for this company")

        entry = await self.journal_entry_service.create_draft_entry(
            company_id=credit_note.company_id,
            branch_id=branch_id,
            journal_code="GEN",
            entry_date=credit_note.invoice_date,
            reference=f"Inventory return for {credit_note.number}",
            lines=[
                {"account_id": inventory_account.id, "debit": total_cost, "credit": 0},
                {"account_id": cogs_account.id, "debit": 0, "credit": total_cost},
            ],
            created_by=created_by,
            source_table="sales_invoice",
            source_id=credit_note.id,
        )
        await self.journal_entry_service.post_entry(entry_id=entry.id, company_id=credit_note.company_id)

    async def _run_zatca_pipeline(
        self,
        *,
        invoice: SalesInvoice,
        partner_name: str,
        partner_vat: str | None,
        submission_mode: str,
        lines: list[InvoiceLineData],
        subtotal: Decimal,
        tax_total: Decimal,
        call_gateway_now: bool,
    ) -> ZatcaSubmission:
        icv, previous_hash = await self._next_icv_and_previous_hash(invoice.company_id)

        invoice_data = InvoiceData(
            invoice_id=invoice.id,
            invoice_number=invoice.number,
            invoice_type=invoice.invoice_type,
            issue_datetime_iso=now_iso(),
            seller_name=self.seller_name,
            seller_vat_number=self.seller_vat_number,
            buyer_name=partner_name,
            buyer_vat_number=partner_vat,
            currency_code=invoice.currency_code,
            subtotal_amount=subtotal,
            tax_amount=tax_total,
            total_amount=subtotal + tax_total,
            lines=lines,
        )

        if call_gateway_now:
            result = await self.zatca_processor.submit(
                invoice_data, previous_hash=previous_hash, icv=icv, submission_mode=submission_mode
            )
        else:
            # Local generation only (FR-ZATCA-007): QR/hash/XML are ready
            # immediately so the invoice can be delivered to the customer at
            # once; the actual Reporting call to ZATCA happens later via the
            # Celery task enqueued by the API route (see workers/tasks/zatca_tasks.py).
            prepared = self.zatca_processor.prepare(invoice_data, previous_hash=previous_hash, icv=icv)
            result = SubmissionResult(
                status="pending_submission",
                uuid_value=prepared.uuid_value,
                icv=prepared.icv,
                previous_hash=prepared.previous_hash,
                invoice_hash=prepared.invoice_hash,
                qr_payload=prepared.qr_payload,
                xml_document=prepared.xml_document,
            )

        submission = ZatcaSubmission(
            id=uuid.uuid4(),
            company_id=invoice.company_id,
            sales_invoice_id=invoice.id,
            uuid_value=result.uuid_value,
            icv=result.icv,
            previous_hash=result.previous_hash,
            invoice_hash=result.invoice_hash,
            qr_payload=result.qr_payload,
            xml_document=result.xml_document,
            submission_mode=submission_mode,
            status=result.status,
            zatca_response=result.zatca_response,
        )
        return await self.zatca_submission_repo.add(submission)

    async def _post_journal_entry(
        self, invoice: SalesInvoice, *, branch_id: UUID, created_by: UUID, is_credit_note: bool = False
    ) -> None:
        ar_account = await self.account_repo.get_by_code(invoice.company_id, ACCOUNT_CODE_AR)
        revenue_account = await self.account_repo.get_by_code(invoice.company_id, ACCOUNT_CODE_SALES_REVENUE)
        vat_account = await self.account_repo.get_by_code(invoice.company_id, ACCOUNT_CODE_VAT_PAYABLE)
        if not (ar_account and revenue_account and vat_account):
            raise ValueError("Default Chart of Accounts is not seeded for this company")

        if is_credit_note:
            # Opposite direction of a normal sales invoice: reduces revenue/
            # VAT payable and the customer's receivable balance.
            lines = [
                {
                    "account_id": revenue_account.id,
                    "debit": invoice.subtotal_amount,
                    "credit": 0,
                    "cost_center_id": invoice.cost_center_id,
                },
                {"account_id": ar_account.id, "debit": 0, "credit": invoice.total_amount},
            ]
            if invoice.tax_amount > 0:
                lines.append({"account_id": vat_account.id, "debit": invoice.tax_amount, "credit": 0})
        else:
            lines = [
                {"account_id": ar_account.id, "debit": invoice.total_amount, "credit": 0},
                {
                    "account_id": revenue_account.id,
                    "debit": 0,
                    "credit": invoice.subtotal_amount,
                    "cost_center_id": invoice.cost_center_id,
                },
            ]
            if invoice.tax_amount > 0:
                lines.append({"account_id": vat_account.id, "debit": 0, "credit": invoice.tax_amount})

        entry = await self.journal_entry_service.create_draft_entry(
            company_id=invoice.company_id,
            branch_id=branch_id,
            journal_code="SALES",
            entry_date=invoice.invoice_date,
            reference=invoice.number,
            lines=lines,
            created_by=created_by,
            source_table="sales_invoice",
            source_id=invoice.id,
        )
        posted = await self.journal_entry_service.post_entry(entry_id=entry.id, company_id=invoice.company_id)
        invoice.journal_entry_id = posted.id

    async def build_invoice_pdf(self, *, invoice_id: UUID, company_id: UUID, lang: str = "ar") -> bytes:
        """Document Delivery — the real invoice document (letterhead, bill-
        to, line items, totals, ZATCA QR), not the tabular reports the
        Standard Reporting Framework already covers. Shared by the download
        endpoint and `send_invoice_email` below — one render, two delivery
        paths."""
        invoice = await self.invoice_repo.get_by_id(invoice_id)
        if invoice is None or invoice.company_id != company_id:
            raise ValueError("Invoice not found")
        lines = await self.invoice_repo.get_lines(invoice_id)
        partner = await self.partner_repo.get_by_id(invoice.partner_id, include_archived=True)
        submission = await self.zatca_submission_repo.get_by_invoice_id(invoice_id)

        doc = InvoiceDocument(
            number=invoice.number,
            invoice_date=invoice.invoice_date,
            due_date=invoice.due_date,
            invoice_type=invoice.invoice_type,
            subtotal_amount=invoice.subtotal_amount,
            tax_amount=invoice.tax_amount,
            total_amount=invoice.total_amount,
            lines=[
                InvoiceLineRow(
                    description=line.description,
                    qty=line.qty,
                    unit_price=line.unit_price,
                    tax_rate_percent=line.tax_rate_percent,
                    line_total=line.line_total,
                    tax_amount=line.tax_amount,
                )
                for line in lines
            ],
            company_name=self.seller_name,
            company_name_ar=self.seller_name_ar or self.seller_name,
            company_vat_number=self.seller_vat_number,
            company_logo_path=self.seller_logo_path,
            partner_name=partner.name if partner else "",
            partner_vat_number=partner.vat_number if partner else None,
            qr_payload=submission.qr_payload if submission else None,
            lang=lang,
        )
        return render_invoice_pdf(doc)

    async def send_invoice_email(
        self,
        *,
        invoice_id: UUID,
        company_id: UUID,
        to_email: str | None = None,
        lang: str = "ar",
        mailer: Callable[..., Awaitable[None]] = default_send_email,
    ) -> SalesInvoice:
        """Document Delivery. Defaults to the customer's Partner.email on
        file; an explicit `to_email` overrides it (e.g. a one-off different
        recipient) without requiring the user to go edit the customer
        record first."""
        invoice = await self.invoice_repo.get_by_id(invoice_id)
        if invoice is None or invoice.company_id != company_id:
            raise ValueError("Invoice not found")
        partner = await self.partner_repo.get_by_id(invoice.partner_id, include_archived=True)
        recipient = to_email or (partner.email if partner else None)
        if not recipient:
            raise ValueError(
                "No email address on file for this customer, and none was provided for this send."
            )

        pdf_bytes = await self.build_invoice_pdf(invoice_id=invoice_id, company_id=company_id, lang=lang)
        subject = f"{self.seller_name} — Invoice {invoice.number}"
        body = (
            f"Dear {partner.name if partner else 'Customer'},\n\n"
            f"Please find attached invoice {invoice.number} dated {invoice.invoice_date.isoformat()}, "
            f"totaling {invoice.total_amount} {invoice.currency_code}.\n\n"
            f"Regards,\n{self.seller_name}"
        )
        await mailer(
            to=recipient,
            subject=subject,
            body=body,
            attachments=[EmailAttachment(filename=f"{invoice.number}.pdf", content=pdf_bytes)],
        )

        invoice.last_emailed_at = datetime.now(UTC).replace(tzinfo=None)
        invoice.last_emailed_to = recipient
        return invoice
