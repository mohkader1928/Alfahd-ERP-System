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
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from src.modules.accounting.application.services import JournalEntryService
from src.modules.accounting.infrastructure.repositories import AccountRepository
from src.modules.fixed_assets.domain.entities import AssetAlreadyDisposedError
from src.modules.fixed_assets.infrastructure.models import (
    FixedAsset,
    FixedAssetCategory,
    FixedAssetDepreciationEntry,
)
from src.modules.fixed_assets.infrastructure.repositories import (
    FixedAssetCategoryRepository,
    FixedAssetDepreciationRepository,
    FixedAssetRepository,
)

FOUR_DP = Decimal("0.0001")


def _month_start(d: date) -> date:
    return date(d.year, d.month, 1)


def _month_end(d: date) -> date:
    next_month = date(d.year + 1, 1, 1) if d.month == 12 else date(d.year, d.month + 1, 1)
    return next_month - timedelta(days=1)


class FixedAssetService:
    def __init__(
        self,
        asset_repo: FixedAssetRepository,
        depreciation_repo: FixedAssetDepreciationRepository,
        account_repo: AccountRepository,
        journal_entry_service: JournalEntryService,
        category_repo: FixedAssetCategoryRepository | None = None,
    ):
        self.asset_repo = asset_repo
        self.depreciation_repo = depreciation_repo
        self.account_repo = account_repo
        self.journal_entry_service = journal_entry_service
        self.category_repo = category_repo

    async def create_asset(
        self,
        *,
        company_id: UUID,
        branch_id: UUID,
        name: str,
        name_ar: str | None,
        category_id: UUID | None = None,
        fixed_asset_account_id: UUID,
        accumulated_depreciation_account_id: UUID,
        depreciation_expense_account_id: UUID,
        funding_account_id: UUID,
        acquisition_date: date,
        cost: Decimal,
        salvage_value: Decimal,
        useful_life_months: int,
        created_by: UUID,
        status: str = "active",
    ) -> FixedAsset:
        if status not in ("active", "idle", "under_maintenance"):
            raise ValueError("Invalid asset status")
        if category_id is not None:
            assert self.category_repo is not None
            category = await self.category_repo.get_by_id(company_id, category_id)
            if category is None:
                raise ValueError("Invalid asset category")
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
            category_id=category_id,
            fixed_asset_account_id=fixed_asset_account_id,
            accumulated_depreciation_account_id=accumulated_depreciation_account_id,
            depreciation_expense_account_id=depreciation_expense_account_id,
            acquisition_date=acquisition_date,
            cost=cost,
            salvage_value=salvage_value,
            useful_life_months=useful_life_months,
            created_by=created_by,
            status=status,
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

    async def update_asset_status(self, *, company_id: UUID, asset_id: UUID, status: str) -> FixedAsset:
        """Owner decision (2026-08-19): Operational Status only, informational
        -- never touches depreciation eligibility (`run_depreciation` still
        keys solely on `disposed_at`). Disposal is its own irreversible
        action (`dispose_asset`) and stays the only way to actually stop an
        asset's operational life; this endpoint cannot set or clear it."""
        if status not in ("active", "idle", "under_maintenance"):
            raise ValueError("Invalid asset status")
        asset = await self.asset_repo.get_by_id(asset_id)
        if asset is None or asset.company_id != company_id:
            raise ValueError("Fixed asset not found")
        if asset.disposed_at is not None:
            raise ValueError("Cannot change the operational status of a disposed asset")
        asset.status = status
        return asset

    async def get_projected_schedule(self, *, company_id: UUID, asset_id: UUID) -> dict:
        """Forward-looking Depreciation Schedule (Owner brief §8) -- the
        FULL straight-line schedule from acquisition to full depreciation,
        one row per month. Already-posted months use their actual posted
        amount (so the final, rounding-capped period matches the GL
        exactly); not-yet-run months are projected with the same formula
        `run_depreciation` itself would use, purely for display -- this
        method posts nothing."""
        asset = await self.asset_repo.get_by_id(asset_id)
        if asset is None or asset.company_id != company_id:
            raise ValueError("Fixed asset not found")
        entries = await self.depreciation_repo.list_for_asset(asset_id)
        posted_by_period = {e.period_month: e.amount for e in entries}

        depreciable_base = asset.cost - asset.salvage_value
        monthly_amount = (depreciable_base / asset.useful_life_months).quantize(FOUR_DP, rounding=ROUND_HALF_UP)

        lines = []
        accumulated = Decimal("0")
        period = _month_start(asset.acquisition_date)
        # Bounded by useful_life_months (+2 buffer for a rounding-residue
        # final period) -- the same natural stopping point run_depreciation
        # itself reaches via `remaining <= 0`, just walked forward here
        # instead of triggered by a batch run.
        for _ in range(asset.useful_life_months + 2):
            if accumulated >= depreciable_base:
                break
            remaining = depreciable_base - accumulated
            posted_amount = posted_by_period.get(period)
            amount = posted_amount if posted_amount is not None else min(monthly_amount, remaining)
            accumulated += amount
            lines.append(
                {
                    "period_month": period,
                    "depreciation": amount,
                    "accumulated_depreciation": accumulated,
                    "net_book_value": asset.cost - accumulated,
                    "posted": posted_amount is not None,
                }
            )
            period = date(period.year + 1, 1, 1) if period.month == 12 else date(period.year, period.month + 1, 1)

        return {
            "asset_id": asset.id,
            "asset_code": asset.asset_code,
            "asset_name": asset.name,
            "cost": asset.cost,
            "salvage_value": asset.salvage_value,
            "useful_life_months": asset.useful_life_months,
            "monthly_depreciation": monthly_amount,
            "lines": lines,
        }

    async def list_assets(
        self, company_id: UUID, *, category_id: UUID | None = None, status: str | None = None
    ) -> list[dict]:
        assets = await self.asset_repo.list_by_company(company_id, category_id=category_id, status=status)
        return [await self._to_dict(asset) for asset in assets]

    async def list_depreciation_entries(self, company_id: UUID, asset_id: UUID) -> list[FixedAssetDepreciationEntry]:
        asset = await self.asset_repo.get_by_id(asset_id)
        if asset is None or asset.company_id != company_id:
            raise ValueError("Fixed asset not found")
        return await self.depreciation_repo.list_for_asset(asset_id)

    async def get_asset_card(
        self, *, company_id: UUID, asset_id: UUID, date_from: date, date_to: date
    ) -> dict:
        """بطاقة الأصل — same opening/running/closing shape
        payments.SubledgerService._build_subledger uses for a customer/
        vendor statement, but tracking three parallel running values (cost,
        accumulated depreciation, net book value) instead of one balance,
        since a fixed asset's movements come from two different sources —
        the asset row itself (acquisition, disposal) and its depreciation
        entries — merged into one chronological event list exactly like
        SubledgerService merges invoices/allocations/unallocated payments."""
        asset = await self.asset_repo.get_by_id(asset_id)
        if asset is None or asset.company_id != company_id:
            raise ValueError("Fixed asset not found")
        entries = await self.depreciation_repo.list_for_asset(asset_id)

        events = [
            {
                "date": asset.acquisition_date,
                "sort_date": asset.acquisition_date,
                "movement_type": "acquisition",
                "reference": asset.asset_code,
                "journal_entry_id": asset.acquisition_journal_entry_id,
                "cost_movement": asset.cost,
                "accumulated_depreciation_movement": Decimal("0"),
            }
        ]
        for entry in entries:
            events.append(
                {
                    "date": entry.period_month,
                    # A depreciation entry's `date` is period_month (the
                    # 1st — matches the actual JE's entry_date exactly, see
                    # run_depreciation), but it represents the WHOLE month,
                    # not literally day 1. Sorting/range-testing by that raw
                    # date would place an asset's own first depreciation
                    # entry BEFORE its mid-month acquisition whenever both
                    # fall in the same calendar month (e.g. acquired
                    # 2026-08-09, first depreciation period_month
                    # 2026-08-01) — found live: the card showed "إهلاك"
                    # before "اقتناء" with a nonsensical negative running
                    # net book value in between. Sorting by the period's
                    # month-END instead (while still DISPLAYING period_month
                    # as `date`, unchanged) places it correctly after
                    # everything else that happened during that month.
                    "sort_date": _month_end(entry.period_month),
                    "movement_type": "depreciation",
                    "reference": asset.asset_code,
                    "journal_entry_id": entry.journal_entry_id,
                    "cost_movement": Decimal("0"),
                    "accumulated_depreciation_movement": entry.amount,
                }
            )
        if asset.disposed_at is not None:
            accumulated_at_disposal = sum((e.amount for e in entries), Decimal("0"))
            events.append(
                {
                    "date": asset.disposed_at,
                    "sort_date": asset.disposed_at,
                    "movement_type": "disposal",
                    "reference": asset.asset_code,
                    "journal_entry_id": asset.disposal_journal_entry_id,
                    "cost_movement": -asset.cost,
                    "accumulated_depreciation_movement": -accumulated_at_disposal,
                }
            )
        # Sort by sort_date (month-end for depreciation) so same-month
        # ordering is correct, but INCLUSION in the opening balance / the
        # printed window still goes by `date` (== the actual JE's
        # entry_date) — that's the real-world "was this already posted by
        # this point" test, matching how the GL itself would filter it.
        # Using sort_date for inclusion too would hide an already-posted
        # depreciation entry from a window ending mid-month (e.g.
        # date_to=2026-08-10 excluding a period_month=2026-08-01 entry
        # whose sort_date is 2026-08-31) even though it's already in the
        # ledger — caught live right after fixing the ordering above.
        events.sort(key=lambda m: m["sort_date"])

        opening_cost = Decimal("0")
        opening_accumulated = Decimal("0")
        for event in events:
            if event["date"] < date_from:
                opening_cost += event["cost_movement"]
                opening_accumulated += event["accumulated_depreciation_movement"]

        running_cost = opening_cost
        running_accumulated = opening_accumulated
        lines = []
        for event in events:
            if date_from <= event["date"] <= date_to:
                running_cost += event["cost_movement"]
                running_accumulated += event["accumulated_depreciation_movement"]
                lines.append(
                    {
                        **event,
                        "running_cost": running_cost,
                        "running_accumulated_depreciation": running_accumulated,
                        "running_net_book_value": running_cost - running_accumulated,
                    }
                )

        return {
            "asset_id": asset.id,
            "asset_code": asset.asset_code,
            "asset_name": asset.name,
            "opening_cost": opening_cost,
            "opening_accumulated_depreciation": opening_accumulated,
            "opening_net_book_value": opening_cost - opening_accumulated,
            "lines": lines,
            "closing_cost": running_cost,
            "closing_accumulated_depreciation": running_accumulated,
            "closing_net_book_value": running_cost - running_accumulated,
        }

    async def get_reconciliation(self, *, company_id: UUID, as_of_date: date) -> dict:
        """Ties the asset register to the GL it's supposed to be a subledger
        of — the same discipline this session already applied to AR/AP
        (payments.SubledgerService vs Trial Balance): a register total that
        can silently drift from the GL is worse than no register at all.
        Groups active assets by the actual GL account each points to
        (rather than assuming a single hardcoded Fixed Assets/Accumulated
        Depreciation account pair) and compares the register's own sum
        against that account's real posted balance via the same
        `account_balance_by_id` General Ledger/Balance Sheet already use.
        """
        # NOT active_only=True: that filters by the asset's CURRENT
        # disposed_at state, but this is an as-of-a-date reconciliation —
        # an asset disposed AFTER as_of_date was still on the books as of
        # that date and its disposal JE (dated in the future relative to
        # as_of_date) hasn't hit the GL yet either. Excluding it here while
        # the GL still carries its acquisition would make this reconciler
        # report a mismatch against its own inconsistency, not a real one
        # — found live: an asset acquired 2026-08-09 and disposed
        # 2026-09-01 was excluded from an "as of 2026-08-10" register total
        # while the GL (correctly, per its own entry_date filtering) still
        # included its acquisition, reporting a false 12,000 SAR gap.
        all_assets = await self.asset_repo.list_by_company(company_id)
        assets = [a for a in all_assets if a.disposed_at is None or a.disposed_at > as_of_date]
        # account_balance_by_id sums entries with entry_date < as_of_date
        # (opening-balance semantics — see repositories.py) so passing the
        # NEXT day makes it inclusive of as_of_date itself.
        balance_cutoff = as_of_date + timedelta(days=1)

        register_by_asset_account: dict[UUID, Decimal] = {}
        register_by_accum_account: dict[UUID, Decimal] = {}
        # Depreciation Expense (Owner brief §15 -- explicitly required, not
        # covered before this phase): the SAME `accumulated` figure booked
        # here again, since every depreciation JE debits Depreciation
        # Expense for the exact amount it credits Accumulated Depreciation
        # for -- reusing it isn't a shortcut, it's the correct cumulative
        # expense-to-date by construction. A standalone manual JE hitting
        # this account independently of `run_depreciation` is exactly the
        # kind of drift this third group exists to catch.
        register_by_expense_account: dict[UUID, Decimal] = {}
        for asset in assets:
            if asset.acquisition_date > as_of_date:
                continue
            entries = await self.depreciation_repo.list_for_asset(asset.id)
            accumulated = sum(
                (e.amount for e in entries if e.period_month <= as_of_date), Decimal("0")
            )
            register_by_asset_account[asset.fixed_asset_account_id] = (
                register_by_asset_account.get(asset.fixed_asset_account_id, Decimal("0")) + asset.cost
            )
            register_by_accum_account[asset.accumulated_depreciation_account_id] = (
                register_by_accum_account.get(asset.accumulated_depreciation_account_id, Decimal("0"))
                + accumulated
            )
            register_by_expense_account[asset.depreciation_expense_account_id] = (
                register_by_expense_account.get(asset.depreciation_expense_account_id, Decimal("0"))
                + accumulated
            )

        entry_repo = self.journal_entry_service.entry_repo
        rows = []
        # Two separate groups, not merged by account_id: a Fixed Asset
        # account is debit-normal (account_balance_by_id's debit-minus-
        # credit comes back positive, matching the register's positive
        # cost total directly), but Accumulated Depreciation is a
        # credit-normal contra-asset -- every depreciation/disposal entry
        # credits it, so its raw GL balance comes back NEGATIVE. Comparing
        # that directly against the register's positive accumulated total
        # would never match; the sign has to be flipped for this group
        # specifically (found while writing the reconciliation test: two
        # assets correctly summing to 200 in the register still failed
        # the check against a GL balance of -200).
        for account_id, register_total in register_by_asset_account.items():
            account = await self.account_repo.get_by_id(account_id)
            gl_balance = await entry_repo.account_balance_by_id(company_id, account_id, balance_cutoff)
            rows.append(
                {
                    "account_id": account_id,
                    "account_code": account.code if account else "?",
                    "account_name": account.name if account else "?",
                    "register_total": register_total,
                    "gl_balance": gl_balance,
                    "difference": register_total - gl_balance,
                    "matches": register_total == gl_balance,
                }
            )
        for account_id, register_total in register_by_accum_account.items():
            account = await self.account_repo.get_by_id(account_id)
            raw_gl_balance = await entry_repo.account_balance_by_id(company_id, account_id, balance_cutoff)
            gl_balance = -raw_gl_balance
            rows.append(
                {
                    "account_id": account_id,
                    "account_code": account.code if account else "?",
                    "account_name": account.name if account else "?",
                    "register_total": register_total,
                    "gl_balance": gl_balance,
                    "difference": register_total - gl_balance,
                    "matches": register_total == gl_balance,
                }
            )
        # Depreciation Expense is debit-normal, same polarity as the Asset
        # Cost group -- no sign flip needed, unlike Accumulated Depreciation.
        for account_id, register_total in register_by_expense_account.items():
            account = await self.account_repo.get_by_id(account_id)
            gl_balance = await entry_repo.account_balance_by_id(company_id, account_id, balance_cutoff)
            rows.append(
                {
                    "account_id": account_id,
                    "account_code": account.code if account else "?",
                    "account_name": account.name if account else "?",
                    "register_total": register_total,
                    "gl_balance": gl_balance,
                    "difference": register_total - gl_balance,
                    "matches": register_total == gl_balance,
                }
            )
        rows.sort(key=lambda r: r["account_code"])

        total_register_cost = sum(register_by_asset_account.values(), Decimal("0"))
        total_register_accumulated = sum(register_by_accum_account.values(), Decimal("0"))
        total_register_expense = sum(register_by_expense_account.values(), Decimal("0"))
        return {
            "as_of_date": as_of_date,
            "accounts": rows,
            "total_register_cost": total_register_cost,
            "total_register_accumulated_depreciation": total_register_accumulated,
            "total_register_net_book_value": total_register_cost - total_register_accumulated,
            "total_register_depreciation_expense": total_register_expense,
            "fully_matched": all(r["matches"] for r in rows),
        }

    async def get_depreciation_schedule(
        self, *, company_id: UUID, date_from: date, date_to: date, category_id: UUID | None = None
    ) -> dict:
        """Company-wide standard report: every depreciation entry actually
        posted within the window, across all assets (or one category) —
        answers "what did we depreciate, and how much" the way the
        per-asset Asset Card answers it for a single asset."""
        asset_ids = None
        if category_id is not None:
            assets_in_category = await self.asset_repo.list_by_company(company_id, category_id=category_id)
            asset_ids = [a.id for a in assets_in_category]
            if not asset_ids:
                return {"date_from": date_from, "date_to": date_to, "lines": [], "total_amount": Decimal("0")}

        entries = await self.depreciation_repo.list_for_company_in_range(
            company_id, date_from, date_to, asset_ids=asset_ids
        )
        asset_cache: dict[UUID, FixedAsset] = {}
        lines = []
        for entry in entries:
            if entry.fixed_asset_id not in asset_cache:
                asset_cache[entry.fixed_asset_id] = await self.asset_repo.get_by_id(entry.fixed_asset_id)
            asset = asset_cache[entry.fixed_asset_id]
            lines.append(
                {
                    "period_month": entry.period_month,
                    "asset_id": entry.fixed_asset_id,
                    "asset_code": asset.asset_code if asset else "?",
                    "asset_name": asset.name if asset else "?",
                    "amount": entry.amount,
                }
            )
        return {
            "date_from": date_from,
            "date_to": date_to,
            "lines": lines,
            "total_amount": sum((line["amount"] for line in lines), Decimal("0")),
        }

    async def run_depreciation(
        self,
        *,
        company_id: UUID,
        branch_id: UUID,
        period_month: date,
        created_by: UUID,
        category_id: UUID | None = None,
    ) -> dict:
        period = _month_start(period_month)
        assets = await self.asset_repo.list_by_company(company_id, active_only=True, category_id=category_id)
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
            "category_id": asset.category_id,
            "fixed_asset_account_id": asset.fixed_asset_account_id,
            "accumulated_depreciation_account_id": asset.accumulated_depreciation_account_id,
            "depreciation_expense_account_id": asset.depreciation_expense_account_id,
            "acquisition_date": asset.acquisition_date,
            "cost": asset.cost,
            "salvage_value": asset.salvage_value,
            "useful_life_months": asset.useful_life_months,
            # Derived display-only annual rate -- useful_life_months stays
            # the sole source of truth (Owner decision, 2026-08-19): never
            # a stored, independently-editable field, so it can never
            # contradict useful_life_months by construction.
            "depreciation_rate_percent": (Decimal("1200") / asset.useful_life_months).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            ),
            "accumulated_depreciation": accumulated,
            "net_book_value": net_book_value,
            "fully_depreciated": accumulated >= depreciable_base,
            "status": "disposed" if asset.disposed_at is not None else asset.status,
            "disposed_at": asset.disposed_at,
            "disposal_proceeds": asset.disposal_proceeds,
        }


class FixedAssetCategoryService:
    """Mirrors ProductCategoryService exactly (identity/application/
    services.py) — same cycle/duplicate/dependency validation, swapping
    "assigned to a product" for "assigned to a fixed asset" as the
    delete-guard dependency check."""

    def __init__(self, category_repo: FixedAssetCategoryRepository, asset_repo: FixedAssetRepository):
        self.category_repo = category_repo
        self.asset_repo = asset_repo

    async def _validate_parent(
        self, *, company_id: UUID, parent_id: UUID | None, editing_id: UUID | None = None
    ) -> None:
        if parent_id is None:
            return
        if editing_id is not None and parent_id == editing_id:
            raise ValueError("A category cannot be its own parent")
        parent = await self.category_repo.get_by_id(company_id, parent_id)
        if parent is None:
            raise ValueError("Invalid parent category")
        if editing_id is None:
            return
        visited: set[UUID] = {editing_id}
        current = parent
        while current.parent_id is not None:
            if current.parent_id in visited:
                raise ValueError("Circular category hierarchy is not allowed")
            visited.add(current.id)
            current = await self.category_repo.get_by_id(company_id, current.parent_id)
            if current is None:
                break

    async def create_category(
        self,
        *,
        company_id: UUID,
        name: str,
        parent_id: UUID | None = None,
        default_useful_life_months: int | None = None,
        default_fixed_asset_account_id: UUID | None = None,
        default_accumulated_depreciation_account_id: UUID | None = None,
        default_depreciation_expense_account_id: UUID | None = None,
    ) -> FixedAssetCategory:
        name = name.strip()
        if not name:
            raise ValueError("Category name is required")
        if default_useful_life_months is not None and default_useful_life_months <= 0:
            raise ValueError("Default useful life must be at least 1 month")
        await self._validate_parent(company_id=company_id, parent_id=parent_id)
        duplicate = await self.category_repo.find_sibling_by_name(company_id, parent_id, name)
        if duplicate is not None:
            raise ValueError(f"A category named '{name}' already exists at this level")
        category = FixedAssetCategory(
            id=uuid.uuid4(),
            company_id=company_id,
            name=name,
            parent_id=parent_id,
            default_useful_life_months=default_useful_life_months,
            default_fixed_asset_account_id=default_fixed_asset_account_id,
            default_accumulated_depreciation_account_id=default_accumulated_depreciation_account_id,
            default_depreciation_expense_account_id=default_depreciation_expense_account_id,
        )
        return await self.category_repo.add(category)

    async def update_category(
        self,
        *,
        company_id: UUID,
        category_id: UUID,
        name: str,
        parent_id: UUID | None,
        default_useful_life_months: int | None = None,
        default_fixed_asset_account_id: UUID | None = None,
        default_accumulated_depreciation_account_id: UUID | None = None,
        default_depreciation_expense_account_id: UUID | None = None,
    ) -> FixedAssetCategory:
        category = await self.category_repo.get_by_id(company_id, category_id)
        if category is None:
            raise LookupError("Category not found")
        name = name.strip()
        if not name:
            raise ValueError("Category name is required")
        if default_useful_life_months is not None and default_useful_life_months <= 0:
            raise ValueError("Default useful life must be at least 1 month")
        await self._validate_parent(company_id=company_id, parent_id=parent_id, editing_id=category_id)
        duplicate = await self.category_repo.find_sibling_by_name(
            company_id, parent_id, name, exclude_id=category_id
        )
        if duplicate is not None:
            raise ValueError(f"A category named '{name}' already exists at this level")
        category.name = name
        category.parent_id = parent_id
        category.default_useful_life_months = default_useful_life_months
        category.default_fixed_asset_account_id = default_fixed_asset_account_id
        category.default_accumulated_depreciation_account_id = default_accumulated_depreciation_account_id
        category.default_depreciation_expense_account_id = default_depreciation_expense_account_id
        return category

    async def delete_category(self, *, company_id: UUID, category_id: UUID) -> None:
        category = await self.category_repo.get_by_id(company_id, category_id)
        if category is None:
            raise LookupError("Category not found")
        child_count = await self.category_repo.count_children(company_id, category_id)
        if child_count > 0:
            raise ValueError("Cannot delete a category that has child categories")
        asset_count = await self.asset_repo.count_by_category(company_id, category_id)
        if asset_count > 0:
            raise ValueError("Cannot delete a category that is assigned to one or more fixed assets")
        await self.category_repo.delete(category)
