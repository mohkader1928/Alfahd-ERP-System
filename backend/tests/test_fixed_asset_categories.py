"""Fixed Asset Categories + category-scoped depreciation + the new
Register/Depreciation Schedule reports — the Owner's "split Fixed Assets
into its own section" request required classifying assets so depreciation
could be run for one specific group rather than only "all assets"."""

from tests.conftest import unique_email, unique_vat


async def _bootstrap_and_login(client, label="FAC"):
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


async def test_create_and_list_categories(client):
    _, headers = await _bootstrap_and_login(client, "FAC_Create")
    root = await client.post("/api/v1/fixed-assets/categories", headers=headers, json={"name": "Vehicles"})
    assert root.status_code == 201, root.text
    child = await client.post(
        "/api/v1/fixed-assets/categories",
        headers=headers,
        json={"name": "Trucks", "parent_id": root.json()["id"]},
    )
    assert child.status_code == 201, child.text
    assert child.json()["parent_id"] == root.json()["id"]

    listing = await client.get("/api/v1/fixed-assets/categories", headers=headers)
    names = {c["name"] for c in listing.json()}
    assert names == {"Vehicles", "Trucks"}


async def test_category_duplicate_name_at_same_level_rejected(client):
    _, headers = await _bootstrap_and_login(client, "FAC_Dup")
    await client.post("/api/v1/fixed-assets/categories", headers=headers, json={"name": "Vehicles"})
    dup = await client.post("/api/v1/fixed-assets/categories", headers=headers, json={"name": "vehicles"})
    assert dup.status_code == 422
    assert "already exists" in dup.json()["detail"]


async def test_category_circular_parent_rejected(client):
    _, headers = await _bootstrap_and_login(client, "FAC_Cycle")
    a = (await client.post("/api/v1/fixed-assets/categories", headers=headers, json={"name": "A"})).json()
    b = (
        await client.post(
            "/api/v1/fixed-assets/categories", headers=headers, json={"name": "B", "parent_id": a["id"]}
        )
    ).json()

    cycle = await client.patch(
        f"/api/v1/fixed-assets/categories/{a['id']}", headers=headers, json={"name": "A", "parent_id": b["id"]}
    )
    assert cycle.status_code == 422
    assert "Circular" in cycle.json()["detail"]


async def test_delete_category_blocked_by_children(client):
    _, headers = await _bootstrap_and_login(client, "FAC_DelChild")
    parent = (await client.post("/api/v1/fixed-assets/categories", headers=headers, json={"name": "Parent"})).json()
    await client.post("/api/v1/fixed-assets/categories", headers=headers, json={"name": "Child", "parent_id": parent["id"]})

    resp = await client.delete(f"/api/v1/fixed-assets/categories/{parent['id']}", headers=headers)
    assert resp.status_code == 422
    assert "child categories" in resp.json()["detail"]


async def test_delete_category_blocked_when_assigned_to_asset(client):
    _, headers = await _bootstrap_and_login(client, "FAC_DelAssigned")
    category = (await client.post("/api/v1/fixed-assets/categories", headers=headers, json={"name": "Vehicles"})).json()
    payload = await _standard_asset_payload(client, headers, category_id=category["id"])
    await client.post("/api/v1/fixed-assets", headers=headers, json=payload)

    resp = await client.delete(f"/api/v1/fixed-assets/categories/{category['id']}", headers=headers)
    assert resp.status_code == 422
    assert "fixed assets" in resp.json()["detail"]


async def test_create_asset_with_category_and_invalid_category_rejected(client):
    _, headers = await _bootstrap_and_login(client, "FAC_AssetCat")
    category = (await client.post("/api/v1/fixed-assets/categories", headers=headers, json={"name": "Vehicles"})).json()

    good = await client.post(
        "/api/v1/fixed-assets", headers=headers, json=await _standard_asset_payload(client, headers, category_id=category["id"])
    )
    assert good.status_code == 201, good.text
    assert good.json()["category_id"] == category["id"]

    bad = await client.post(
        "/api/v1/fixed-assets",
        headers=headers,
        json=await _standard_asset_payload(client, headers, category_id="00000000-0000-0000-0000-000000000099"),
    )
    assert bad.status_code == 422
    assert "Invalid asset category" in bad.json()["detail"]


async def test_run_depreciation_scoped_to_category_only_affects_that_group(client):
    """The Owner's actual requirement: run depreciation for "a specific
    group of assets", not just "all assets"."""
    _, headers = await _bootstrap_and_login(client, "FAC_ScopedRun")
    vehicles = (await client.post("/api/v1/fixed-assets/categories", headers=headers, json={"name": "Vehicles"})).json()
    computers = (await client.post("/api/v1/fixed-assets/categories", headers=headers, json={"name": "Computers"})).json()

    truck = (
        await client.post(
            "/api/v1/fixed-assets",
            headers=headers,
            json=await _standard_asset_payload(
                client, headers, category_id=vehicles["id"], cost="1200.00", useful_life_months=12
            ),
        )
    ).json()
    laptop = (
        await client.post(
            "/api/v1/fixed-assets",
            headers=headers,
            json=await _standard_asset_payload(
                client, headers, category_id=computers["id"], cost="2400.00", useful_life_months=24
            ),
        )
    ).json()

    run = await client.post(
        "/api/v1/fixed-assets:run-depreciation",
        headers=headers,
        json={"period_month": "2026-01-01", "category_id": vehicles["id"]},
    )
    assert run.status_code == 200, run.text
    body = run.json()
    assert body["assets_posted"] == 1
    assert body["posted"][0]["asset_id"] == truck["id"]

    truck_after = (await client.get(f"/api/v1/fixed-assets/{truck['id']}", headers=headers)).json()
    laptop_after = (await client.get(f"/api/v1/fixed-assets/{laptop['id']}", headers=headers)).json()
    assert truck_after["accumulated_depreciation"] == "100.0000"
    assert laptop_after["accumulated_depreciation"] == "0.0000"  # untouched — different category

    # Running for the OTHER category now depreciates the laptop, not the truck again.
    run2 = await client.post(
        "/api/v1/fixed-assets:run-depreciation",
        headers=headers,
        json={"period_month": "2026-01-01", "category_id": computers["id"]},
    )
    assert run2.json()["assets_posted"] == 1
    assert run2.json()["posted"][0]["asset_id"] == laptop["id"]


async def test_register_report_status_filter(client):
    _, headers = await _bootstrap_and_login(client, "FAC_RegisterFilter")
    payload = await _standard_asset_payload(client, headers)
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
    # A second, still-active asset.
    await client.post(
        "/api/v1/fixed-assets", headers=headers, json=await _standard_asset_payload(client, headers)
    )

    active_only = await client.get("/api/v1/fixed-assets", headers=headers, params={"status_filter": "active"})
    assert len(active_only.json()) == 1
    disposed_only = await client.get("/api/v1/fixed-assets", headers=headers, params={"status_filter": "disposed"})
    assert len(disposed_only.json()) == 1
    everything = await client.get("/api/v1/fixed-assets", headers=headers)
    assert len(everything.json()) == 2


async def test_depreciation_schedule_report_totals_and_category_scope(client):
    _, headers = await _bootstrap_and_login(client, "FAC_Schedule")
    vehicles = (await client.post("/api/v1/fixed-assets/categories", headers=headers, json={"name": "Vehicles"})).json()
    truck = (
        await client.post(
            "/api/v1/fixed-assets",
            headers=headers,
            json=await _standard_asset_payload(
                client, headers, category_id=vehicles["id"], cost="1200.00", useful_life_months=12
            ),
        )
    ).json()
    laptop = (
        await client.post(
            "/api/v1/fixed-assets",
            headers=headers,
            json=await _standard_asset_payload(client, headers, cost="2400.00", useful_life_months=24),
        )
    ).json()
    await client.post("/api/v1/fixed-assets:run-depreciation", headers=headers, json={"period_month": "2026-01-01"})

    everything = await client.get(
        "/api/v1/fixed-assets/depreciation-schedule",
        headers=headers,
        params={"date_from": "2026-01-01", "date_to": "2026-01-31"},
    )
    assert everything.status_code == 200, everything.text
    body = everything.json()
    assert len(body["lines"]) == 2
    assert body["total_amount"] == "200.0000"  # 100 (truck) + 100 (laptop)

    scoped = await client.get(
        "/api/v1/fixed-assets/depreciation-schedule",
        headers=headers,
        params={"date_from": "2026-01-01", "date_to": "2026-01-31", "category_id": vehicles["id"]},
    )
    scoped_body = scoped.json()
    assert len(scoped_body["lines"]) == 1
    assert scoped_body["lines"][0]["asset_id"] == truck["id"]
    assert scoped_body["total_amount"] == "100.0000"
    assert laptop["id"]  # sanity: laptop was created outside the scoped result


async def test_categories_isolated_across_companies(client):
    _, headers_a = await _bootstrap_and_login(client, "FAC_TenantA")
    _, headers_b = await _bootstrap_and_login(client, "FAC_TenantB")

    category = (await client.post("/api/v1/fixed-assets/categories", headers=headers_a, json={"name": "Vehicles"})).json()

    cross_update = await client.patch(
        f"/api/v1/fixed-assets/categories/{category['id']}", headers=headers_b, json={"name": "Hacked"}
    )
    assert cross_update.status_code == 404

    list_b = await client.get("/api/v1/fixed-assets/categories", headers=headers_b)
    assert list_b.json() == []
