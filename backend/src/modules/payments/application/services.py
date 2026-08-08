"""Phase 17D: Payments application service.

Records a customer payment against sales invoices, or a vendor payment
against vendor bills, allocates the amount across one or more target
documents, and posts the matching cash/bank journal entry — reusing
`JournalEntryService` exactly like Sales/Purchasing/Inventory already do,
including the same idempotency discipline Phase 16B established (the
route commits once, after everything below has flushed within the same
transaction — no partial-commit window).
"""

import uuid
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from src.modules.accounting.application.services import JournalEntryService
from src.modules.accounting.infrastructure.repositories import AccountRepository
from src.modules.identity.infrastructure.repositories import PartnerRepository
from src.modules.payments.domain.entities import InvalidAllocationTargetError, OverAllocationError
from src.modules.payments.infrastructure.models import Payment, PaymentAllocation
from src.modules.payments.infrastructure.repositories import PaymentRepository
from src.modules.purchasing.infrastructure.repositories import VendorBillRepository
from src.modules.sales.infrastructure.repositories import SalesInvoiceRepository

ACCOUNT_CODE_AR = "1200"
ACCOUNT_CODE_AP = "2100"


class PaymentService:
    def __init__(
        self,
        payment_repo: PaymentRepository,
        sales_invoice_repo: SalesInvoiceRepository,
        vendor_bill_repo: VendorBillRepository,
        account_repo: AccountRepository,
        journal_entry_service: JournalEntryService,
    ):
        self.payment_repo = payment_repo
        self.sales_invoice_repo = sales_invoice_repo
        self.vendor_bill_repo = vendor_bill_repo
        self.account_repo = account_repo
        self.journal_entry_service = journal_entry_service

    async def record_payment(
        self,
        *,
        company_id: UUID,
        branch_id: UUID,
        partner_id: UUID,
        payment_type: str,
        payment_date: date,
        amount: Decimal,
        account_id: UUID,
        reference: str | None,
        allocations: list[dict],
        created_by: UUID,
    ) -> Payment:
        account = await self.account_repo.get_by_id(account_id)
        if account is None or account.company_id != company_id:
            raise ValueError("Cash/bank account not found")

        allocated_total = Decimal("0")
        prepared_allocations: list[PaymentAllocation] = []
        for item in allocations:
            target_amount = Decimal(str(item["amount"]))
            if payment_type == "customer":
                # Row-locked read: two concurrent payments allocating to the
                # SAME invoice must not both pass this check before either
                # commits — the second waits for the first's transaction to
                # end, then re-reads the now-updated already_allocated sum.
                invoice = await self.sales_invoice_repo.get_by_id_for_update(
                    item["sales_invoice_id"]
                )
                if invoice is None or invoice.company_id != company_id:
                    raise ValueError("Sales invoice not found")
                if invoice.partner_id != partner_id:
                    raise InvalidAllocationTargetError(
                        "Cannot allocate a customer payment to another customer's invoice"
                    )
                already_allocated = await self.payment_repo.sum_allocated_for_sales_invoice(
                    invoice.id
                )
                if already_allocated + target_amount > invoice.total_amount:
                    raise OverAllocationError(
                        f"Allocation exceeds invoice {invoice.number}'s outstanding balance"
                    )
                prepared_allocations.append(
                    PaymentAllocation(
                        id=uuid.uuid4(),
                        company_id=company_id,
                        sales_invoice_id=invoice.id,
                        amount=target_amount,
                    )
                )
            elif payment_type == "vendor":
                bill = await self.vendor_bill_repo.get_by_id_for_update(item["vendor_bill_id"])
                if bill is None or bill.company_id != company_id:
                    raise ValueError("Vendor bill not found")
                if bill.partner_id != partner_id:
                    raise InvalidAllocationTargetError(
                        "Cannot allocate a vendor payment to another vendor's bill"
                    )
                already_allocated = await self.payment_repo.sum_allocated_for_vendor_bill(bill.id)
                if already_allocated + target_amount > bill.total_amount:
                    raise OverAllocationError(
                        f"Allocation exceeds bill {bill.number}'s outstanding balance"
                    )
                prepared_allocations.append(
                    PaymentAllocation(
                        id=uuid.uuid4(),
                        company_id=company_id,
                        vendor_bill_id=bill.id,
                        amount=target_amount,
                    )
                )
            else:
                raise ValueError(f"Unknown payment_type: {payment_type}")

            allocated_total += target_amount

        if allocated_total > amount:
            # The remainder (amount - allocated_total) is fine — it's an
            # unallocated credit on the payment, not an error. Allocating
            # MORE than the payment is worth is the actual invalid case.
            raise OverAllocationError("Total allocated amount exceeds the payment amount")

        number = await self.payment_repo.next_number(company_id)
        payment = Payment(
            id=uuid.uuid4(),
            company_id=company_id,
            branch_id=branch_id,
            partner_id=partner_id,
            payment_type=payment_type,
            number=number,
            payment_date=payment_date,
            amount=amount,
            account_id=account_id,
            reference=reference,
            created_by=created_by,
        )
        try:
            await self.payment_repo.add(payment, prepared_allocations)
        except IntegrityError as e:
            raise ValueError("A payment was created concurrently with the same number — please retry") from e
        await self._post_journal_entry(payment, branch_id=branch_id, created_by=created_by)
        return payment

    async def get_sales_invoice_balance(self, company_id: UUID, invoice_id: UUID) -> dict | None:
        """Payment status is computed on demand from `payment_allocation`,
        not a persisted/mutable column on `sales_invoice` — avoids the
        exact class of stored-state-drift bug Phase 16B was created to
        close (a denormalized balance can only go out of sync with what
        was actually allocated; a live SUM() can't)."""
        invoice = await self.sales_invoice_repo.get_by_id(invoice_id)
        if invoice is None or invoice.company_id != company_id:
            return None
        amount_paid = await self.payment_repo.sum_allocated_for_sales_invoice(invoice.id)
        return _balance_dict(invoice.total_amount, amount_paid)

    async def get_vendor_bill_balance(self, company_id: UUID, bill_id: UUID) -> dict | None:
        bill = await self.vendor_bill_repo.get_by_id(bill_id)
        if bill is None or bill.company_id != company_id:
            return None
        amount_paid = await self.payment_repo.sum_allocated_for_vendor_bill(bill.id)
        return _balance_dict(bill.total_amount, amount_paid)

    async def _post_journal_entry(
        self, payment: Payment, *, branch_id: UUID, created_by: UUID
    ) -> None:
        if payment.payment_type == "customer":
            ar_account = await self.account_repo.get_by_code(payment.company_id, ACCOUNT_CODE_AR)
            if ar_account is None:
                raise ValueError("Default Chart of Accounts is not seeded for this company")
            # Customer payment: cash/bank increases, receivable decreases.
            lines = [
                {"account_id": payment.account_id, "debit": payment.amount, "credit": 0},
                {"account_id": ar_account.id, "debit": 0, "credit": payment.amount},
            ]
        else:
            ap_account = await self.account_repo.get_by_code(payment.company_id, ACCOUNT_CODE_AP)
            if ap_account is None:
                raise ValueError("Default Chart of Accounts is not seeded for this company")
            # Vendor payment: payable decreases, cash/bank decreases.
            lines = [
                {"account_id": ap_account.id, "debit": payment.amount, "credit": 0},
                {"account_id": payment.account_id, "debit": 0, "credit": payment.amount},
            ]

        entry = await self.journal_entry_service.create_draft_entry(
            company_id=payment.company_id,
            branch_id=branch_id,
            journal_code="BANK",
            entry_date=payment.payment_date,
            reference=payment.number,
            lines=lines,
            created_by=created_by,
            source_table="payment",
            source_id=payment.id,
        )
        posted = await self.journal_entry_service.post_entry(
            entry_id=entry.id, company_id=payment.company_id
        )
        payment.journal_entry_id = posted.id


class SubledgerService:
    """Milestone 1b — Customer/Vendor Subledgers and AR/AP Aging.

    Deliberately placed in the Payments module, not Accounting: this is
    the one module that already reads Sales and Purchasing (read-only) as
    well as Accounting, matching the one-way dependency shape this needs.
    Putting it in Accounting would mean Accounting starts depending on
    Sales/Purchasing/Payments, which nothing else in the system does.

    Every figure here is derived from the same `sales_invoice`/
    `vendor_bill`/`payment_allocation` rows Payments already reads for its
    own balance endpoints -- no new table, no separate ledger, so a
    Subledger can never drift from what Payments (and, through the Journal
    Entries those documents post, the General Ledger) already show.
    """

    def __init__(
        self,
        payment_repo: PaymentRepository,
        sales_invoice_repo: SalesInvoiceRepository,
        vendor_bill_repo: VendorBillRepository,
        partner_repo: PartnerRepository,
    ):
        self.payment_repo = payment_repo
        self.sales_invoice_repo = sales_invoice_repo
        self.vendor_bill_repo = vendor_bill_repo
        self.partner_repo = partner_repo

    async def customer_subledger(
        self, *, company_id: UUID, partner_id: UUID, date_from: date, date_to: date
    ) -> dict:
        invoices = await self.sales_invoice_repo.list_by_company(company_id, partner_id=partner_id)
        allocations = await self.payment_repo.list_allocations_for_partner(
            company_id, partner_id, "customer"
        )
        movements = _customer_movements(invoices, allocations)
        return _build_subledger(movements, date_from, date_to)

    async def vendor_subledger(
        self, *, company_id: UUID, partner_id: UUID, date_from: date, date_to: date
    ) -> dict:
        bills = await self.vendor_bill_repo.list_by_company(company_id, partner_id=partner_id)
        allocations = await self.payment_repo.list_allocations_for_partner(
            company_id, partner_id, "vendor"
        )
        movements = _vendor_movements(bills, allocations)
        return _build_subledger(movements, date_from, date_to)

    async def ar_aging(self, *, company_id: UUID, as_of_date: date) -> list[dict]:
        invoices = await self.sales_invoice_repo.list_by_company(company_id, limit=5000)
        partners = {
            p.id: p
            for p in await self.partner_repo.list_by_company(company_id, customers_only=True)
        }
        # A credit note reduces the specific invoice it was issued against
        # (SalesInvoice.original_invoice_id), not just the customer's
        # overall AR balance -- built once, up front, so a fully
        # credit-noted invoice is correctly excluded below rather than
        # still showing its full original total as overdue.
        credited_by_original_invoice: dict = {}
        for row in invoices:
            if (
                row.invoice_type == "credit_note"
                and row.original_invoice_id
                and row.journal_entry_id
            ):
                credited_by_original_invoice[row.original_invoice_id] = (
                    credited_by_original_invoice.get(row.original_invoice_id, Decimal("0"))
                    + row.total_amount
                )

        rows = []
        for invoice in invoices:
            # Only real, posted invoices count as an open AR item -- a
            # credit note is never itself aged as an open item (it reduces
            # its original invoice's balance instead, via the map above),
            # and an invoice that never posted a Journal Entry was never
            # real AR.
            if invoice.invoice_type == "credit_note" or invoice.journal_entry_id is None:
                continue
            paid = await self.payment_repo.sum_allocated_for_sales_invoice(invoice.id)
            credited = credited_by_original_invoice.get(invoice.id, Decimal("0"))
            balance_due = invoice.total_amount - paid - credited
            if balance_due <= 0:
                continue
            partner = partners.get(invoice.partner_id)
            rows.append(
                _aging_row(
                    partner,
                    invoice.id,
                    invoice.number,
                    invoice.due_date,
                    invoice.invoice_date,
                    balance_due,
                    as_of_date,
                )
            )
        return rows

    async def ap_aging(self, *, company_id: UUID, as_of_date: date) -> list[dict]:
        bills = await self.vendor_bill_repo.list_by_company(company_id)
        partners = {
            p.id: p for p in await self.partner_repo.list_by_company(company_id, vendors_only=True)
        }
        rows = []
        for bill in bills:
            if bill.journal_entry_id is None:
                continue
            paid = await self.payment_repo.sum_allocated_for_vendor_bill(bill.id)
            balance_due = bill.total_amount - paid
            if balance_due <= 0:
                continue
            partner = partners.get(bill.partner_id)
            rows.append(
                _aging_row(
                    partner,
                    bill.id,
                    bill.number,
                    bill.due_date,
                    bill.bill_date,
                    balance_due,
                    as_of_date,
                )
            )
        return rows


def _customer_movements(invoices: list, allocations: list[dict]) -> list[dict]:
    movements = []
    for inv in invoices:
        if inv.journal_entry_id is None:
            continue  # never actually posted -- not a real AR movement
        if inv.invoice_type == "credit_note":
            movements.append(
                {
                    "date": inv.invoice_date,
                    "movement_type": "credit_note",
                    "document_type": "sales_invoice",
                    "document_id": inv.id,
                    "reference": inv.number,
                    "debit": Decimal("0.0000"),
                    "credit": inv.total_amount,
                }
            )
        else:
            movements.append(
                {
                    "date": inv.invoice_date,
                    "movement_type": "invoice",
                    "document_type": "sales_invoice",
                    "document_id": inv.id,
                    "reference": inv.number,
                    "debit": inv.total_amount,
                    "credit": Decimal("0.0000"),
                }
            )
    for alloc in allocations:
        if alloc["sales_invoice_id"] is None:
            continue
        movements.append(
            {
                "date": alloc["payment_date"],
                "movement_type": "payment",
                "document_type": "payment",
                "document_id": alloc["payment_id"],
                "reference": alloc["number"],
                "debit": Decimal("0.0000"),
                "credit": alloc["amount"],
            }
        )
    return movements


def _vendor_movements(bills: list, allocations: list[dict]) -> list[dict]:
    movements = []
    for bill in bills:
        if bill.journal_entry_id is None:
            continue
        movements.append(
            {
                "date": bill.bill_date,
                "movement_type": "bill",
                "document_type": "vendor_bill",
                "document_id": bill.id,
                "reference": bill.number,
                "debit": Decimal("0.0000"),
                "credit": bill.total_amount,
            }
        )
    for alloc in allocations:
        if alloc["vendor_bill_id"] is None:
            continue
        movements.append(
            {
                "date": alloc["payment_date"],
                "movement_type": "payment",
                "document_type": "payment",
                "document_id": alloc["payment_id"],
                "reference": alloc["number"],
                "debit": alloc["amount"],
                "credit": Decimal("0.0000"),
            }
        )
    return movements


def _build_subledger(movements: list[dict], date_from: date, date_to: date) -> dict:
    movements.sort(key=lambda m: m["date"])
    opening = Decimal("0.0000")
    for m in movements:
        if m["date"] < date_from:
            opening += m["debit"] - m["credit"]

    running = opening
    lines = []
    for m in movements:
        if date_from <= m["date"] <= date_to:
            running += m["debit"] - m["credit"]
            lines.append({**m, "running_balance": running})

    return {"opening_balance": opening, "lines": lines, "closing_balance": running}


def _aging_row(
    partner,
    document_id: UUID,
    number: str,
    due_date: date | None,
    fallback_date: date,
    balance_due: Decimal,
    as_of_date: date,
) -> dict:
    effective_due = due_date or fallback_date
    days_overdue = (as_of_date - effective_due).days
    if days_overdue <= 0:
        bucket = "current"
    elif days_overdue <= 30:
        bucket = "1_30"
    elif days_overdue <= 60:
        bucket = "31_60"
    elif days_overdue <= 90:
        bucket = "61_90"
    else:
        bucket = "over_90"
    return {
        "partner_id": partner.id if partner else None,
        "partner_name": partner.name if partner else "Unknown",
        "document_id": document_id,
        "number": number,
        "due_date": effective_due,
        "balance_due": balance_due,
        "days_overdue": days_overdue,
        "bucket": bucket,
    }


def _balance_dict(total_amount: Decimal, amount_paid: Decimal) -> dict:
    balance_due = total_amount - amount_paid
    if amount_paid <= 0:
        payment_status = "unpaid"
    elif balance_due <= 0:
        payment_status = "paid"
    else:
        payment_status = "partially_paid"
    return {
        "total_amount": total_amount,
        "amount_paid": amount_paid,
        "balance_due": balance_due,
        "payment_status": payment_status,
    }
