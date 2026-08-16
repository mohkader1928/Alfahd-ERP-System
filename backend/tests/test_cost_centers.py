"""Standard SME ERP Phase 1 — Cost Centers.

CostCenter has existed as a schema-only placeholder since the M1
Accounting migration (name, company_id, and a real
journal_entry_line.cost_center_id FK, already RLS'd under
company_isolation since 461205cf56a6) with zero management surface.
This proves the real, non-destructively-archivable capability: create,
list, get, update, archive/reactivate, company isolation, RBAC, audit
trail, real accounting-transaction association (with company-ownership
and active-status validation that never existed before), and that
archiving never orphans existing journal entry history.
"""

from tests.conftest import unique_email, unique_vat


async def _bootstrap_and_login(client, label="CC"):
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
    assert boot_resp.status_code == 201, boot_resp.text
    company_id = boot_resp.json()["company_id"]
    tenant_id = boot_resp.json()["tenant_id"]

    login_resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": payload["admin_email"], "password": payload["admin_password"]},
    )
    assert login_resp.status_code == 200, login_resp.text
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Company-Id": company_id}
    return tenant_id, company_id, headers


async def _get_account_id(client, headers, code: str) -> str:
    resp = await client.get("/api/v1/accounting/chart-of-accounts", headers=headers)
    return next(a["id"] for a in resp.json() if a["code"] == code)


async def _create_cost_center(client, headers, name="Marketing", name_ar="التسويق") -> dict:
    resp = await client.post(
        "/api/v1/accounting/cost-centers", headers=headers, json={"name": name, "name_ar": name_ar}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# --- 1. Create -------------------------------------------------------------


async def test_create_cost_center(client):
    _, _, headers = await _bootstrap_and_login(client, "Create")
    cc = await _create_cost_center(client, headers, "Warehouse Ops", "عمليات المستودع")
    assert cc["name"] == "Warehouse Ops"
    assert cc["name_ar"] == "عمليات المستودع"
    assert cc["is_active"] is True


async def test_create_cost_center_rejects_duplicate_name(client):
    _, _, headers = await _bootstrap_and_login(client, "Dup")
    await _create_cost_center(client, headers, "Sales Region A")
    resp = await client.post(
        "/api/v1/accounting/cost-centers", headers=headers, json={"name": "Sales Region A"}
    )
    assert resp.status_code == 422


async def test_create_cost_center_rejects_blank_name(client):
    _, _, headers = await _bootstrap_and_login(client, "Blank")
    resp = await client.post("/api/v1/accounting/cost-centers", headers=headers, json={"name": "   "})
    assert resp.status_code == 422


# --- 2. Read -----------------------------------------------------------------


async def test_list_cost_centers(client):
    _, _, headers = await _bootstrap_and_login(client, "List")
    await _create_cost_center(client, headers, "A")
    await _create_cost_center(client, headers, "B")
    resp = await client.get("/api/v1/accounting/cost-centers", headers=headers)
    assert resp.status_code == 200
    names = {c["name"] for c in resp.json()}
    assert {"A", "B"}.issubset(names)


async def test_get_cost_center_by_id(client):
    _, _, headers = await _bootstrap_and_login(client, "GetById")
    cc = await _create_cost_center(client, headers, "Finance")
    resp = await client.get(f"/api/v1/accounting/cost-centers/{cc['id']}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == cc["id"]


async def test_get_unknown_cost_center_404(client):
    _, _, headers = await _bootstrap_and_login(client, "GetUnknown")
    resp = await client.get(
        "/api/v1/accounting/cost-centers/00000000-0000-0000-0000-000000000099", headers=headers
    )
    assert resp.status_code == 404


# --- 3. Update ---------------------------------------------------------------


async def test_update_cost_center_name(client):
    _, _, headers = await _bootstrap_and_login(client, "Rename")
    cc = await _create_cost_center(client, headers, "Old Name")
    resp = await client.patch(
        f"/api/v1/accounting/cost-centers/{cc['id']}", headers=headers, json={"name": "New Name"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "New Name"


# --- 4. Archive / reactivate (never destructive delete) ---------------------


async def test_archive_and_reactivate_cost_center(client):
    _, _, headers = await _bootstrap_and_login(client, "Archive")
    cc = await _create_cost_center(client, headers, "Temp Project")

    archive_resp = await client.patch(
        f"/api/v1/accounting/cost-centers/{cc['id']}", headers=headers, json={"is_active": False}
    )
    assert archive_resp.status_code == 200
    assert archive_resp.json()["is_active"] is False

    # Still fully readable -- archiving is not a delete.
    get_resp = await client.get(f"/api/v1/accounting/cost-centers/{cc['id']}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "Temp Project"

    reactivate_resp = await client.patch(
        f"/api/v1/accounting/cost-centers/{cc['id']}", headers=headers, json={"is_active": True}
    )
    assert reactivate_resp.status_code == 200
    assert reactivate_resp.json()["is_active"] is True


async def test_no_delete_endpoint_exists_for_cost_centers(client):
    """Explicit product requirement: never a destructive DELETE."""
    _, _, headers = await _bootstrap_and_login(client, "NoDelete")
    cc = await _create_cost_center(client, headers)
    resp = await client.delete(f"/api/v1/accounting/cost-centers/{cc['id']}", headers=headers)
    assert resp.status_code == 405


# --- 5. RBAC -------------------------------------------------------------------


async def test_unauthorized_access_rejected(client):
    _, company_id, headers = await _bootstrap_and_login(client, "Unauth")
    cc = await _create_cost_center(client, headers)
    no_auth_headers = {"X-Company-Id": company_id}
    assert (await client.get("/api/v1/accounting/cost-centers", headers=no_auth_headers)).status_code == 401
    assert (
        await client.post("/api/v1/accounting/cost-centers", headers=no_auth_headers, json={"name": "X"})
    ).status_code == 401
    assert (
        await client.patch(
            f"/api/v1/accounting/cost-centers/{cc['id']}", headers=no_auth_headers, json={"name": "Y"}
        )
    ).status_code == 401


# --- 6. Company isolation ----------------------------------------------------


async def test_cross_company_read_rejected(client):
    _, _, headers_a = await _bootstrap_and_login(client, "IsoA")
    _, company_b, headers_b = await _bootstrap_and_login(client, "IsoB")
    cc_a = await _create_cost_center(client, headers_a, "Company A Only")

    resp = await client.get(f"/api/v1/accounting/cost-centers/{cc_a['id']}", headers=headers_b)
    assert resp.status_code == 404

    list_resp = await client.get("/api/v1/accounting/cost-centers", headers=headers_b)
    assert cc_a["id"] not in {c["id"] for c in list_resp.json()}
    assert company_b != cc_a["company_id"]


async def test_cross_company_update_rejected(client):
    _, _, headers_a = await _bootstrap_and_login(client, "IsoUpdA")
    _, _, headers_b = await _bootstrap_and_login(client, "IsoUpdB")
    cc_a = await _create_cost_center(client, headers_a)

    resp = await client.patch(
        f"/api/v1/accounting/cost-centers/{cc_a['id']}", headers=headers_b, json={"name": "Hijacked"}
    )
    assert resp.status_code == 404


async def test_rls_isolation_at_db_level(client):
    """Direct DB proof (not just API-level 404) that company_isolation RLS
    genuinely blocks cross-company visibility, mirroring the style of
    tests/test_multi_tenancy_isolation.py."""
    from sqlalchemy import select

    from src.modules.accounting.infrastructure.models import CostCenter
    from src.shared.infrastructure.db.session import AsyncSessionLocal, set_company_context

    _, company_a, headers_a = await _bootstrap_and_login(client, "RlsA")
    _, company_b, headers_b = await _bootstrap_and_login(client, "RlsB")
    await _create_cost_center(client, headers_a, "RLS Secret")

    async with AsyncSessionLocal() as session:
        await set_company_context(session, company_b)
        result = await session.execute(select(CostCenter).where(CostCenter.name == "RLS Secret"))
        assert result.scalar_one_or_none() is None

    async with AsyncSessionLocal() as session:
        await set_company_context(session, company_a)
        result = await session.execute(select(CostCenter).where(CostCenter.name == "RLS Secret"))
        assert result.scalar_one_or_none() is not None


# --- 7. Accounting integration ------------------------------------------------


async def test_journal_entry_line_accepts_valid_cost_center(client):
    _, _, headers = await _bootstrap_and_login(client, "JeValid")
    cash_id = await _get_account_id(client, headers, "1100")
    capital_id = await _get_account_id(client, headers, "3100")
    cc = await _create_cost_center(client, headers, "Store 1")

    resp = await client.post(
        "/api/v1/accounting/journal-entries",
        headers=headers,
        json={
            "journal_code": "GEN",
            "entry_date": "2026-02-01",
            "lines": [
                {"account_id": cash_id, "debit": 500, "credit": 0, "cost_center_id": cc["id"]},
                {"account_id": capital_id, "debit": 0, "credit": 500},
            ],
        },
    )
    assert resp.status_code == 201, resp.text
    entry_id = resp.json()["id"]

    detail = await client.get(f"/api/v1/accounting/journal-entries/{entry_id}", headers=headers)
    lines = detail.json()["lines"]
    cash_line = next(line_ for line_ in lines if line_["account_id"] == cash_id)
    assert cash_line["cost_center_id"] == cc["id"]


async def test_journal_entry_line_rejects_cross_company_cost_center(client):
    _, _, headers_a = await _bootstrap_and_login(client, "JeIsoA")
    _, _, headers_b = await _bootstrap_and_login(client, "JeIsoB")
    cc_b = await _create_cost_center(client, headers_b, "Belongs To B")

    cash_id = await _get_account_id(client, headers_a, "1100")
    capital_id = await _get_account_id(client, headers_a, "3100")

    resp = await client.post(
        "/api/v1/accounting/journal-entries",
        headers=headers_a,
        json={
            "journal_code": "GEN",
            "entry_date": "2026-02-01",
            "lines": [
                {"account_id": cash_id, "debit": 100, "credit": 0, "cost_center_id": cc_b["id"]},
                {"account_id": capital_id, "debit": 0, "credit": 100},
            ],
        },
    )
    assert resp.status_code == 422
    assert "not found in this company" in resp.json()["detail"]


async def test_journal_entry_line_rejects_archived_cost_center(client):
    _, _, headers = await _bootstrap_and_login(client, "JeArchived")
    cash_id = await _get_account_id(client, headers, "1100")
    capital_id = await _get_account_id(client, headers, "3100")
    cc = await _create_cost_center(client, headers, "Closing Down")
    await client.patch(
        f"/api/v1/accounting/cost-centers/{cc['id']}", headers=headers, json={"is_active": False}
    )

    resp = await client.post(
        "/api/v1/accounting/journal-entries",
        headers=headers,
        json={
            "journal_code": "GEN",
            "entry_date": "2026-02-01",
            "lines": [
                {"account_id": cash_id, "debit": 100, "credit": 0, "cost_center_id": cc["id"]},
                {"account_id": capital_id, "debit": 0, "credit": 100},
            ],
        },
    )
    assert resp.status_code == 422
    assert "archived" in resp.json()["detail"]


async def test_archiving_cost_center_preserves_existing_journal_entry_history(client):
    """Archiving must never orphan or hide a real, already-posted line's
    cost center reference -- only block it from being picked again."""
    _, _, headers = await _bootstrap_and_login(client, "JeHistory")
    cash_id = await _get_account_id(client, headers, "1100")
    capital_id = await _get_account_id(client, headers, "3100")
    cc = await _create_cost_center(client, headers, "Legacy Branch")

    create_resp = await client.post(
        "/api/v1/accounting/journal-entries",
        headers=headers,
        json={
            "journal_code": "GEN",
            "entry_date": "2026-02-01",
            "lines": [
                {"account_id": cash_id, "debit": 250, "credit": 0, "cost_center_id": cc["id"]},
                {"account_id": capital_id, "debit": 0, "credit": 250},
            ],
        },
    )
    entry_id = create_resp.json()["id"]

    await client.patch(
        f"/api/v1/accounting/cost-centers/{cc['id']}", headers=headers, json={"is_active": False}
    )

    detail = await client.get(f"/api/v1/accounting/journal-entries/{entry_id}", headers=headers)
    lines = detail.json()["lines"]
    cash_line = next(line_ for line_ in lines if line_["account_id"] == cash_id)
    assert cash_line["cost_center_id"] == cc["id"]  # still there, untouched


async def test_journal_entries_without_cost_center_unaffected(client):
    """Regression: existing accounting workflows (no cost center at all)
    must keep working exactly as before this stage."""
    _, _, headers = await _bootstrap_and_login(client, "NoCcRegression")
    cash_id = await _get_account_id(client, headers, "1100")
    capital_id = await _get_account_id(client, headers, "3100")

    resp = await client.post(
        "/api/v1/accounting/journal-entries",
        headers=headers,
        json={
            "journal_code": "GEN",
            "entry_date": "2026-02-01",
            "lines": [
                {"account_id": cash_id, "debit": 300, "credit": 0},
                {"account_id": capital_id, "debit": 0, "credit": 300},
            ],
        },
    )
    assert resp.status_code == 201, resp.text
    assert (
        await client.post(f"/api/v1/accounting/journal-entries/{resp.json()['id']}:post", headers=headers)
    ).status_code == 200


# --- 8. Audit trail ------------------------------------------------------------


async def test_audit_trail_for_create_and_archive(client):
    from sqlalchemy import text as sql_text

    from src.shared.infrastructure.db.session import AsyncSessionLocal, set_tenant_context

    tenant_id, company_id, headers = await _bootstrap_and_login(client, "Audit")
    cc = await _create_cost_center(client, headers, "Audited CC")
    await client.patch(
        f"/api/v1/accounting/cost-centers/{cc['id']}", headers=headers, json={"is_active": False}
    )

    async with AsyncSessionLocal() as session:
        await set_tenant_context(session, tenant_id)
        result = await session.execute(
            sql_text(
                "SELECT field_name, old_value, new_value, user_id FROM audit_log "
                "WHERE target_table = 'cost_center' AND target_id = :cc_id ORDER BY changed_at"
            ),
            {"cc_id": cc["id"]},
        )
        rows = result.all()

    fields = [r.field_name for r in rows]
    assert "name" in fields  # creation
    assert "is_active" in fields  # archive
    assert all(r.user_id is not None for r in rows)
    is_active_row = next(r for r in rows if r.field_name == "is_active")
    assert is_active_row.old_value == "True"
    assert is_active_row.new_value == "False"
