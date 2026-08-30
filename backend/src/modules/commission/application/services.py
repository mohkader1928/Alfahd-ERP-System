"""Commercial Performance Stage 3 — CommissionService.

Records a CommissionTransaction row at the exact moment a commission-bearing
event happens (invoice issuance, credit note, customer payment) — never
retroactively, and never by re-reading `SalesRepresentative.commission_rate`
for anything other than a brand-new event. A rate change on the
representative's master record can therefore never alter a historical
commission figure: each row is written once and is never updated again.

Called synchronously and inline from `SalesInvoiceService` and
`PaymentService`, the same way those services already call
`JournalEntryService`/the ZATCA pipeline directly — no event bus.
"""

import uuid
from datetime import date
from decimal import Decimal
from uuid import UUID

from src.modules.commission.infrastructure.models import CommissionTransaction
from src.modules.commission.infrastructure.repositories import CommissionTransactionRepository
from src.modules.identity.infrastructure.repositories import SalesRepresentativeRepository

_CENTS = Decimal("0.01")


class CommissionService:
    def __init__(
        self,
        txn_repo: CommissionTransactionRepository,
        sales_rep_repo: SalesRepresentativeRepository,
    ):
        self.txn_repo = txn_repo
        self.sales_rep_repo = sales_rep_repo

    async def record_sales_commission(
        self,
        *,
        company_id: UUID,
        representative_id: UUID,
        source_id: UUID,
        base_amount: Decimal,
        transaction_date: date,
    ) -> CommissionTransaction | None:
        """Invoice issuance. No row is written when the representative has
        no `commission_rate` configured — a rep can be tracked for sales
        attribution without necessarily participating in commission yet."""
        rep = await self.sales_rep_repo.get_by_id(company_id, representative_id)
        if rep is None or rep.commission_rate is None:
            return None
        return await self._write(
            company_id=company_id,
            representative_id=representative_id,
            commission_type="sales",
            source_table="sales_invoice",
            source_id=source_id,
            base_amount=base_amount,
            rate=rep.commission_rate,
            transaction_date=transaction_date,
        )

    async def reverse_sales_commission(
        self,
        *,
        company_id: UUID,
        representative_id: UUID,
        source_id: UUID,
        base_amount: Decimal,
        transaction_date: date,
        original_invoice_id: UUID | None,
    ) -> CommissionTransaction | None:
        """Credit note. Reuses the ORIGINAL invoice's own stored
        `commission_rate` (never today's rate) so the reversal exactly
        offsets what was actually commissioned, even if the representative's
        rate has since changed. Falls back to the representative's current
        rate only for a genuinely freeform return with no original invoice
        to inherit from — the same documented exception Stage 2C already
        established for `sales_rep_id` itself in that one case."""
        rate: Decimal | None = None
        if original_invoice_id is not None:
            original_txn = await self.txn_repo.get_by_source(
                company_id=company_id,
                source_table="sales_invoice",
                source_id=original_invoice_id,
                commission_type="sales",
            )
            if original_txn is not None:
                rate = original_txn.commission_rate
        if rate is None:
            rep = await self.sales_rep_repo.get_by_id(company_id, representative_id)
            if rep is None or rep.commission_rate is None:
                return None
            rate = rep.commission_rate
        return await self._write(
            company_id=company_id,
            representative_id=representative_id,
            commission_type="sales",
            source_table="sales_invoice",
            source_id=source_id,
            base_amount=-base_amount,
            rate=rate,
            transaction_date=transaction_date,
        )

    async def record_collection_commission(
        self,
        *,
        company_id: UUID,
        representative_id: UUID,
        source_id: UUID,
        base_amount: Decimal,
        transaction_date: date,
    ) -> CommissionTransaction | None:
        """Customer receipt. Each payment gets its own row, so a partial
        payment naturally yields a proportional commission with no special
        handling — the base_amount is the actual collected amount, not the
        invoice's total."""
        rep = await self.sales_rep_repo.get_by_id(company_id, representative_id)
        if rep is None or rep.commission_rate is None:
            return None
        return await self._write(
            company_id=company_id,
            representative_id=representative_id,
            commission_type="collection",
            source_table="payment",
            source_id=source_id,
            base_amount=base_amount,
            rate=rep.commission_rate,
            transaction_date=transaction_date,
        )

    async def _write(
        self,
        *,
        company_id: UUID,
        representative_id: UUID,
        commission_type: str,
        source_table: str,
        source_id: UUID,
        base_amount: Decimal,
        rate: Decimal,
        transaction_date: date,
    ) -> CommissionTransaction:
        amount = (base_amount * rate / Decimal("100")).quantize(_CENTS)
        txn = CommissionTransaction(
            id=uuid.uuid4(),
            company_id=company_id,
            representative_id=representative_id,
            commission_type=commission_type,
            source_table=source_table,
            source_id=source_id,
            base_amount=base_amount,
            commission_rate=rate,
            commission_amount=amount,
            transaction_date=transaction_date,
        )
        await self.txn_repo.add(txn)
        return txn
