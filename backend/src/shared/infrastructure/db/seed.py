"""Idempotent seed data (Phase 7 §8): default currencies, account types, and
the permission catalog. Safe to run repeatedly — every insert is guarded by
an existence check. Invoked once at API startup for the nucleus's first
milestones; a dedicated `python -m src.scripts.seed` entry point can replace
this once a release/deploy pipeline exists (Phase 14).
"""

import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.accounting.infrastructure.models import AccountType
from src.modules.identity.infrastructure.models import Currency, Permission
from src.shared.infrastructure.db.session import set_admin_sync

DEFAULT_CURRENCIES = [
    ("SAR", "ر.س", 2),
    ("USD", "$", 2),
    ("EUR", "€", 2),
]

ACCOUNT_TYPE_CODES = ["asset", "liability", "equity", "revenue", "expense"]

# code, scope — screen/action-level permissions. Field-level permissions
# (FR-CORE-016) and Record Rules (FR-CORE-017) are configured per-role at
# runtime, not seeded as a fixed catalog.
PERMISSION_CATALOG = [
    # M0 — Identity
    ("company.manage_branches", "action"),
    ("company.view", "screen"),
    # UI/UX Foundation milestone — Company Context: lets an existing tenant
    # add a second company (previously only possible via /bootstrap, which
    # always mints a brand-new tenant alongside it).
    ("company.create", "action"),
    # UI/UX Evolution milestone — Entity Media Foundation: the one general
    # "edit this company's own profile" permission; covers the logo today,
    # the natural home for any future company-profile field.
    ("company.manage", "action"),
    ("user.create", "action"),
    ("user.manage_roles", "action"),
    ("user.view", "screen"),
    ("audit_log.view", "screen"),
    # Settings Architecture Foundation milestone: controls the Security
    # settings section (view/create roles, edit a role's own permission
    # set). Deliberately one permission for the whole section, not split
    # view/manage — anyone who can see role membership can already infer
    # the access model, and a narrower split has no real use case yet.
    ("role.manage", "action"),
    ("partner.view", "screen"),
    ("partner.create", "action"),
    ("partner.update", "action"),
    ("product.view", "screen"),
    ("product.create", "action"),
    ("product.update", "action"),
    ("product_category.view", "screen"),
    ("product_category.manage", "action"),
    ("uom.view", "screen"),
    ("uom.manage", "action"),
    # M1 — Accounting
    ("accounting.chart_of_accounts.view", "screen"),
    ("accounting.chart_of_accounts.manage", "action"),
    ("accounting.journal_entry.view", "screen"),
    ("accounting.journal_entry.create", "action"),
    ("accounting.journal_entry.post", "action"),
    ("accounting.journal_entry.reverse", "action"),
    # Owner-reported gap: a draft entry stuck in a closed fiscal period had
    # no way out (can't post, no edit/cancel existed at all). A draft has
    # zero ledger impact, so cancelling one is independent of period status.
    ("accounting.journal_entry.cancel", "action"),
    ("accounting.reports.trial_balance.view", "screen"),
    ("accounting.fiscal_period.manage", "action"),
    ("accounting.tax_rate.view", "screen"),
    # Phase 17E — Accounting Standardization (Milestone 1a)
    ("accounting.reports.general_ledger.view", "screen"),
    ("accounting.reports.income_statement.view", "screen"),
    ("accounting.reports.balance_sheet.view", "screen"),
    # Milestone 1b — Subledgers + AR/AP Aging
    ("payment.subledger.view", "screen"),
    ("payment.aging.view", "screen"),
    # M2 — Sales + ZATCA
    ("sales.quotation.create", "action"),
    ("sales.quotation.update", "action"),
    ("sales.quotation.confirm", "action"),
    ("sales.order.view", "screen"),
    ("sales.order.update", "action"),
    ("sales.order.cancel", "action"),
    ("sales.invoice.create", "action"),
    ("sales.invoice.credit_note", "action"),
    ("sales.invoice.send_email", "action"),
    # M3 — Inventory
    ("inventory.warehouse.manage", "action"),
    ("inventory.warehouse.view", "screen"),
    ("inventory.stock.receive", "action"),
    ("inventory.stock.view", "screen"),
    ("inventory.transfer.create", "action"),
    ("inventory.cycle_count.manage", "action"),
    # M4 — Purchasing
    ("purchasing.order.create", "action"),
    ("purchasing.order.update", "action"),
    ("purchasing.order.confirm", "action"),
    ("purchasing.order.approve", "action"),
    ("purchasing.order.view", "screen"),
    ("purchasing.order.short_close", "action"),
    ("purchasing.order.reopen", "action"),
    ("purchasing.goods_receipt.create", "action"),
    ("purchasing.vendor_bill.create", "action"),
    ("purchasing.vendor_bill.update", "action"),
    ("purchasing.vendor_bill.view", "screen"),
    ("purchasing.vendor_bill.approve", "action"),
    ("purchasing.vendor_bill.debit_note", "action"),
    # M5 — Reporting
    ("reporting.dashboard.view", "screen"),
    ("reporting.export", "action"),
    ("reporting.sales.view", "screen"),
    ("reporting.purchasing.view", "screen"),
    # Phase 17D — Payments
    ("payment.view", "screen"),
    ("payment.create", "action"),
    # Professional Workspace Layer — Attachments: one pair of permissions
    # for the whole cross-cutting concern (view/download vs upload/delete),
    # not one per document type — matches the same "single permission for
    # a cross-module concern" precedent `audit_log.view` already set.
    ("attachment.view", "screen"),
    ("attachment.manage", "action"),
    ("search.use", "screen"),
    ("reporting.vat.view", "screen"),
    ("reporting.inventory_valuation.view", "screen"),
    # P0-5 (3-Day Brief) — Fixed Assets
    ("fixed_assets.view", "screen"),
    ("fixed_assets.create", "action"),
    ("fixed_assets.depreciation.run", "action"),
    ("fixed_assets.dispose", "action"),
    ("fixed_assets.category.manage", "action"),
]


async def seed_core_data(session: AsyncSession) -> None:
    for code, symbol, decimals in DEFAULT_CURRENCIES:
        existing = await session.execute(select(Currency).where(Currency.code == code))
        if existing.scalar_one_or_none() is None:
            session.add(
                Currency(id=uuid.uuid4(), code=code, symbol=symbol, decimal_places=decimals)
            )

    for code in ACCOUNT_TYPE_CODES:
        existing = await session.execute(select(AccountType).where(AccountType.code == code))
        if existing.scalar_one_or_none() is None:
            session.add(AccountType(id=uuid.uuid4(), code=code))

    for code, scope in PERMISSION_CATALOG:
        existing = await session.execute(select(Permission).where(Permission.code == code))
        if existing.scalar_one_or_none() is None:
            session.add(Permission(id=uuid.uuid4(), code=code, scope=scope))

    # Flush so every permission row exists before the Admin-role sync below.
    await session.flush()

    # Sync: any Admin role should always hold every permission in the catalog
    # — handles new permissions added after the company was bootstrapped.
    #
    # This must NOT select from `role` directly: `role` has FORCE ROW LEVEL
    # SECURITY keyed on company context, and this runs at API startup with no
    # company context set, so a `role`-table query silently sees zero rows —
    # not an error, just a no-op — for every DB user, `erp_app` included
    # (confirmed live: this exact bug left `role.manage` missing from an
    # existing company's Admin role for as long as the previous version of
    # this sync existed; see migration `d3e4f5a6b7c8` for the one-time
    # repair). Identifying Admin roles *indirectly* — any role already
    # holding a permission only an Admin role would have — avoids needing
    # `role` at all, working unconditionally regardless of DB user.
    #
    # `role_permission` ALSO carries FORCE ROW LEVEL SECURITY (added later,
    # P0-6, after the paragraph above was first written — a second
    # occurrence of the exact same bug, found live and one-time-repaired by
    # migration `a5b6c7d8e9f0`). `set_admin_sync()` below is the permanent
    # fix: the same narrow, additive escape-hatch policy pattern the login
    # flow already uses for `user_company_access` (`set_login_lookup`,
    # migrations `f7004fe055a4`/`0fc571b91522`), added here for
    # `role_permission` by migration `b6c7d8e9f0a1`.
    await set_admin_sync(session)
    # Performance note (found live: this query saturated a dev DB that had
    # accumulated ~9,000 roles from repeated test bootstrapping — every
    # role x every catalog permission with a correlated NOT EXISTS is
    # O(roles x permissions), and this runs on every API startup). Narrow
    # to *incomplete* Admin roles first with a cheap GROUP BY/HAVING (index-
    # only on the role_permission PK) — in steady state that's ~0 rows, so
    # the expensive CROSS JOIN below only ever runs against roles that
    # actually need it (freshly created, or a permission was just added to
    # the catalog).
    # ON CONFLICT DO NOTHING, not a NOT EXISTS predicate: this can run
    # concurrently with itself — multiple API replicas/workers starting up
    # around the same time (or, found live, this same test's direct call
    # racing the actual dev server's own reload-triggered run against the
    # same DB) both see the same gap and both try to fill it. A
    # check-then-insert NOT EXISTS has a real TOCTOU race there
    # (confirmed live: `role_permission_pkey` UniqueViolationError); the
    # role_permission PK IS exactly (role_id, permission_id), so ON
    # CONFLICT makes the fill atomic and idempotent instead.
    catalog_size = len(PERMISSION_CATALOG)
    await session.execute(
        text("""
        INSERT INTO role_permission (role_id, permission_id)
        SELECT incomplete.role_id, p_missing.id
        FROM (
            SELECT admin_rp.role_id
            FROM role_permission admin_rp
            JOIN permission p_marker ON p_marker.id = admin_rp.permission_id
                                      AND p_marker.code = 'reporting.dashboard.view'
            JOIN role_permission rp_count ON rp_count.role_id = admin_rp.role_id
            GROUP BY admin_rp.role_id
            HAVING COUNT(*) < :catalog_size
        ) incomplete
        CROSS JOIN permission p_missing
        ON CONFLICT (role_id, permission_id) DO NOTHING
    """),
        {"catalog_size": catalog_size},
    )

    await session.commit()
