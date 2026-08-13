"""Journal entry draft cancel/void — owner-reported gap closure.

Owner scenario: closed fiscal period 2026-01-01..2026-01-31, a draft entry
(created before the close) was rejected at posting time (correctly — the
period is closed) but had no way out afterward: could not be posted,
edited, or cancelled. The backend had exactly three operations on a
journal entry — create (draft), post, reverse (posted-only) — and no
draft-only exit at all.

A draft entry has zero ledger impact until posted (JournalEntryService.
post_entry is the only place that ever touches account balances), so
cancelling one is deliberately independent of fiscal period status —
unlike post_entry, cancel_draft_entry does not consult FiscalPeriodRepository
at all.
"""

from tests.conftest import unique_email, unique_vat


async def _bootstrap(client, label: str) -> dict:
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
    return {"company_id": company_id, "branch_id": branch_id, "headers": headers}


async def _create_limited_user(client, headers, company_id: str) -> dict:
    role_resp = await client.post("/api/v1/identity/roles", headers=headers, json={"name": "No Permissions"})
    assert role_resp.status_code == 201
    role_id = role_resp.json()["id"]

    email = unique_email()
    password = "Str0ng!Passw0rd"
    user_resp = await client.post(
        "/api/v1/identity/users",
        headers=headers,
        json={"email": email, "full_name": "Limited User", "password": password, "company_id": company_id},
    )
    assert user_resp.status_code == 201
    user_id = user_resp.json()["id"]
    assign_resp = await client.post(
        f"/api/v1/identity/users/{user_id}/roles", headers=headers, json={"role_id": role_id}
    )
    assert assign_resp.status_code == 204

    login_resp = await client.post("/api/v1/identity/auth/login", json={"email": email, "password": password})
    token = login_resp.json()["access_token"]
    return {"headers": {"Authorization": f"Bearer {token}", "X-Company-Id": company_id}}


async def _account_id(client, headers, code: str) -> str:
    accounts = (await client.get("/api/v1/accounting/chart-of-accounts", headers=headers)).json()
    return next(a["id"] for a in accounts if a["code"] == code)


async def _create_draft_entry(client, headers, *, entry_date: str, ar_id: str, revenue_id: str, amount: str = "100.00") -> str:
    create_resp = await client.post(
        "/api/v1/accounting/journal-entries",
        headers=headers,
        json={
            "journal_code": "GEN",
            "entry_date": entry_date,
            "reference": "JE-cancel test entry",
            "lines": [
                {"account_id": ar_id, "debit": amount, "credit": "0"},
                {"account_id": revenue_id, "debit": "0", "credit": amount},
            ],
        },
    )
    assert create_resp.status_code == 201
    return create_resp.json()["id"]


async def test_cancel_draft_entry_in_open_period_succeeds(client):
    env = await _bootstrap(client, f"JEC-Open-{unique_vat()[:6]}")
    headers = env["headers"]
    ar_id = await _account_id(client, headers, "1200")
    revenue_id = await _account_id(client, headers, "4100")

    entry_id = await _create_draft_entry(client, headers, entry_date="2026-01-15", ar_id=ar_id, revenue_id=revenue_id)

    cancel_resp = await client.post(f"/api/v1/accounting/journal-entries/{entry_id}:cancel", headers=headers)
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"


async def test_cancel_draft_entry_in_closed_period_succeeds(client):
    """The exact owner-reported scenario: period closed, draft entry
    created before the close, posting correctly rejected — cancel must
    still work because the draft never touched the ledger."""
    env = await _bootstrap(client, f"JEC-Closed-{unique_vat()[:6]}")
    headers = env["headers"]
    ar_id = await _account_id(client, headers, "1200")
    revenue_id = await _account_id(client, headers, "4100")

    period_resp = await client.post(
        "/api/v1/accounting/fiscal-periods",
        headers=headers,
        json={"period_start": "2026-01-01", "period_end": "2026-01-31"},
    )
    period_id = period_resp.json()["id"]

    entry_id = await _create_draft_entry(client, headers, entry_date="2026-01-15", ar_id=ar_id, revenue_id=revenue_id)

    await client.post(f"/api/v1/accounting/fiscal-periods/{period_id}:close", headers=headers)

    # Posting correctly stays rejected (period closed).
    post_resp = await client.post(f"/api/v1/accounting/journal-entries/{entry_id}:post", headers=headers)
    assert post_resp.status_code == 409

    # But cancelling the still-draft entry succeeds regardless.
    cancel_resp = await client.post(f"/api/v1/accounting/journal-entries/{entry_id}:cancel", headers=headers)
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"

    detail = await client.get(f"/api/v1/accounting/journal-entries/{entry_id}", headers=headers)
    assert detail.json()["entry"]["status"] == "cancelled"


async def test_cancelled_entry_cannot_subsequently_be_posted(client):
    env = await _bootstrap(client, f"JEC-NoPost-{unique_vat()[:6]}")
    headers = env["headers"]
    ar_id = await _account_id(client, headers, "1200")
    revenue_id = await _account_id(client, headers, "4100")

    entry_id = await _create_draft_entry(client, headers, entry_date="2026-02-15", ar_id=ar_id, revenue_id=revenue_id)
    await client.post(f"/api/v1/accounting/journal-entries/{entry_id}:cancel", headers=headers)

    post_resp = await client.post(f"/api/v1/accounting/journal-entries/{entry_id}:post", headers=headers)
    assert post_resp.status_code == 409


async def test_cannot_cancel_a_posted_entry(client):
    """Posted entries have a real ledger footprint — reverse is the correct
    tool, not cancel."""
    env = await _bootstrap(client, f"JEC-Posted-{unique_vat()[:6]}")
    headers = env["headers"]
    ar_id = await _account_id(client, headers, "1200")
    revenue_id = await _account_id(client, headers, "4100")

    entry_id = await _create_draft_entry(client, headers, entry_date="2026-02-15", ar_id=ar_id, revenue_id=revenue_id)
    post_resp = await client.post(f"/api/v1/accounting/journal-entries/{entry_id}:post", headers=headers)
    assert post_resp.status_code == 200

    cancel_resp = await client.post(f"/api/v1/accounting/journal-entries/{entry_id}:cancel", headers=headers)
    assert cancel_resp.status_code == 409

    detail = await client.get(f"/api/v1/accounting/journal-entries/{entry_id}", headers=headers)
    assert detail.json()["entry"]["status"] == "posted"


async def test_cannot_cancel_an_already_cancelled_entry(client):
    env = await _bootstrap(client, f"JEC-Twice-{unique_vat()[:6]}")
    headers = env["headers"]
    ar_id = await _account_id(client, headers, "1200")
    revenue_id = await _account_id(client, headers, "4100")

    entry_id = await _create_draft_entry(client, headers, entry_date="2026-02-15", ar_id=ar_id, revenue_id=revenue_id)
    first = await client.post(f"/api/v1/accounting/journal-entries/{entry_id}:cancel", headers=headers)
    assert first.status_code == 200

    second = await client.post(f"/api/v1/accounting/journal-entries/{entry_id}:cancel", headers=headers)
    assert second.status_code == 409


async def test_cancel_requires_permission(client):
    env = await _bootstrap(client, f"JEC-Perm-{unique_vat()[:6]}")
    headers = env["headers"]
    ar_id = await _account_id(client, headers, "1200")
    revenue_id = await _account_id(client, headers, "4100")
    limited = await _create_limited_user(client, headers, env["company_id"])

    entry_id = await _create_draft_entry(client, headers, entry_date="2026-02-15", ar_id=ar_id, revenue_id=revenue_id)

    forbidden = await client.post(
        f"/api/v1/accounting/journal-entries/{entry_id}:cancel", headers=limited["headers"]
    )
    assert forbidden.status_code == 403

    detail = await client.get(f"/api/v1/accounting/journal-entries/{entry_id}", headers=headers)
    assert detail.json()["entry"]["status"] == "draft"


async def test_cancel_company_isolation(client):
    company_a = await _bootstrap(client, f"JEC-IsoA-{unique_vat()[:6]}")
    company_b = await _bootstrap(client, f"JEC-IsoB-{unique_vat()[:6]}")
    ar_id = await _account_id(client, company_a["headers"], "1200")
    revenue_id = await _account_id(client, company_a["headers"], "4100")

    entry_id = await _create_draft_entry(
        client, company_a["headers"], entry_date="2026-02-15", ar_id=ar_id, revenue_id=revenue_id
    )

    cross_cancel = await client.post(
        f"/api/v1/accounting/journal-entries/{entry_id}:cancel", headers=company_b["headers"]
    )
    assert cross_cancel.status_code == 404

    detail = await client.get(f"/api/v1/accounting/journal-entries/{entry_id}", headers=company_a["headers"])
    assert detail.json()["entry"]["status"] == "draft"
