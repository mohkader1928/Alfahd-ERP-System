"""P0-5 (3-Day Brief): Fixed Assets application service.

Registers a fixed asset and immediately posts its acquisition entry (Dr
the asset account, Cr wherever it was funded from — cash/bank or
accounts payable, chosen by the caller) exactly like every other
document type in this codebase posts on creation rather than sitting as
an unposted draft (PaymentService.record_payment, VendorBillService's
debit note, etc.).

Depreciation is a monthly, straight-line, manually-triggered batch run
("Run Depreciation for period") rather than a Celery Beat cron job —
this codebase's only existing scheduled-work infra (Celery) has no Beat
configured anywhere (invoke-on-demand only, confirmed via ZATCA's
report_invoice_task), and adding Beat is a bigger infrastructure change
than a 3-Day Brief item should carry. `run_depreciation` is safe to
call repeatedly for the same period: the UNIQUE(fixed_asset_id,
period_month) constraint plus an upfront existence check make it a
no-op the second time.

Disposal writes off the asset at its net book value and recognizes the
resulting gain or loss — the only place in this service two GL accounts
are picked by the caller rather than fixed by the asset record, since
where disposal proceeds land (cash vs. a receivable) and which P&L
account records the gain/loss are per-disposal decisions, not
per-asset ones.
"""

import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from src.modules.accounting.application.services import JournalEntryService
from src.modules.accounting.infrastructure.repositories import AccountRepository
from src.modules.fixed_assets.domain.entities import AssetAlreadyDisposedError
from src.modules.fixed_assets.infrastructure.models import FixedAsset, FixedAssetDepreciationEntry
from src.modules.fixed_assets.infrastructure.repositories import (
    FixedAssetDepreciationRepository,
    FixedAssetRepository,
)

FOUR_DP = Decimal("0.0001")


def _month_start(d: date) -> date:
    return date(d.year, d.month, 1)


class FixedAssetService:
    def __init__(
        self,
        asset_repo: FixedAssetRepository,
        depreciation_repo: FixedAssetDepreciationRepository,
        account_repo: AccountRepository,
        journal_entry_service: JournalEntryService,
    ):
        self.asset_repo = asset_repo
        self.depreciation_repo = depreciation_repo
        self.account_repo = account_repo
        self.journal_entry_service = journal_entry_service

    async def create_asset(
        self,
        *,
        company_id: UUID,
        branch_id: UUID,
        name: str,
        name_ar: str | None,
        fixed_asset_account_id: UUID,
        accumulated_depreciation_account_id: UUID,
        depreciation_expense_account_id: UUID,
        funding_account_id: UUID,
        acquisition_date: date,
        cost: Decimal,
        salvage_value: Decimal,
        useful_life_months: int,
        created_by: UUID,
    ) -> FixedAsset:
        fixed_asset_account = await self._require_account(fixed_asset_account_id, company_id)
        accum_account = await self._require_account(accumulated_depreciation_account_id, company_id)
        expense_account = await self._require_account(depreciation_expense_account_id, company_id)
        funding_account = await self._require_account(funding_account_id, company_id)
        for account in (fixed_asset_account, accum_account, expense_account, funding_account):
            if account.is_group:
                raise ValueError(f"Cannot post to {account.code} — {account.name}: it is a group account")
        if salvage_value >= cost:
            raise ValueError("Salvage value must be less than cost")
        if useful_life_months <= 0:
            raise ValueError("Useful life must be at least 1 month")

        number = await self.asset_repo.next_number(company_id)
        asset = FixedAsset(
            id=uuid.uuid4(),
            company_id=company_id,
            branch_id=branch_id,
            asset_code=number,
            name=name,
            name_ar=name_ar,
            fixed_asset_account_id=fixed_asset_account_id,
            accumulated_depreciation_account_id=accumulated_depreciation_account_id,
            depreciation_expense_account_id=depreciation_expense_account_id,
            acquisition_date=acquisition_date,
            cost=cost,
            salvage_value=salvage_value,
            useful_life_months=useful_life_months,
            created_by=created_by,
        )
        try:
            await self.asset_repo.add(asset)
        except IntegrityError as e:
            raise ValueError("A fixed asset was created concurrently with the same code — please retry") from e

        entry = await self.journal_entry_service.create_draft_entry(
            company_id=company_id,
            branch_id=branch_id,
            journal_code="GEN",
            entry_date=acquisition_date,
            reference=asset.asset_code,
            description=f"Acquisition of {name}",
            lines=[
                {"account_id": fixed_asset_account_id, "debit": cost, "credit": 0},
                {"account_id": funding_account_id, "debit": 0, "credit": cost},
            ],
            created_by=created_by,
            source_table="fixed_asset",
            source_id=asset.id,
        )
        posted = await self.journal_entry_service.post_entry(entry_id=entry.id, company_id=company_id)
        asset.acquisition_journal_entry_id = posted.id
        return asset

    async def get_asset(self, company_id: UUID, asset_id: UUID) -> dict | None:
        asset = await self.asset_repo.get_by_id(asset_id)
        if asset is None or asset.company_id != company_id:
            return None
        return await self._to_dict(asset)

    async def list_assets(self, company_id: UUID) -> list[dict]:
        assets = await self.asset_repo.list_by_company(company_id)
        return [await self._to_dict(asset) for asset in assets]

    async def list_depreciation_entries(self, company_id: UUID, asset_id: UUID) -> list[FixedAssetDepreciationEntry]:
        asset = await self.asset_repo.get_by_id(asset_id)
        if asset is None or asset.company_id != company_id:
            raise ValueError("Fixed asset not found")
        return await self.depreciation_repo.list_for_asset(asset_id)

    async def run_depreciation(
        self, *, company_id: UUID, branch_id: UUID, period_month: date, created_by: UUID
    ) -> dict:
        period = _month_start(period_month)
        assets = await self.asset_repo.list_by_company(company_id, active_only=True)
        posted: list[dict] = []
        skipped: list[dict] = []
        for asset in assets:
            # Full-month convention: an asset acquired on any day within a
            # month is eligible for that month's depreciation, not just one
            # acquired exactly on the 1st. Comparing the raw acquisition_date
            # against the period's month-start (rather than acquisition's own
            # month-start) would wrongly exclude every asset from its own
            # acquisition month unless bought on day 1 — found live testing
            # an asset acquired 2026-08-09 against period_month=2026-08-01.
            if _month_start(asset.acquisition_date) > period:
                skipped.append(
                    {"asset_id": asset.id, "asset_code": asset.asset_code, "reason": "not_yet_acquired"}
                )
                continue
            existing = await self.depreciation_repo.get_for_asset_and_period(asset.id, period)
            if existing is not None:
                skipped.append({"asset_id": asset.id, "asset_code": asset.asset_code, "reason": "already_posted"})
                continue

            depreciable_base = asset.cost - asset.salvage_value
            already = await self.depreciation_repo.sum_for_asset(asset.id)
            remaining = depreciable_base - already
            if remaining <= 0:
                skipped.append({"asset_id": asset.id, "asset_code": asset.asset_code, "reason": "fully_depreciated"})
                continue

            monthly_amount = (depreciable_base / asset.useful_life_months).quantize(
                FOUR_DP, rounding=ROUND_HALF_UP
            )
            amount = min(monthly_amount, remaining)

            entry = await self.journal_entry_service.create_draft_entry(
                company_id=company_id,
                branch_id=branch_id,
                journal_code="GEN",
                entry_date=period,
                reference=asset.asset_code,
                description=f"Depreciation for {asset.name} — {period.isoformat()[:7]}",
                lines=[
                    {"account_id": asset.depreciation_expense_account_id, "debit": amount, "credit": 0},
                    {"account_id": asset.accumulated_depreciation_account_id, "debit": 0, "credit": amount},
                ],
                created_by=created_by,
                source_table="fixed_asset",
                source_id=asset.id,
            )
            posted_entry = await self.journal_entry_service.post_entry(entry_id=entry.id, company_id=company_id)

            depreciation_entry = FixedAssetDepreciationEntry(
                id=uuid.uuid4(),
                company_id=company_id,
                fixed_asset_id=asset.id,
                period_month=period,
                amount=amount,
                journal_entry_id=posted_entry.id,
            )
            try:
                await self.depreciation_repo.add(depreciation_entry)
            except IntegrityError as e:
                raise ValueError(
                    f"Depreciation for {asset.asset_code} was posted concurrently for this period — please retry"
                ) from e

            posted.append({"asset_id": asset.id, "asset_code": asset.asset_code, "amount": amount})

        return {
            "period_month": period,
            "assets_posted": len(posted),
            "assets_skipped": len(skipped),
            "total_amount": sum((p["amount"] for p in posted), start=Decimal("0")),
            "posted": posted,
            "skipped": skipped,
        }

    async def dispose_asset(
        self,
        *,
        company_id: UUID,
        branch_id: UUID,
        asset_id: UUID,
        disposal_date: date,
        proceeds: Decimal,
        proceeds_account_id: UUID | None,
        gain_loss_account_id: UUID | None,
        created_by: UUID,
    ) -> FixedAsset:
        asset = await self.asset_repo.get_by_id_for_update(asset_id)
        if asset is None or asset.company_id != company_id:
            raise ValueError("Fixed asset not found")
        if asset.disposed_at is not None:
            raise AssetAlreadyDisposedError(f"{asset.asset_code} was already disposed on {asset.disposed_at}")
        if proceeds > 0 and proceeds_account_id is None:
            raise ValueError("proceeds_account_id is required when disposal proceeds are greater than zero")

        accumulated = await self.depreciation_repo.sum_for_asset(asset.id)
        net_book_value = asset.cost - accumulated
        gain_loss = proceeds - net_book_value
        if gain_loss != 0 and gain_loss_account_id is None:
            raise ValueError("gain_loss_account_id is required — this disposal results in a gain or loss")

        lines = [{"account_id": asset.accumulated_depreciation_account_id, "debit": accumulated, "credit": 0}]
        if proceeds > 0:
            lines.append({"account_id": proceeds_account_id, "debit": proceeds, "credit": 0})
        if gain_loss < 0:
            lines.append({"account_id": gain_loss_account_id, "debit": -gain_loss, "credit": 0})
        lines.append({"account_id": asset.fixed_asset_account_id, "debit": 0, "credit": asset.cost})
        if gain_loss > 0:
            lines.append({"account_id": gain_loss_account_id, "debit": 0, "credit": gain_loss})

        entry = await self.journal_entry_service.create_draft_entry(
            company_id=company_id,
            branch_id=branch_id,
            journal_code="GEN",
            entry_date=disposal_date,
            reference=asset.asset_code,
            description=f"Disposal of {asset.name}",
            lines=lines,
            created_by=created_by,
            source_table="fixed_asset",
            source_id=asset.id,
        )
        posted = await self.journal_entry_service.post_entry(entry_id=entry.id, company_id=company_id)

        asset.disposed_at = disposal_date
        asset.disposal_proceeds = proceeds
        asset.disposal_journal_entry_id = posted.id
        return asset

    async def _require_account(self, account_id: UUID, company_id: UUID):
        account = await self.account_repo.get_by_id(account_id)
        if account is None or account.company_id != company_id:
            raise ValueError(f"Account not found in this company: {account_id}")
        return account

    async def _to_dict(self, asset: FixedAsset) -> dict:
        accumulated = await self.depreciation_repo.sum_for_asset(asset.id)
        depreciable_base = asset.cost - asset.salvage_value
        net_book_value = asset.cost - accumulated
        return {
            "id": asset.id,
            "company_id": asset.company_id,
            "asset_code": asset.asset_code,
            "name": asset.name,
            "name_ar": asset.name_ar,
            "fixed_asset_account_id": asset.fixed_asset_account_id,
            "accumulated_depreciation_account_id": asset.accumulated_depreciation_account_id,
            "depreciation_expense_account_id": asset.depreciation_expense_account_id,
            "acquisition_date": asset.acquisition_date,
            "cost": asset.cost,
            "salvage_value": asset.salvage_value,
            "useful_life_months": asset.useful_life_months,
            "accumulated_depreciation": accumulated,
            "net_book_value": net_book_value,
            "fully_depreciated": accumulated >= depreciable_base,
            "status": "disposed" if asset.disposed_at is not None else "active",
            "disposed_at": asset.disposed_at,
            "disposal_proceeds": asset.disposal_proceeds,
        }
