"""INV-002 — configurable Inventory Adjustment account for Cycle Count
approval (BASELINE-DRIFT-001's sibling incident).

Root cause: Cycle Count approval hardcoded account code "5200" ("Operating
Expenses") as its shortage/surplus adjustment account. This broke the
moment any company added a sub-account under it -- an ordinary
bookkeeping action (Salaries, Rent, Commission, ...) that auto-promotes
the parent to a group account, which JournalEntryService.create_draft_entry
correctly refuses to post to. Confirmed live in production for "Ehab
Abdelrahman Testing Co." (CC-000002), surfacing as an opaque HTTP 500
("An unexpected error occurred") because approve_cycle_count had no
try/except around the posting call.

Fix: a company-scoped AccountingSettings.inventory_adjustment_account_id,
validated (same company, not a group, active, expense-type) both when
saved and again defensively at posting time, with the account's own
create_draft_entry group-account guard never weakened. One account for
both shortage and surplus per Owner's accounting policy -- debit/credit
polarity distinguishes the two.

Owner design correction: EVERY company -- new or existing -- starts with
inventory_adjustment_account_id unconfigured (NULL / no row). An earlier
iteration of this fix auto-defaulted freshly bootstrapped companies to
their own just-seeded "5200"; Owner explicitly rejected that as replacing
one implicit-5200 dependency with another. Option 2 exists specifically
so each company makes its own explicit choice via
PATCH /api/v1/accounting/settings.
"""

from tests.conftest import unique_email, unique_vat


async def _bootstrap_and_login(client, label="Inv002"):
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


async def _create_product(client, headers, name="Test Item") -> str:
    resp = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"SKU-{unique_vat()[:8]}", "name": name, "sales_price": "1000.00"},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _create_warehouse(client, headers) -> dict:
    resp = await client.post(
        "/api/v1/inventory/warehouses", headers=headers, json={"name": "Main Warehouse", "is_default": True}
    )
    assert resp.status_code == 201
    return resp.json()


async def _configure_adjustment_account(client, headers, account_id: str) -> None:
    resp = await client.patch(
        "/api/v1/accounting/settings", headers=headers, json={"inventory_adjustment_account_id": account_id}
    )
    assert resp.status_code == 200, resp.text


async def _create_leaf_expense_account(client, headers, code: str, name: str) -> dict:
    """A fresh, unused, never-subdivided expense leaf -- code 59xx to stay
    well clear of the seeded template's own codes."""
    resp = await client.post(
        "/api/v1/accounting/chart-of-accounts",
        headers=headers,
        json={"code": code, "name": name, "account_type_code": "expense", "parent_id": None},
    )
    assert resp.status_code == 201
    return resp.json()


# --- TEST 1 / 2 -----------------------------------------------------------


async def test_configured_account_must_belong_to_same_company(client):
    """TEST 1/2: an account id belonging to a DIFFERENT company is rejected
    with the existing 'not found in this company' shape, not silently
    accepted and not leaked as a different account existing elsewhere."""
    _, headers_a = await _bootstrap_and_login(client, "SettingsCompanyA")
    _, headers_b = await _bootstrap_and_login(client, "SettingsCompanyB")
    b_leaf = await _create_leaf_expense_account(client, headers_b, "5960", "B's Own Adjustment")

    resp = await client.patch(
        "/api/v1/accounting/settings",
        headers=headers_a,
        json={"inventory_adjustment_account_id": b_leaf["id"]},
    )
    assert resp.status_code == 422, resp.text
    assert "not found in this company" in resp.json()["detail"].lower()

    # A's own settings must be untouched by the rejected attempt -- still
    # unconfigured (no automatic default of any kind), not B's account.
    a_settings = (await client.get("/api/v1/accounting/settings", headers=headers_a)).json()
    assert a_settings["inventory_adjustment_account_id"] is None


async def test_configured_account_belonging_to_same_company_accepted(client):
    """TEST 1: a same-company, valid leaf expense account is accepted and
    persisted."""
    _, headers = await _bootstrap_and_login(client, "SettingsSameCompany")
    leaf = await _create_leaf_expense_account(client, headers, "5960", "Custom Adjustment")

    resp = await client.patch(
        "/api/v1/accounting/settings",
        headers=headers,
        json={"inventory_adjustment_account_id": leaf["id"]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["inventory_adjustment_account_id"] == leaf["id"]

    get_resp = await client.get("/api/v1/accounting/settings", headers=headers)
    assert get_resp.json()["inventory_adjustment_account_id"] == leaf["id"]


# --- TEST 3 -----------------------------------------------------------


async def test_group_account_selection_rejected_at_save_time(client):
    """TEST 3: "5000 Expenses" is a group account immediately after
    seeding (it has children: 5100/5150/5200/5900/5950) -- selecting it
    must be rejected, never silently accepted."""
    _, headers = await _bootstrap_and_login(client, "SettingsGroupReject")
    expenses_root = await _get_account(client, headers, "5000")
    assert expenses_root["is_group"] is True

    resp = await client.patch(
        "/api/v1/accounting/settings",
        headers=headers,
        json={"inventory_adjustment_account_id": expenses_root["id"]},
    )
    assert resp.status_code == 422, resp.text
    assert "group account" in resp.json()["detail"].lower()


# --- TEST 4 -----------------------------------------------------------


async def test_inactive_account_selection_rejected(client):
    """TEST 4a."""
    _, headers = await _bootstrap_and_login(client, "SettingsInactiveReject")
    leaf = await _create_leaf_expense_account(client, headers, "5960", "Soon Inactive")
    patch_resp = await client.patch(
        f"/api/v1/accounting/chart-of-accounts/{leaf['id']}", headers=headers, json={"is_active": False}
    )
    assert patch_resp.status_code == 200

    resp = await client.patch(
        "/api/v1/accounting/settings",
        headers=headers,
        json={"inventory_adjustment_account_id": leaf["id"]},
    )
    assert resp.status_code == 422, resp.text
    assert "not active" in resp.json()["detail"].lower()


async def test_deleted_account_selection_rejected(client):
    """TEST 4b: a soft-deleted account id resolves to nothing (repository
    filters deleted_at IS NULL), surfacing as the same 'not found' error
    as a nonexistent id -- never a 500, never silently accepted."""
    _, headers = await _bootstrap_and_login(client, "SettingsDeletedReject")
    leaf = await _create_leaf_expense_account(client, headers, "5960", "Soon Deleted")
    delete_resp = await client.delete(f"/api/v1/accounting/chart-of-accounts/{leaf['id']}", headers=headers)
    assert delete_resp.status_code == 204

    resp = await client.patch(
        "/api/v1/accounting/settings",
        headers=headers,
        json={"inventory_adjustment_account_id": leaf["id"]},
    )
    assert resp.status_code == 422, resp.text
    assert "not found" in resp.json()["detail"].lower()


async def test_non_expense_type_account_rejected(client):
    """Mandatory validation: 'appropriate accounting type for this
    policy' -- an asset-type leaf (e.g. seeded '1100 Cash and Bank') must
    be rejected even though it's a perfectly valid, active, non-group
    account in every other respect."""
    _, headers = await _bootstrap_and_login(client, "SettingsWrongType")
    cash = await _get_account(client, headers, "1100")
    assert cash["is_group"] is False

    resp = await client.patch(
        "/api/v1/accounting/settings",
        headers=headers,
        json={"inventory_adjustment_account_id": cash["id"]},
    )
    assert resp.status_code == 422, resp.text
    assert "expense" in resp.json()["detail"].lower()


# --- TEST 5 -----------------------------------------------------------


async def test_fresh_company_starts_unconfigured(client):
    """TEST 1: a freshly bootstrapped company gets its normal Chart of
    Accounts but NO automatic inventory adjustment account -- no row, or
    a row with a NULL account id, either way reads back as unconfigured."""
    _, headers = await _bootstrap_and_login(client, "FreshCompanyUnconfigured")
    settings = (await client.get("/api/v1/accounting/settings", headers=headers)).json()
    assert settings["inventory_adjustment_account_id"] is None


async def test_missing_configuration_produces_controlled_4xx_not_500(client):
    """TEST 2: a freshly bootstrapped company (unconfigured by default,
    per test_fresh_company_starts_unconfigured above) attempts to approve
    a cycle count with a real shortage -- must be a clean 422 naming
    Accounting Settings, never an opaque 500 and never a guessed account."""
    _, headers = await _bootstrap_and_login(client, "SettingsMissingConfig")
    product_id = await _create_product(client, headers)
    wh = await _create_warehouse(client, headers)
    location_id = wh["default_location"]["id"]
    await client.post(
        "/api/v1/inventory/stock/receive",
        headers=headers,
        json={"product_id": product_id, "location_id": location_id, "qty": "10", "unit_cost": "20.00"},
    )
    create_resp = await client.post(
        "/api/v1/inventory/cycle-counts",
        headers=headers,
        json={
            "warehouse_id": wh["warehouse"]["id"],
            "scheduled_date": "2026-04-01",
            "lines": [{"product_id": product_id, "location_id": location_id, "counted_qty": "7"}],
        },
    )
    cycle_count_id = create_resp.json()["cycle_count"]["id"]

    approve_resp = await client.post(f"/api/v1/inventory/cycle-counts/{cycle_count_id}:approve", headers=headers)
    assert approve_resp.status_code == 422, approve_resp.text
    assert approve_resp.status_code != 500
    assert "accounting settings" in approve_resp.json()["detail"].lower()

    # And the cycle count itself must NOT have been silently marked
    # approved despite the failed posting.
    detail_resp = await client.get(f"/api/v1/inventory/cycle-counts/{cycle_count_id}", headers=headers)
    assert detail_resp.json()["cycle_count"]["status"] != "approved"


# --- TEST 6 / 9 (CC-000002 exact reproduction) -----------------------------


async def test_cc_000002_shaped_scenario_no_longer_crashes(client):
    """TEST 6 + TEST 9: exact reproduction of the real production defect.
    An admin explicitly configures the company's Cycle Count inventory
    adjustment account to "5200" (VALID at configuration time -- no
    automatic default exists any more, so this models the real-world act
    of an admin choosing it), then the company does the ordinary,
    encouraged bookkeeping thing of adding a real expense sub-account
    under it (exactly what happened at Ehab Abdelrahman Testing Co.) --
    silently promoting it to a group account. The already-configured
    setting is now stale. Approval must re-validate defensively at
    posting time and fail with a controlled 422, never the 500 seen in
    production."""
    _, headers = await _bootstrap_and_login(client, "CC000002Repro")
    operating_expenses = await _get_account(client, headers, "5200")
    assert operating_expenses["is_group"] is False  # true immediately after seeding

    configure_resp = await client.patch(
        "/api/v1/accounting/settings",
        headers=headers,
        json={"inventory_adjustment_account_id": operating_expenses["id"]},
    )
    assert configure_resp.status_code == 200, configure_resp.text

    # Ordinary bookkeeping: add "Salaries" under Operating Expenses.
    child_resp = await client.post(
        "/api/v1/accounting/chart-of-accounts",
        headers=headers,
        json={
            "code": "5200001",
            "name": "Salaries",
            "account_type_code": "expense",
            "parent_id": operating_expenses["id"],
        },
    )
    assert child_resp.status_code == 201
    operating_expenses = await _get_account(client, headers, "5200")
    assert operating_expenses["is_group"] is True  # auto-promoted, exactly like production

    product_id = await _create_product(client, headers)
    wh = await _create_warehouse(client, headers)
    location_id = wh["default_location"]["id"]
    await client.post(
        "/api/v1/inventory/stock/receive",
        headers=headers,
        json={"product_id": product_id, "location_id": location_id, "qty": "16", "unit_cost": "50.00"},
    )
    create_resp = await client.post(
        "/api/v1/inventory/cycle-counts",
        headers=headers,
        json={
            "warehouse_id": wh["warehouse"]["id"],
            "scheduled_date": "2026-04-01",
            "lines": [{"product_id": product_id, "location_id": location_id, "counted_qty": "12"}],
        },
    )
    cycle_count_id = create_resp.json()["cycle_count"]["id"]

    approve_resp = await client.post(f"/api/v1/inventory/cycle-counts/{cycle_count_id}:approve", headers=headers)
    assert approve_resp.status_code == 422, approve_resp.text
    assert approve_resp.status_code != 500
    assert "accounting settings" in approve_resp.json()["detail"].lower()


# --- TEST 7 / 8 (shortage / surplus posting correctness) ------------------


async def test_shortage_debits_adjustment_account_credits_inventory(client):
    """TEST 3 + TEST 7: after an admin explicitly configures a valid
    account (no automatic default exists), counted < system -> Debit
    adjustment account, Credit inventory (1300), per Owner's approved
    accounting policy."""
    _, headers = await _bootstrap_and_login(client, "ShortagePosting")
    operating_expenses = await _get_account(client, headers, "5200")
    await _configure_adjustment_account(client, headers, operating_expenses["id"])

    product_id = await _create_product(client, headers)
    wh = await _create_warehouse(client, headers)
    location_id = wh["default_location"]["id"]
    await client.post(
        "/api/v1/inventory/stock/receive",
        headers=headers,
        json={"product_id": product_id, "location_id": location_id, "qty": "10", "unit_cost": "20.00"},
    )
    create_resp = await client.post(
        "/api/v1/inventory/cycle-counts",
        headers=headers,
        json={
            "warehouse_id": wh["warehouse"]["id"],
            "scheduled_date": "2026-04-01",
            "lines": [{"product_id": product_id, "location_id": location_id, "counted_qty": "7"}],  # shortage of 3
        },
    )
    cycle_count_id = create_resp.json()["cycle_count"]["id"]
    approve_resp = await client.post(f"/api/v1/inventory/cycle-counts/{cycle_count_id}:approve", headers=headers)
    assert approve_resp.status_code == 200, approve_resp.text

    trial_balance = await client.get(
        "/api/v1/accounting/reports/trial-balance",
        headers=headers,
        params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
    )
    rows = {row["account_code"]: row for row in trial_balance.json()}
    assert rows["1300"]["total_credit"] == "60.0000"  # 3 units * 20.00 written off
    assert rows["5200"]["total_debit"] == "60.0000"  # shortage cost debited to the adjustment account


async def test_surplus_debits_inventory_credits_adjustment_account(client):
    """TEST 4 + TEST 8: after an admin explicitly configures a valid
    account, counted > system -> Debit inventory (1300), Credit
    adjustment account, per Owner's approved accounting policy."""
    _, headers = await _bootstrap_and_login(client, "SurplusPosting")
    operating_expenses = await _get_account(client, headers, "5200")
    await _configure_adjustment_account(client, headers, operating_expenses["id"])

    product_id = await _create_product(client, headers)
    wh = await _create_warehouse(client, headers)
    location_id = wh["default_location"]["id"]
    await client.post(
        "/api/v1/inventory/stock/receive",
        headers=headers,
        json={"product_id": product_id, "location_id": location_id, "qty": "10", "unit_cost": "20.00"},
    )
    create_resp = await client.post(
        "/api/v1/inventory/cycle-counts",
        headers=headers,
        json={
            "warehouse_id": wh["warehouse"]["id"],
            "scheduled_date": "2026-04-01",
            "lines": [{"product_id": product_id, "location_id": location_id, "counted_qty": "14"}],  # surplus of 4
        },
    )
    cycle_count_id = create_resp.json()["cycle_count"]["id"]
    approve_resp = await client.post(f"/api/v1/inventory/cycle-counts/{cycle_count_id}:approve", headers=headers)
    assert approve_resp.status_code == 200, approve_resp.text

    trial_balance = await client.get(
        "/api/v1/accounting/reports/trial-balance",
        headers=headers,
        params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
    )
    rows = {row["account_code"]: row for row in trial_balance.json()}
    assert rows["1300"]["total_debit"] == "80.0000"  # 4 units * 20.00 found stock
    assert rows["5200"]["total_credit"] == "80.0000"  # surplus value credited to the adjustment account


# --- TEST 10 (group-account guard never weakened) --------------------------


async def test_manual_journal_entry_to_group_account_still_rejected(client):
    """TEST 10: JournalEntryService.create_draft_entry's own group-account
    guard (used by every posting path, not just Cycle Count) is untouched
    by INV-002 -- a manual journal entry to a known group account ("5000
    Expenses") is still rejected exactly as before."""
    _, headers = await _bootstrap_and_login(client, "GroupGuardIntact")
    expenses_root = await _get_account(client, headers, "5000")
    cash = await _get_account(client, headers, "1100")

    resp = await client.post(
        "/api/v1/accounting/journal-entries",
        headers=headers,
        json={
            "journal_code": "GEN",
            "entry_date": "2026-04-01",
            "lines": [
                {"account_id": expenses_root["id"], "debit": "100.00", "credit": "0"},
                {"account_id": cash["id"], "debit": "0", "credit": "100.00"},
            ],
        },
    )
    assert resp.status_code == 422, resp.text
    assert "group account" in resp.json()["detail"].lower()


# --- TEST 12 (tenant isolation) --------------------------------------------


async def test_each_company_posts_only_to_its_own_configured_account(client):
    """TEST 12: two companies, each with its own distinct configured
    adjustment account -- approving Company A's cycle count must never
    touch Company B's account or vice versa."""
    _, headers_a = await _bootstrap_and_login(client, "IsolationPostingA")
    _, headers_b = await _bootstrap_and_login(client, "IsolationPostingB")

    leaf_a = await _create_leaf_expense_account(client, headers_a, "5960", "A's Adjustment")
    leaf_b = await _create_leaf_expense_account(client, headers_b, "5960", "B's Adjustment")
    await _configure_adjustment_account(client, headers_a, leaf_a["id"])
    await _configure_adjustment_account(client, headers_b, leaf_b["id"])

    for headers in (headers_a, headers_b):
        product_id = await _create_product(client, headers)
        wh = await _create_warehouse(client, headers)
        location_id = wh["default_location"]["id"]
        await client.post(
            "/api/v1/inventory/stock/receive",
            headers=headers,
            json={"product_id": product_id, "location_id": location_id, "qty": "10", "unit_cost": "20.00"},
        )
        create_resp = await client.post(
            "/api/v1/inventory/cycle-counts",
            headers=headers,
            json={
                "warehouse_id": wh["warehouse"]["id"],
                "scheduled_date": "2026-04-01",
                "lines": [{"product_id": product_id, "location_id": location_id, "counted_qty": "7"}],
            },
        )
        cycle_count_id = create_resp.json()["cycle_count"]["id"]
        approve_resp = await client.post(
            f"/api/v1/inventory/cycle-counts/{cycle_count_id}:approve", headers=headers
        )
        assert approve_resp.status_code == 200, approve_resp.text

    tb_a = {
        row["account_code"]: row
        for row in (
            await client.get(
                "/api/v1/accounting/reports/trial-balance",
                headers=headers_a,
                params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
            )
        ).json()
    }
    tb_b = {
        row["account_code"]: row
        for row in (
            await client.get(
                "/api/v1/accounting/reports/trial-balance",
                headers=headers_b,
                params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
            )
        ).json()
    }
    assert tb_a["5960"]["total_debit"] == "60.0000"
    assert tb_b["5960"]["total_debit"] == "60.0000"

    # Company A's settings/accounts are never visible under Company B's
    # headers and vice versa (RLS + explicit company_id checks).
    cross_resp = await client.patch(
        "/api/v1/accounting/settings", headers=headers_b, json={"inventory_adjustment_account_id": leaf_a["id"]}
    )
    assert cross_resp.status_code == 422
