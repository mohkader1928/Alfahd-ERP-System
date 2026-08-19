"""P0-5 (3-Day Brief): Fixed Assets — register, straight-line depreciation,
and disposal, all integrated with the GL via JournalEntryService."""

from decimal import Decimal

from tests.conftest import unique_email, unique_vat


async def _bootstrap_and_login(client, label="FixedAssets"):
    payload = {
        "tenant_legal_name": f"{label} Holding",
        "company_legal_name": f"{label} Trading Co.",
        "company_legal_name_ar": f"{label} Trading Arabic",
        "vat_number": unique_vat(),
        "base_currency_code": "SAR",
        "valuation_method": "average",
        "admin_email": unique_email(),
        "admin_full_name": f"{label} Admin",
        "admin_password": "Str0ng!Passw0rd",
    }
    boot_resp = await client.post("/api/v1/identity/bootstrap", json=payload)
    assert boot_resp.status_code == 201
    company_id = boot_resp.json()["company_id"]
    branch_id = boot_resp.json()["branch_id"]

    login_resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": payload["admin_email"], "password": payload["admin_password"]},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Company-Id": company_id, "X-Branch-Id": branch_id}
    return company_id, headers


async def _get_account(client, headers, code: str) -> dict:
    resp = await client.get("/api/v1/accounting/chart-of-accounts", headers=headers)
    return next(a for a in resp.json() if a["code"] == code)


async def _standard_asset_payload(client, headers, **overrides) -> dict:
    fixed = await _get_account(client, headers, "1410")
    accum = await _get_account(client, headers, "1490")
    expense = await _get_account(client, headers, "5950")
    cash = await _get_account(client, headers, "1100")
    payload = {
        "name": "Delivery Truck",
        "name_ar": "شاحنة توصيل",
        "fixed_asset_account_id": fixed["id"],
        "accumulated_depreciation_account_id": accum["id"],
        "depreciation_expense_account_id": expense["id"],
        "funding_account_id": cash["id"],
        "acquisition_date": "2026-01-01",
        "cost": "1200.00",
        "salvage_value": "0",
        "useful_life_months": 12,
    }
    payload.update(overrides)
    return payload


async def test_create_fixed_asset_posts_acquisition_entry(client):
    _, headers = await _bootstrap_and_login(client, "FA_Create")
    payload = await _standard_asset_payload(client, headers)

    resp = await client.post("/api/v1/fixed-assets", headers=headers, json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["asset_code"] == "FA-000001"
    assert body["status"] == "active"
    assert body["accumulated_depreciation"] == "0.0000"
    assert body["net_book_value"] == "1200.0000"

    tb = await client.get(
        "/api/v1/accounting/reports/trial-balance",
        headers=headers,
        params={"date_from": "2026-01-01", "date_to": "2026-01-31"},
    )
    rows = {r["account_code"]: r for r in tb.json()}
    assert rows["1410"]["period_debit"] == "1200.0000"
    assert rows["1100"]["period_credit"] == "1200.0000"


async def test_create_fixed_asset_rejects_group_account(client):
    _, headers = await _bootstrap_and_login(client, "FA_Group")
    group_account = await _get_account(client, headers, "1400")  # is_group=true
    payload = await _standard_asset_payload(client, headers, fixed_asset_account_id=group_account["id"])

    resp = await client.post("/api/v1/fixed-assets", headers=headers, json=payload)
    assert resp.status_code == 422
    assert "group account" in resp.json()["detail"]


async def test_create_fixed_asset_rejects_salvage_above_cost(client):
    _, headers = await _bootstrap_and_login(client, "FA_Salvage")
    payload = await _standard_asset_payload(client, headers, cost="500.00", salvage_value="600.00")

    resp = await client.post("/api/v1/fixed-assets", headers=headers, json=payload)
    assert resp.status_code == 422


async def test_run_depreciation_straight_line_and_idempotent_per_period(client):
    _, headers = await _bootstrap_and_login(client, "FA_Depr")
    payload = await _standard_asset_payload(client, headers, cost="1200.00", salvage_value="0", useful_life_months=12)
    create_resp = await client.post("/api/v1/fixed-assets", headers=headers, json=payload)
    asset_id = create_resp.json()["id"]

    run1 = await client.post(
        "/api/v1/fixed-assets:run-depreciation", headers=headers, json={"period_month": "2026-01-15"}
    )
    assert run1.status_code == 200, run1.text
    body1 = run1.json()
    assert body1["assets_posted"] == 1
    assert body1["total_amount"] == "100.0000"

    # Same period again -> skipped, not double-posted (UNIQUE(fixed_asset_id, period_month)).
    run_again = await client.post(
        "/api/v1/fixed-assets:run-depreciation", headers=headers, json={"period_month": "2026-01-20"}
    )
    assert run_again.json()["assets_posted"] == 0
    assert run_again.json()["assets_skipped"] == 1

    # A different period -> posts again, accumulating.
    run2 = await client.post(
        "/api/v1/fixed-assets:run-depreciation", headers=headers, json={"period_month": "2026-02-01"}
    )
    assert run2.json()["assets_posted"] == 1

    asset = (await client.get(f"/api/v1/fixed-assets/{asset_id}", headers=headers)).json()
    assert asset["accumulated_depreciation"] == "200.0000"
    assert asset["net_book_value"] == "1000.0000"

    entries = (await client.get(f"/api/v1/fixed-assets/{asset_id}/depreciation-entries", headers=headers)).json()
    assert len(entries) == 2


async def test_run_depreciation_caps_at_depreciable_base(client):
    _, headers = await _bootstrap_and_login(client, "FA_Cap")
    payload = await _standard_asset_payload(client, headers, cost="1000.00", salvage_value="900.00", useful_life_months=1)
    create_resp = await client.post("/api/v1/fixed-assets", headers=headers, json=payload)
    asset_id = create_resp.json()["id"]

    run1 = await client.post(
        "/api/v1/fixed-assets:run-depreciation", headers=headers, json={"period_month": "2026-01-01"}
    )
    assert run1.json()["total_amount"] == "100.0000"  # full depreciable base in one month

    run2 = await client.post(
        "/api/v1/fixed-assets:run-depreciation", headers=headers, json={"period_month": "2026-02-01"}
    )
    assert run2.json()["assets_posted"] == 0
    assert run2.json()["skipped"][0]["reason"] == "fully_depreciated"

    asset = (await client.get(f"/api/v1/fixed-assets/{asset_id}", headers=headers)).json()
    assert asset["fully_depreciated"] is True
    assert asset["net_book_value"] == "900.0000"


async def test_dispose_asset_posts_gain_and_blocks_further_action(client):
    _, headers = await _bootstrap_and_login(client, "FA_Dispose")
    payload = await _standard_asset_payload(client, headers, cost="1200.00", salvage_value="0", useful_life_months=12)
    create_resp = await client.post("/api/v1/fixed-assets", headers=headers, json=payload)
    asset_id = create_resp.json()["id"]

    await client.post("/api/v1/fixed-assets:run-depreciation", headers=headers, json={"period_month": "2026-01-01"})
    # accumulated = 100, net book value = 1100

    cash = await _get_account(client, headers, "1100")
    gain_account = await _get_account(client, headers, "4900")
    dispose = await client.post(
        f"/api/v1/fixed-assets/{asset_id}:dispose",
        headers=headers,
        json={
            "disposal_date": "2026-03-01",
            "proceeds": "1300.00",
            "proceeds_account_id": cash["id"],
            "gain_loss_account_id": gain_account["id"],
        },
    )
    assert dispose.status_code == 200, dispose.text
    body = dispose.json()
    assert body["status"] == "disposed"
    assert body["disposal_proceeds"] == "1300.0000"  # NUMERIC(18,4), same convention as every other decimal in this file

    tb = await client.get(
        "/api/v1/accounting/reports/trial-balance",
        headers=headers,
        params={"date_from": "2026-03-01", "date_to": "2026-03-31"},
    )
    rows = {r["account_code"]: r for r in tb.json()}
    assert rows["4900"]["period_credit"] == "200.0000"  # gain = 1300 proceeds - 1100 NBV

    # Depreciation can no longer be posted for a disposed asset.
    redepr = await client.post(
        "/api/v1/fixed-assets:run-depreciation", headers=headers, json={"period_month": "2026-04-01"}
    )
    assert redepr.json()["assets_posted"] == 0  # active_only=True excludes it

    # A second disposal attempt is rejected.
    redispose = await client.post(
        f"/api/v1/fixed-assets/{asset_id}:dispose",
        headers=headers,
        json={"disposal_date": "2026-04-01", "proceeds": "0"},
    )
    assert redispose.status_code == 422
    assert "already disposed" in redispose.json()["detail"]


async def test_dispose_asset_below_book_value_posts_loss(client):
    _, headers = await _bootstrap_and_login(client, "FA_Loss")
    payload = await _standard_asset_payload(client, headers, cost="1200.00", salvage_value="0", useful_life_months=12)
    create_resp = await client.post("/api/v1/fixed-assets", headers=headers, json=payload)
    asset_id = create_resp.json()["id"]
    # No depreciation posted -> net book value = cost = 1200.

    cash = await _get_account(client, headers, "1100")
    loss_account = await _get_account(client, headers, "5900")
    dispose = await client.post(
        f"/api/v1/fixed-assets/{asset_id}:dispose",
        headers=headers,
        json={
            "disposal_date": "2026-02-01",
            "proceeds": "500.00",
            "proceeds_account_id": cash["id"],
            "gain_loss_account_id": loss_account["id"],
        },
    )
    assert dispose.status_code == 200, dispose.text

    tb = await client.get(
        "/api/v1/accounting/reports/trial-balance",
        headers=headers,
        params={"date_from": "2026-02-01", "date_to": "2026-02-28"},
    )
    rows = {r["account_code"]: r for r in tb.json()}
    assert rows["5900"]["period_debit"] == "700.0000"  # loss = 1200 NBV - 500 proceeds


async def test_run_depreciation_full_month_convention_for_mid_month_acquisition(client):
    """Found live (browser walkthrough): an asset acquired mid-month (e.g.
    2026-08-09) must still be eligible for that month's depreciation run
    (period_month=2026-08-01) under the standard full-month convention —
    comparing the raw acquisition_date against the period's month-start
    wrongly excluded every asset from its own acquisition month unless
    bought on day 1."""
    _, headers = await _bootstrap_and_login(client, "FA_MidMonth")
    payload = await _standard_asset_payload(
        client, headers, acquisition_date="2026-08-09", cost="1200.00", salvage_value="0", useful_life_months=12
    )
    create_resp = await client.post("/api/v1/fixed-assets", headers=headers, json=payload)
    assert create_resp.status_code == 201, create_resp.text
    asset_id = create_resp.json()["id"]

    run = await client.post(
        "/api/v1/fixed-assets:run-depreciation", headers=headers, json={"period_month": "2026-08-01"}
    )
    assert run.status_code == 200, run.text
    body = run.json()
    assert body["assets_posted"] == 1
    assert body["assets_skipped"] == 0
    assert body["total_amount"] == "100.0000"

    asset = (await client.get(f"/api/v1/fixed-assets/{asset_id}", headers=headers)).json()
    assert asset["accumulated_depreciation"] == "100.0000"

    # A period BEFORE acquisition is still correctly excluded (and reported
    # as skipped, not silently dropped).
    early = await client.post(
        "/api/v1/fixed-assets:run-depreciation", headers=headers, json={"period_month": "2026-07-01"}
    )
    assert early.json()["assets_posted"] == 0
    assert early.json()["skipped"][0]["reason"] == "not_yet_acquired"


async def test_asset_card_shows_running_cost_accumulated_and_nbv(client):
    """Owner-requested follow-up: بطاقة الأصل — a per-asset card mirroring
    Product Cardex/Customer Subledger's running-balance shape, but tracking
    three parallel values (cost, accumulated depreciation, net book value)
    since a fixed asset's movements come from two sources (the asset row
    itself, and its depreciation entries)."""
    _, headers = await _bootstrap_and_login(client, "FA_Card")
    payload = await _standard_asset_payload(
        client, headers, acquisition_date="2026-01-01", cost="1200.00", salvage_value="0", useful_life_months=12
    )
    create_resp = await client.post("/api/v1/fixed-assets", headers=headers, json=payload)
    asset_id = create_resp.json()["id"]

    await client.post("/api/v1/fixed-assets:run-depreciation", headers=headers, json={"period_month": "2026-01-01"})
    await client.post("/api/v1/fixed-assets:run-depreciation", headers=headers, json={"period_month": "2026-02-01"})

    card = await client.get(
        f"/api/v1/fixed-assets/{asset_id}/card",
        headers=headers,
        params={"date_from": "2026-01-01", "date_to": "2026-02-28"},
    )
    assert card.status_code == 200, card.text
    body = card.json()
    assert body["opening_cost"] == "0"
    assert body["opening_accumulated_depreciation"] == "0"
    assert [line["movement_type"] for line in body["lines"]] == ["acquisition", "depreciation", "depreciation"]

    acquisition_line, jan_line, feb_line = body["lines"]
    assert acquisition_line["running_cost"] == "1200.0000"
    assert acquisition_line["running_net_book_value"] == "1200.0000"
    assert jan_line["running_accumulated_depreciation"] == "100.0000"
    assert jan_line["running_net_book_value"] == "1100.0000"
    assert feb_line["running_accumulated_depreciation"] == "200.0000"
    assert feb_line["running_net_book_value"] == "1000.0000"

    assert body["closing_cost"] == "1200.0000"
    assert body["closing_accumulated_depreciation"] == "200.0000"
    assert body["closing_net_book_value"] == "1000.0000"


async def test_asset_card_orders_acquisition_before_same_month_depreciation(client):
    """Found live: an asset acquired mid-month (2026-08-09) whose first
    depreciation entry is period_month=2026-08-01 (the JE's own entry_date,
    matching the full-month convention) must still show "acquisition"
    before "depreciation" on the card — sorting by the raw period_month
    would put depreciation first and produce a nonsensical negative
    running net book value in between."""
    _, headers = await _bootstrap_and_login(client, "FA_CardOrder")
    payload = await _standard_asset_payload(
        client, headers, acquisition_date="2026-08-09", cost="1200.00", salvage_value="0", useful_life_months=12
    )
    create_resp = await client.post("/api/v1/fixed-assets", headers=headers, json=payload)
    asset_id = create_resp.json()["id"]
    await client.post("/api/v1/fixed-assets:run-depreciation", headers=headers, json={"period_month": "2026-08-01"})

    card = await client.get(
        f"/api/v1/fixed-assets/{asset_id}/card",
        headers=headers,
        params={"date_from": "2026-08-01", "date_to": "2026-08-31"},
    )
    assert card.status_code == 200, card.text
    body = card.json()
    assert [line["movement_type"] for line in body["lines"]] == ["acquisition", "depreciation"]

    acquisition_line, depreciation_line = body["lines"]
    # No intermediate negative net book value from an out-of-order sort.
    assert acquisition_line["running_net_book_value"] == "1200.0000"
    assert depreciation_line["running_net_book_value"] == "1100.0000"

    # A window ending MID-month (before the period's own month-end) must
    # still include an already-posted same-month depreciation entry — the
    # entry's real entry_date is period_month (the 1st), already in the
    # past relative to date_to, even though sort_date (used only to fix
    # the ordering above) is the month-end. Using sort_date for inclusion
    # too would wrongly hide an already-posted entry — caught live right
    # after the ordering fix itself.
    mid_month_card = await client.get(
        f"/api/v1/fixed-assets/{asset_id}/card",
        headers=headers,
        params={"date_from": "2026-08-01", "date_to": "2026-08-10"},
    )
    mid_month_body = mid_month_card.json()
    assert [line["movement_type"] for line in mid_month_body["lines"]] == ["acquisition", "depreciation"]
    assert mid_month_body["closing_accumulated_depreciation"] == "100.0000"


async def test_asset_card_disposal_movement_zeroes_out_running_totals(client):
    _, headers = await _bootstrap_and_login(client, "FA_CardDisposal")
    payload = await _standard_asset_payload(
        client, headers, acquisition_date="2026-01-01", cost="1200.00", salvage_value="0", useful_life_months=12
    )
    create_resp = await client.post("/api/v1/fixed-assets", headers=headers, json=payload)
    asset_id = create_resp.json()["id"]
    await client.post("/api/v1/fixed-assets:run-depreciation", headers=headers, json={"period_month": "2026-01-01"})

    cash = await _get_account(client, headers, "1100")
    gain_account = await _get_account(client, headers, "4900")
    await client.post(
        f"/api/v1/fixed-assets/{asset_id}:dispose",
        headers=headers,
        json={
            "disposal_date": "2026-03-01",
            "proceeds": "1300.00",
            "proceeds_account_id": cash["id"],
            "gain_loss_account_id": gain_account["id"],
        },
    )

    card = await client.get(
        f"/api/v1/fixed-assets/{asset_id}/card",
        headers=headers,
        params={"date_from": "2026-01-01", "date_to": "2026-03-31"},
    )
    body = card.json()
    disposal_line = body["lines"][-1]
    assert disposal_line["movement_type"] == "disposal"
    assert disposal_line["running_cost"] == "0.0000"
    assert disposal_line["running_accumulated_depreciation"] == "0.0000"
    assert disposal_line["running_net_book_value"] == "0.0000"
    assert body["closing_net_book_value"] == "0.0000"


async def test_reconciliation_matches_gl_for_active_assets(client):
    """The reconciliation is what actually enforces the Owner's standing
    requirement: the register's totals must tie to the same GL accounts
    Trial Balance reads, not just look plausible on their own."""
    _, headers = await _bootstrap_and_login(client, "FA_Reconcile")
    payload1 = await _standard_asset_payload(
        client, headers, acquisition_date="2026-01-01", cost="1200.00", salvage_value="0", useful_life_months=12
    )
    asset1 = (await client.post("/api/v1/fixed-assets", headers=headers, json=payload1)).json()
    payload2 = await _standard_asset_payload(
        client, headers, acquisition_date="2026-01-01", cost="2400.00", salvage_value="0", useful_life_months=24
    )
    await client.post("/api/v1/fixed-assets", headers=headers, json=payload2)
    await client.post("/api/v1/fixed-assets:run-depreciation", headers=headers, json={"period_month": "2026-01-01"})

    recon = await client.get(
        "/api/v1/fixed-assets/reconciliation", headers=headers, params={"as_of_date": "2026-06-01"}
    )
    assert recon.status_code == 200, recon.text
    body = recon.json()
    assert body["fully_matched"] is True
    assert body["total_register_cost"] == "3600.0000"
    # asset1: 1200/12 = 100; asset2: 2400/24 = 100 -> 200 total accumulated depreciation
    assert body["total_register_accumulated_depreciation"] == "200.0000"
    assert body["total_register_net_book_value"] == "3400.0000"
    for row in body["accounts"]:
        assert row["matches"] is True
        assert row["difference"] == "0.0000"

    # Cross-check against Trial Balance directly for the fixed asset account.
    tb = await client.get(
        "/api/v1/accounting/reports/trial-balance",
        headers=headers,
        params={"date_from": "2026-01-01", "date_to": "2026-06-01"},
    )
    tb_rows = {r["account_code"]: r for r in tb.json()}
    account_1410 = await _get_account(client, headers, "1410")
    assert tb_rows[account_1410["code"]]["closing_balance"] == "3600.0000"
    assert asset1["asset_code"] == "FA-000001"


async def test_reconciliation_excludes_disposed_assets(client):
    _, headers = await _bootstrap_and_login(client, "FA_ReconcileDisposed")
    payload = await _standard_asset_payload(
        client, headers, acquisition_date="2026-01-01", cost="1200.00", salvage_value="0", useful_life_months=12
    )
    asset = (await client.post("/api/v1/fixed-assets", headers=headers, json=payload)).json()
    cash = await _get_account(client, headers, "1100")
    gain_account = await _get_account(client, headers, "4900")
    await client.post(
        f"/api/v1/fixed-assets/{asset['id']}:dispose",
        headers=headers,
        json={
            "disposal_date": "2026-02-01",
            "proceeds": "1200.00",
            "proceeds_account_id": cash["id"],
            "gain_loss_account_id": gain_account["id"],
        },
    )

    recon = await client.get(
        "/api/v1/fixed-assets/reconciliation", headers=headers, params={"as_of_date": "2026-06-01"}
    )
    body = recon.json()
    assert body["accounts"] == []
    assert body["total_register_cost"] == "0"
    assert body["fully_matched"] is True


async def test_reconciliation_includes_asset_disposed_after_as_of_date(client):
    """Found live: an asset disposed on a date AFTER as_of_date is still
    "on the books" as of that date — its disposal JE hasn't hit the GL yet
    either (entry_date is in the future relative to as_of_date). Filtering
    the register by the asset's CURRENT disposed_at state rather than its
    state as of as_of_date excluded it from the register total while the
    GL (correctly) still carried its acquisition, reporting a false
    mismatch against the reconciler's own inconsistency."""
    _, headers = await _bootstrap_and_login(client, "FA_ReconcileFutureDispose")
    payload = await _standard_asset_payload(
        client, headers, acquisition_date="2026-01-01", cost="1200.00", salvage_value="0", useful_life_months=12
    )
    asset = (await client.post("/api/v1/fixed-assets", headers=headers, json=payload)).json()
    cash = await _get_account(client, headers, "1100")
    gain_account = await _get_account(client, headers, "4900")
    await client.post(
        f"/api/v1/fixed-assets/{asset['id']}:dispose",
        headers=headers,
        json={
            "disposal_date": "2026-06-01",
            "proceeds": "1200.00",
            "proceeds_account_id": cash["id"],
            "gain_loss_account_id": gain_account["id"],
        },
    )

    # as_of_date is BEFORE the disposal -> the asset was still active then.
    recon = await client.get(
        "/api/v1/fixed-assets/reconciliation", headers=headers, params={"as_of_date": "2026-03-01"}
    )
    assert recon.status_code == 200, recon.text
    body = recon.json()
    assert body["fully_matched"] is True
    assert body["total_register_cost"] == "1200.0000"
    for row in body["accounts"]:
        assert row["matches"] is True


async def test_fixed_assets_isolated_across_companies(client):
    _, headers_a = await _bootstrap_and_login(client, "FA_TenantA")
    _, headers_b = await _bootstrap_and_login(client, "FA_TenantB")

    payload = await _standard_asset_payload(client, headers_a)
    create_resp = await client.post("/api/v1/fixed-assets", headers=headers_a, json=payload)
    asset_id = create_resp.json()["id"]

    cross_get = await client.get(f"/api/v1/fixed-assets/{asset_id}", headers=headers_b)
    assert cross_get.status_code == 404

    list_b = await client.get("/api/v1/fixed-assets", headers=headers_b)
    assert list_b.json() == []


# ---------------------------------------------------------------------------
# Asset Master + Controlled Depreciation phase (2026-08-19): operational
# status, derived depreciation rate, category default policy, Depreciation
# Expense reconciliation, and the forward-looking projected schedule.
# ---------------------------------------------------------------------------


async def test_create_fixed_asset_with_status_and_derived_rate(client):
    _, headers = await _bootstrap_and_login(client, "FA_StatusCreate")
    payload = await _standard_asset_payload(client, headers, useful_life_months=60, status="idle")

    resp = await client.post("/api/v1/fixed-assets", headers=headers, json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "idle"
    # Derived, never stored independently: 12/60*100 = 20.00%.
    assert body["depreciation_rate_percent"] == "20.00"


async def test_create_fixed_asset_defaults_to_active_status(client):
    _, headers = await _bootstrap_and_login(client, "FA_StatusDefault")
    payload = await _standard_asset_payload(client, headers)
    resp = await client.post("/api/v1/fixed-assets", headers=headers, json=payload)
    assert resp.json()["status"] == "active"


async def test_create_fixed_asset_rejects_invalid_status(client):
    _, headers = await _bootstrap_and_login(client, "FA_StatusInvalid")
    payload = await _standard_asset_payload(client, headers, status="retired")
    resp = await client.post("/api/v1/fixed-assets", headers=headers, json=payload)
    assert resp.status_code == 422


async def test_update_asset_status_active_to_idle_and_back(client):
    _, headers = await _bootstrap_and_login(client, "FA_StatusUpdate")
    payload = await _standard_asset_payload(client, headers)
    asset_id = (await client.post("/api/v1/fixed-assets", headers=headers, json=payload)).json()["id"]

    idle = await client.patch(f"/api/v1/fixed-assets/{asset_id}/status", headers=headers, json={"status": "idle"})
    assert idle.status_code == 200, idle.text
    assert idle.json()["status"] == "idle"

    maintenance = await client.patch(
        f"/api/v1/fixed-assets/{asset_id}/status", headers=headers, json={"status": "under_maintenance"}
    )
    assert maintenance.json()["status"] == "under_maintenance"

    back = await client.patch(f"/api/v1/fixed-assets/{asset_id}/status", headers=headers, json={"status": "active"})
    assert back.json()["status"] == "active"


async def test_update_asset_status_rejects_invalid_value(client):
    _, headers = await _bootstrap_and_login(client, "FA_StatusInvalidUpdate")
    payload = await _standard_asset_payload(client, headers)
    asset_id = (await client.post("/api/v1/fixed-assets", headers=headers, json=payload)).json()["id"]

    resp = await client.patch(f"/api/v1/fixed-assets/{asset_id}/status", headers=headers, json={"status": "retired"})
    assert resp.status_code == 422


async def test_update_asset_status_blocked_for_disposed_asset(client):
    _, headers = await _bootstrap_and_login(client, "FA_StatusDisposed")
    payload = await _standard_asset_payload(client, headers, cost="1200.00", salvage_value="0")
    asset_id = (await client.post("/api/v1/fixed-assets", headers=headers, json=payload)).json()["id"]
    # proceeds == cost, no depreciation posted yet -> gain_loss == 0, so no
    # gain_loss account is required, keeping this test focused on the
    # status-update guard rather than disposal's own gain/loss accounting.
    cash = await _get_account(client, headers, "1100")
    dispose = await client.post(
        f"/api/v1/fixed-assets/{asset_id}:dispose",
        headers=headers,
        json={"disposal_date": "2026-02-01", "proceeds": "1200.00", "proceeds_account_id": cash["id"]},
    )
    assert dispose.status_code == 200, dispose.text

    resp = await client.patch(f"/api/v1/fixed-assets/{asset_id}/status", headers=headers, json={"status": "idle"})
    assert resp.status_code == 422
    assert "disposed" in resp.json()["detail"]


async def test_update_asset_status_requires_authentication(client):
    _, headers = await _bootstrap_and_login(client, "FA_StatusAuth")
    payload = await _standard_asset_payload(client, headers)
    asset_id = (await client.post("/api/v1/fixed-assets", headers=headers, json=payload)).json()["id"]

    resp = await client.patch(f"/api/v1/fixed-assets/{asset_id}/status", json={"status": "idle"})
    assert resp.status_code == 401


async def test_operational_status_does_not_stop_depreciation(client):
    """Owner's own explicit warning (§11): don't assume Inactive/Idle stops
    depreciation. `run_depreciation` keys solely on `disposed_at`, so an
    idle-but-not-disposed asset must still depreciate normally."""
    _, headers = await _bootstrap_and_login(client, "FA_IdleStillDepreciates")
    payload = await _standard_asset_payload(client, headers, cost="1200.00", salvage_value="0", useful_life_months=12)
    asset_id = (await client.post("/api/v1/fixed-assets", headers=headers, json=payload)).json()["id"]
    await client.patch(f"/api/v1/fixed-assets/{asset_id}/status", headers=headers, json={"status": "idle"})

    run = await client.post("/api/v1/fixed-assets:run-depreciation", headers=headers, json={"period_month": "2026-01-01"})
    assert run.json()["assets_posted"] == 1
    assert run.json()["total_amount"] == "100.0000"

    asset = (await client.get(f"/api/v1/fixed-assets/{asset_id}", headers=headers)).json()
    assert asset["status"] == "idle"
    assert asset["accumulated_depreciation"] == "100.0000"


async def test_list_assets_filters_by_operational_status(client):
    _, headers = await _bootstrap_and_login(client, "FA_StatusFilter")
    active_id = (await client.post("/api/v1/fixed-assets", headers=headers, json=await _standard_asset_payload(client, headers))).json()["id"]
    idle_id = (await client.post("/api/v1/fixed-assets", headers=headers, json=await _standard_asset_payload(client, headers))).json()["id"]
    await client.patch(f"/api/v1/fixed-assets/{idle_id}/status", headers=headers, json={"status": "idle"})

    active_list = (await client.get("/api/v1/fixed-assets", headers=headers, params={"status_filter": "active"})).json()
    assert {a["id"] for a in active_list} == {active_id}

    idle_list = (await client.get("/api/v1/fixed-assets", headers=headers, params={"status_filter": "idle"})).json()
    assert {a["id"] for a in idle_list} == {idle_id}


async def test_category_default_policy_roundtrips_and_is_optional(client):
    _, headers = await _bootstrap_and_login(client, "FA_CategoryDefaults")
    fixed = await _get_account(client, headers, "1410")
    accum = await _get_account(client, headers, "1490")
    expense = await _get_account(client, headers, "5950")

    with_defaults = await client.post(
        "/api/v1/fixed-assets/categories",
        headers=headers,
        json={
            "name": "Vehicles",
            "default_useful_life_months": 60,
            "default_fixed_asset_account_id": fixed["id"],
            "default_accumulated_depreciation_account_id": accum["id"],
            "default_depreciation_expense_account_id": expense["id"],
        },
    )
    assert with_defaults.status_code == 201, with_defaults.text
    body = with_defaults.json()
    assert body["default_useful_life_months"] == 60
    assert body["default_fixed_asset_account_id"] == fixed["id"]

    without_defaults = await client.post("/api/v1/fixed-assets/categories", headers=headers, json={"name": "Misc"})
    assert without_defaults.status_code == 201
    assert without_defaults.json()["default_useful_life_months"] is None


async def test_category_default_policy_is_a_prefill_only_not_enforced(client):
    """A category's default policy is a soft UI prefill (Owner decision,
    2026-08-19) -- an asset in that category can still be created with
    completely different useful-life/accounts than the category's own
    defaults, with no validation tying the two together."""
    _, headers = await _bootstrap_and_login(client, "FA_CategoryPrefillOnly")
    category = (
        await client.post(
            "/api/v1/fixed-assets/categories", headers=headers, json={"name": "Machinery", "default_useful_life_months": 60}
        )
    ).json()
    payload = await _standard_asset_payload(client, headers, category_id=category["id"], useful_life_months=12)
    resp = await client.post("/api/v1/fixed-assets", headers=headers, json=payload)
    assert resp.status_code == 201, resp.text
    assert resp.json()["useful_life_months"] == 12  # not silently overridden to the category's 60


async def test_reconciliation_includes_depreciation_expense_account(client):
    _, headers = await _bootstrap_and_login(client, "FA_ReconcileExpense")
    payload = await _standard_asset_payload(client, headers, cost="1200.00", salvage_value="0", useful_life_months=12)
    (await client.post("/api/v1/fixed-assets", headers=headers, json=payload)).json()
    await client.post("/api/v1/fixed-assets:run-depreciation", headers=headers, json={"period_month": "2026-01-01"})

    recon = await client.get("/api/v1/fixed-assets/reconciliation", headers=headers, params={"as_of_date": "2026-01-31"})
    assert recon.status_code == 200, recon.text
    body = recon.json()
    assert body["total_register_depreciation_expense"] == "100.0000"
    expense_row = next(r for r in body["accounts"] if r["account_code"] == "5950")
    assert expense_row["register_total"] == "100.0000"
    assert expense_row["gl_balance"] == "100.0000"
    assert expense_row["matches"] is True
    assert body["fully_matched"] is True


async def test_reconciliation_detects_manual_journal_on_depreciation_expense_account(client):
    """A manual JE hitting the Depreciation Expense account completely
    outside `run_depreciation` is exactly the drift this third
    reconciliation group exists to catch (mirrors the Owner's §12 concern
    about manual postings to a controlled account)."""
    _, headers = await _bootstrap_and_login(client, "FA_ReconcileExpenseManual")
    payload = await _standard_asset_payload(client, headers, cost="1200.00", salvage_value="0", useful_life_months=12)
    (await client.post("/api/v1/fixed-assets", headers=headers, json=payload)).json()
    await client.post("/api/v1/fixed-assets:run-depreciation", headers=headers, json={"period_month": "2026-01-01"})

    expense = await _get_account(client, headers, "5950")
    cash = await _get_account(client, headers, "1100")
    je = await client.post(
        "/api/v1/accounting/journal-entries",
        headers=headers,
        json={
            "journal_code": "GEN",
            "entry_date": "2026-01-20",
            "lines": [
                {"account_id": expense["id"], "debit": 50, "credit": 0},
                {"account_id": cash["id"], "debit": 0, "credit": 50},
            ],
        },
    )
    await client.post(f"/api/v1/accounting/journal-entries/{je.json()['id']}:post", headers=headers)

    recon = await client.get("/api/v1/fixed-assets/reconciliation", headers=headers, params={"as_of_date": "2026-01-31"})
    body = recon.json()
    expense_row = next(r for r in body["accounts"] if r["account_code"] == "5950")
    assert expense_row["register_total"] == "100.0000"  # unaware of the manual JE, by design
    assert expense_row["gl_balance"] == "150.0000"  # 100 from run_depreciation + 50 manual
    assert expense_row["difference"] == "-50.0000"
    assert expense_row["matches"] is False
    assert body["fully_matched"] is False


async def test_projected_schedule_shows_posted_and_projected_periods(client):
    _, headers = await _bootstrap_and_login(client, "FA_ProjectedSchedule")
    payload = await _standard_asset_payload(client, headers, cost="1200.00", salvage_value="0", useful_life_months=12)
    asset_id = (await client.post("/api/v1/fixed-assets", headers=headers, json=payload)).json()["id"]
    await client.post("/api/v1/fixed-assets:run-depreciation", headers=headers, json={"period_month": "2026-01-01"})
    await client.post("/api/v1/fixed-assets:run-depreciation", headers=headers, json={"period_month": "2026-02-01"})

    resp = await client.get(f"/api/v1/fixed-assets/{asset_id}/projected-schedule", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["monthly_depreciation"] == "100.0000"
    assert len(body["lines"]) == 12  # 1200/100 = 12 full periods, none capped short

    jan, feb, mar = body["lines"][0], body["lines"][1], body["lines"][2]
    assert jan["period_month"] == "2026-01-01"
    assert jan["posted"] is True
    assert jan["depreciation"] == "100.0000"
    assert feb["posted"] is True
    assert mar["posted"] is False  # not yet run
    assert mar["depreciation"] == "100.0000"  # still correctly projected

    final = body["lines"][-1]
    assert final["accumulated_depreciation"] == "1200.0000"
    assert final["net_book_value"] == "0.0000"


async def test_projected_schedule_caps_at_salvage_value(client):
    _, headers = await _bootstrap_and_login(client, "FA_ProjectedScheduleSalvage")
    payload = await _standard_asset_payload(
        client, headers, cost="1000.00", salvage_value="300.00", useful_life_months=7
    )
    asset_id = (await client.post("/api/v1/fixed-assets", headers=headers, json=payload)).json()["id"]

    resp = await client.get(f"/api/v1/fixed-assets/{asset_id}/projected-schedule", headers=headers)
    body = resp.json()
    for line in body["lines"]:
        assert Decimal(line["net_book_value"]) >= Decimal("300.0000")
    assert body["lines"][-1]["net_book_value"] == "300.0000"
    assert body["lines"][-1]["accumulated_depreciation"] == "700.0000"


async def test_projected_schedule_isolated_across_companies(client):
    _, headers_a = await _bootstrap_and_login(client, "FA_ScheduleTenantA")
    _, headers_b = await _bootstrap_and_login(client, "FA_ScheduleTenantB")
    payload = await _standard_asset_payload(client, headers_a)
    asset_id = (await client.post("/api/v1/fixed-assets", headers=headers_a, json=payload)).json()["id"]

    resp = await client.get(f"/api/v1/fixed-assets/{asset_id}/projected-schedule", headers=headers_b)
    assert resp.status_code == 404
