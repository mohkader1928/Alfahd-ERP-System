"""P0-5 (3-Day Brief): Fixed Assets — register, straight-line depreciation,
and disposal, all integrated with the GL via JournalEntryService."""

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
    assert body["disposal_proceeds"] == "1300.00"

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
