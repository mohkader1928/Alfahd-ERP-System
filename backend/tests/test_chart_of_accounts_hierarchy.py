"""Chart of Accounts hierarchy (P0-4, 3-Day Brief): 4-level cap, auto-
computed level, group-posting status, safe delete/reparent. Builds on
the bootstrap pattern in test_accounting_m1_smoke.py.
"""

from tests.conftest import unique_email, unique_vat


async def _bootstrap_and_login(client, label="CoA Hierarchy"):
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

    login_resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": payload["admin_email"], "password": payload["admin_password"]},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Company-Id": company_id}
    return company_id, headers


async def _get_account(client, headers, code: str) -> dict:
    resp = await client.get("/api/v1/accounting/chart-of-accounts", headers=headers)
    return next(a for a in resp.json() if a["code"] == code)


async def test_top_level_seeded_accounts_are_group_accounts_at_level_1(client):
    _, headers = await _bootstrap_and_login(client, "Seeded")
    assets = await _get_account(client, headers, "1000")
    cash = await _get_account(client, headers, "1100")
    assert assets["level"] == 1
    assert assets["is_group"] is True
    assert cash["level"] == 2
    assert cash["is_group"] is False


async def test_create_account_computes_level_and_promotes_parent_to_group(client):
    _, headers = await _bootstrap_and_login(client, "AutoLevel")
    cash = await _get_account(client, headers, "1100")

    resp = await client.post(
        "/api/v1/accounting/chart-of-accounts",
        headers=headers,
        json={"code": "1110", "name": "Petty Cash", "account_type_code": "asset", "parent_id": cash["id"]},
    )
    assert resp.status_code == 201, resp.text
    child = resp.json()
    assert child["level"] == 3
    assert child["is_group"] is False

    cash_after = await _get_account(client, headers, "1100")
    assert cash_after["is_group"] is True  # auto-promoted the moment it gained a child


async def test_create_account_rejects_a_5th_level(client):
    _, headers = await _bootstrap_and_login(client, "FifthLevel")
    cash = await _get_account(client, headers, "1100")
    l3 = (
        await client.post(
            "/api/v1/accounting/chart-of-accounts",
            headers=headers,
            json={"code": "1110", "name": "L3", "account_type_code": "asset", "parent_id": cash["id"]},
        )
    ).json()
    assert l3["level"] == 3
    l4 = (
        await client.post(
            "/api/v1/accounting/chart-of-accounts",
            headers=headers,
            json={"code": "1111", "name": "L4", "account_type_code": "asset", "parent_id": l3["id"]},
        )
    ).json()
    assert l4["level"] == 4

    resp = await client.post(
        "/api/v1/accounting/chart-of-accounts",
        headers=headers,
        json={"code": "1112", "name": "L5 rejected", "account_type_code": "asset", "parent_id": l4["id"]},
    )
    assert resp.status_code == 422
    assert "4" in resp.json()["detail"]


async def test_posting_to_a_group_account_is_rejected(client):
    _, headers = await _bootstrap_and_login(client, "PostToGroup")
    assets = await _get_account(client, headers, "1000")  # level 1, is_group=True
    capital = await _get_account(client, headers, "3100")

    resp = await client.post(
        "/api/v1/accounting/journal-entries",
        headers=headers,
        json={
            "journal_code": "GEN",
            "entry_date": "2026-06-01",
            "lines": [
                {"account_id": assets["id"], "debit": "100.00", "credit": "0"},
                {"account_id": capital["id"], "debit": "0", "credit": "100.00"},
            ],
        },
    )
    assert resp.status_code == 422
    assert "group account" in resp.json()["detail"].lower()


async def test_update_account_reparent_recomputes_level_and_descendants(client):
    _, headers = await _bootstrap_and_login(client, "Reparent")
    cash = await _get_account(client, headers, "1100")
    ar = await _get_account(client, headers, "1200")
    child = (
        await client.post(
            "/api/v1/accounting/chart-of-accounts",
            headers=headers,
            json={"code": "1110", "name": "Petty Cash", "account_type_code": "asset", "parent_id": cash["id"]},
        )
    ).json()
    assert child["level"] == 3

    resp = await client.patch(
        f"/api/v1/accounting/chart-of-accounts/{child['id']}",
        headers=headers,
        json={"parent_id": ar["id"], "parent_id_set": True},
    )
    assert resp.status_code == 200, resp.text
    moved = resp.json()
    assert moved["parent_id"] == ar["id"]
    assert moved["level"] == 3  # AR is also level 2, so level is unchanged here

    ar_after = await _get_account(client, headers, "1200")
    assert ar_after["is_group"] is True


async def test_update_account_rejects_reparent_that_would_exceed_4_levels(client):
    _, headers = await _bootstrap_and_login(client, "ReparentOverflow")
    cash = await _get_account(client, headers, "1100")
    ar = await _get_account(client, headers, "1200")
    l3 = (
        await client.post(
            "/api/v1/accounting/chart-of-accounts",
            headers=headers,
            json={"code": "1110", "name": "L3", "account_type_code": "asset", "parent_id": cash["id"]},
        )
    ).json()
    l4 = (
        await client.post(
            "/api/v1/accounting/chart-of-accounts",
            headers=headers,
            json={"code": "1111", "name": "L4", "account_type_code": "asset", "parent_id": l3["id"]},
        )
    ).json()
    assert l4["level"] == 4

    l3_under_ar = (
        await client.post(
            "/api/v1/accounting/chart-of-accounts",
            headers=headers,
            json={"code": "1210", "name": "AR L3", "account_type_code": "asset", "parent_id": ar["id"]},
        )
    ).json()
    l4_under_ar = (
        await client.post(
            "/api/v1/accounting/chart-of-accounts",
            headers=headers,
            json={"code": "1211", "name": "AR L4", "account_type_code": "asset", "parent_id": l3_under_ar["id"]},
        )
    ).json()
    assert l4_under_ar["level"] == 4

    # Moving l3 (whose own descendant l4 sits at level 4) under l3_under_ar
    # (already level 3) would push l4 to level 5 -- must be rejected.
    resp = await client.patch(
        f"/api/v1/accounting/chart-of-accounts/{l3['id']}",
        headers=headers,
        json={"parent_id": l3_under_ar["id"], "parent_id_set": True},
    )
    assert resp.status_code == 422


async def test_update_account_rejects_moving_under_own_descendant(client):
    _, headers = await _bootstrap_and_login(client, "CycleGuard")
    cash = await _get_account(client, headers, "1100")
    child = (
        await client.post(
            "/api/v1/accounting/chart-of-accounts",
            headers=headers,
            json={"code": "1110", "name": "Petty Cash", "account_type_code": "asset", "parent_id": cash["id"]},
        )
    ).json()

    resp = await client.patch(
        f"/api/v1/accounting/chart-of-accounts/{cash['id']}",
        headers=headers,
        json={"parent_id": child["id"], "parent_id_set": True},
    )
    assert resp.status_code == 422


async def test_update_account_rejects_ungrouping_an_account_with_children(client):
    _, headers = await _bootstrap_and_login(client, "Ungroup")
    cash = await _get_account(client, headers, "1100")
    await client.post(
        "/api/v1/accounting/chart-of-accounts",
        headers=headers,
        json={"code": "1110", "name": "Petty Cash", "account_type_code": "asset", "parent_id": cash["id"]},
    )

    resp = await client.patch(
        f"/api/v1/accounting/chart-of-accounts/{cash['id']}",
        headers=headers,
        json={"is_group": False},
    )
    assert resp.status_code == 422


async def test_delete_account_rejected_when_it_has_children(client):
    _, headers = await _bootstrap_and_login(client, "DeleteWithChildren")
    cash = await _get_account(client, headers, "1100")
    await client.post(
        "/api/v1/accounting/chart-of-accounts",
        headers=headers,
        json={"code": "1110", "name": "Petty Cash", "account_type_code": "asset", "parent_id": cash["id"]},
    )

    resp = await client.delete(f"/api/v1/accounting/chart-of-accounts/{cash['id']}", headers=headers)
    assert resp.status_code == 422


async def test_delete_account_rejected_when_it_has_posted_transactions(client):
    _, headers = await _bootstrap_and_login(client, "DeleteWithTx")
    cash = await _get_account(client, headers, "1100")
    capital = await _get_account(client, headers, "3100")
    await client.post(
        "/api/v1/accounting/journal-entries",
        headers=headers,
        json={
            "journal_code": "GEN",
            "entry_date": "2026-06-01",
            "lines": [
                {"account_id": cash["id"], "debit": "100.00", "credit": "0"},
                {"account_id": capital["id"], "debit": "0", "credit": "100.00"},
            ],
        },
    )

    resp = await client.delete(f"/api/v1/accounting/chart-of-accounts/{cash['id']}", headers=headers)
    assert resp.status_code == 422


async def test_delete_account_succeeds_when_unused(client):
    _, headers = await _bootstrap_and_login(client, "DeleteUnused")
    cash = await _get_account(client, headers, "1100")
    created = (
        await client.post(
            "/api/v1/accounting/chart-of-accounts",
            headers=headers,
            json={"code": "1110", "name": "Petty Cash", "account_type_code": "asset", "parent_id": cash["id"]},
        )
    ).json()

    resp = await client.delete(f"/api/v1/accounting/chart-of-accounts/{created['id']}", headers=headers)
    assert resp.status_code == 204

    all_accounts = (await client.get("/api/v1/accounting/chart-of-accounts", headers=headers)).json()
    assert not any(a["id"] == created["id"] for a in all_accounts)
