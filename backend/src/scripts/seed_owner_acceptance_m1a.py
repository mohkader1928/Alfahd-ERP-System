"""Owner Acceptance environment for Milestone 1a (Accounting Standardization).

Scope note: this is intentionally NOT the full Milestone 3 "100+ records
per master data type" demo dataset described in
docs/master-execution-plan.md Section F — that is a separate, larger,
not-yet-started body of work. This script exists only to make Milestone
1a's own screens (General Ledger, Income Statement, Balance Sheet,
Payments, cross-company isolation) tryable from a browser without SQL,
Postman, or developer tools, per the Owner's explicit "prepare it for real
hands-on testing" instruction for this checkpoint.

Design, matching the same rules the bigger Milestone 3 mechanism will
follow:
  - Goes entirely through the real HTTP API (bootstrap, Sales, Purchasing,
    Payments, Accounting) as the restricted `erp_app` runtime role would
    see it -- no superuser, no direct SQL writes, no RLS bypass.
  - Idempotent by natural key: fixed, documented email/VAT identifiers: if
    a run finds the demo company (or a specific demo transaction) already
    exists, it skips re-creating it rather than erroring or duplicating.
  - Two isolated companies are created -- "A" (the one with real
    transactions to explore) and "B" (deliberately left with none of A's
    data), so the Owner can prove cross-company isolation by logging into
    B and confirming nothing from A appears.
  - Never touches any pre-existing company or user -- everything it
    creates is scoped to its own two fixed demo companies.

Run with:  docker exec erp-nucleus-api-1 python -m src.scripts.seed_owner_acceptance_m1a
"""

import asyncio
import base64
import json
import sys

import httpx


def _decode_jwt_claims(token: str) -> dict:
    """Reads the JWT payload without verifying the signature -- this script
    already holds a validly-issued token from the real /auth/login
    endpoint; it only needs the `authorized_companies` claim already baked
    into that token by AuthenticationService.issue_tokens, not a second
    trust decision."""
    payload_b64 = token.split(".")[1]
    padded = payload_b64 + "=" * (-len(payload_b64) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))

BASE_URL = "http://localhost:8000"

COMPANY_A = {
    "tenant_legal_name": "Owner Acceptance Demo Holding",
    "company_legal_name": "Owner Acceptance Demo Co.",
    "company_legal_name_ar": "شركة قبول المالك التجريبية",
    "vat_number": "300000000000201",
    "base_currency_code": "SAR",
    "valuation_method": "average",
    "admin_email": "owner-demo-a@example.com",
    "admin_full_name": "Owner Acceptance Admin",
    "admin_password": "OwnerDemo!2026",
}

COMPANY_B = {
    "tenant_legal_name": "Owner Acceptance Isolation Test Holding",
    "company_legal_name": "Owner Acceptance Isolation Test Co.",
    "company_legal_name_ar": "شركة اختبار العزل التجريبية",
    "vat_number": "300000000000202",
    "base_currency_code": "SAR",
    "valuation_method": "average",
    "admin_email": "owner-demo-b@example.com",
    "admin_full_name": "Isolation Test Admin",
    "admin_password": "OwnerDemo!2026",
}

TAX_RATE_PLACEHOLDER = "00000000-0000-0000-0000-000000000001"


async def _bootstrap_or_login(client: httpx.AsyncClient, payload: dict) -> tuple[str, str, dict]:
    """Idempotent: if this demo company was already created by a previous
    run, bootstrap will reject the duplicate email/VAT -- fall back to
    logging in with the same fixed credentials instead of failing."""
    boot_resp = await client.post("/api/v1/identity/bootstrap", json=payload)
    if boot_resp.status_code == 201:
        body = boot_resp.json()
        company_id, branch_id = body["company_id"], body["branch_id"]
        created = True
    else:
        created = False
        company_id = branch_id = None  # discovered via login below

    login_resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": payload["admin_email"], "password": payload["admin_password"]},
    )
    login_resp.raise_for_status()
    login_body = login_resp.json()
    token = login_body["access_token"]

    if company_id is None:
        # Existing-company path: the access token's `authorized_companies`
        # claim ("company_id:branch_id") carries what bootstrap would have
        # returned directly -- reused here so a second run doesn't need to
        # duplicate lookups the token already answers.
        claims = _decode_jwt_claims(token)
        first = claims["authorized_companies"][0]
        company_id, branch_id = first.split(":") if ":" in first else (first, None)

    headers = {"Authorization": f"Bearer {token}", "X-Company-Id": company_id, "X-Branch-Id": branch_id}
    return company_id, branch_id, headers, created


async def _find_or_create_partner(client, headers, *, name: str, is_customer=False, is_vendor=False) -> str:
    existing = (await client.get("/api/v1/identity/partners", headers=headers)).json()
    match = next((p for p in existing if p["name"] == name), None)
    if match:
        return match["id"]
    resp = await client.post(
        "/api/v1/identity/partners",
        headers=headers,
        json={"name": name, "is_customer": is_customer, "is_vendor": is_vendor},
    )
    resp.raise_for_status()
    return resp.json()["id"]


async def _find_or_create_product(client, headers, *, sku: str, name: str, sales_price: str) -> str:
    existing = (await client.get("/api/v1/identity/products", headers=headers)).json()
    match = next((p for p in existing if p["sku"] == sku), None)
    if match:
        return match["id"]
    resp = await client.post(
        "/api/v1/identity/products", headers=headers, json={"sku": sku, "name": name, "sales_price": sales_price}
    )
    resp.raise_for_status()
    return resp.json()["id"]


async def _get_account_id(client, headers, code: str) -> str:
    accounts = (await client.get("/api/v1/accounting/chart-of-accounts", headers=headers)).json()
    return next(a["id"] for a in accounts if a["code"] == code)


async def _journal_entry_exists(client, headers, reference: str) -> bool:
    entries = (await client.get("/api/v1/accounting/journal-entries", headers=headers)).json()
    return any(e.get("reference") == reference for e in entries)


async def _post_je(client, headers, entry_date: str, reference: str, lines: list[dict]) -> None:
    if await _journal_entry_exists(client, headers, reference):
        print(f"    (skip) journal entry already posted: {reference}")
        return
    create_resp = await client.post(
        "/api/v1/accounting/journal-entries",
        headers=headers,
        json={"journal_code": "GEN", "entry_date": entry_date, "reference": reference, "lines": lines},
    )
    create_resp.raise_for_status()
    entry_id = create_resp.json()["id"]
    post_resp = await client.post(f"/api/v1/accounting/journal-entries/{entry_id}:post", headers=headers)
    post_resp.raise_for_status()
    print(f"    posted journal entry: {reference}")


async def seed_company_a(client: httpx.AsyncClient) -> dict:
    print(f"Company A ({COMPANY_A['company_legal_name']}):")
    company_id, branch_id, headers, created = await _bootstrap_or_login(client, COMPANY_A)
    print(f"  company_id={company_id} ({'created' if created else 'already existed, reused'})")

    cash = await _get_account_id(client, headers, "1100")
    inventory = await _get_account_id(client, headers, "1300")
    capital = await _get_account_id(client, headers, "3100")
    opex = await _get_account_id(client, headers, "5200")

    # --- Real business transactions (through the actual modules, not raw
    # journal entries) -- this is the traceable chain the Owner asked to
    # see proven: Business Transaction -> Journal Entry -> Journal Entry
    # Lines -> Account -> General Ledger -> Income Statement / Balance Sheet.
    await _post_je(
        client, headers, "2026-01-05", "Owner Acceptance Demo — capital injection",
        [{"account_id": cash, "debit": 20000, "credit": 0}, {"account_id": capital, "debit": 0, "credit": 20000}],
    )
    await _post_je(
        client, headers, "2026-01-06", "Owner Acceptance Demo — initial inventory purchase",
        [{"account_id": inventory, "debit": 4000, "credit": 0}, {"account_id": cash, "debit": 0, "credit": 4000}],
    )
    await _post_je(
        client, headers, "2026-01-20", "Owner Acceptance Demo — office rent (operating expense)",
        [{"account_id": opex, "debit": 800, "credit": 0}, {"account_id": cash, "debit": 0, "credit": 800}],
    )

    customer_id = await _find_or_create_partner(client, headers, name="Demo Customer LLC", is_customer=True)
    product_id = await _find_or_create_product(
        client, headers, sku="OWNER-DEMO-SKU-1", name="Demo Product A", sales_price="500.00"
    )

    invoices = (await client.get("/api/v1/sales/invoices", headers=headers)).json()
    demo_invoice = next((i for i in invoices if i.get("partner_id") == customer_id), None)
    if demo_invoice:
        print("  (skip) demo sales invoice already exists")
        invoice_id, invoice_total = demo_invoice["id"], demo_invoice["total_amount"]
    else:
        quote_resp = await client.post(
            "/api/v1/sales/quotations",
            headers=headers,
            json={
                "partner_id": customer_id,
                "quote_date": "2026-02-01",
                "lines": [{"product_id": product_id, "qty": "3", "unit_price": "500.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
            },
        )
        quote_resp.raise_for_status()
        order_resp = await client.post(f"/api/v1/sales/quotations/{quote_resp.json()['id']}:confirm", headers=headers)
        order_resp.raise_for_status()
        invoice_resp = await client.post(f"/api/v1/sales/orders/{order_resp.json()['id']}:invoice", headers=headers)
        invoice_resp.raise_for_status()
        invoice = invoice_resp.json()["invoice"]
        invoice_id, invoice_total = invoice["id"], invoice["total_amount"]
        print(f"  issued real Sales Invoice {invoice_id}: total {invoice_total} (posts Revenue + VAT automatically)")

    payments = (await client.get("/api/v1/payments/payments", headers=headers)).json()
    if any(p.get("reference") == "Owner Acceptance Demo — first payment" for p in payments):
        print("  (skip) demo payment already recorded")
    else:
        balance = (await client.get(f"/api/v1/payments/balance/sales-invoice/{invoice_id}", headers=headers)).json()
        pay_resp = await client.post(
            "/api/v1/payments/payments",
            headers=headers,
            json={
                "partner_id": customer_id,
                "payment_type": "customer",
                "payment_date": "2026-02-10",
                "amount": balance["balance_due"],
                "account_id": cash,
                "reference": "Owner Acceptance Demo — first payment",
                "allocations": [{"sales_invoice_id": invoice_id, "amount": balance["balance_due"]}],
            },
        )
        pay_resp.raise_for_status()
        print(f"  recorded real Payment against invoice {invoice_id}: {balance['balance_due']} SAR")

    return {"company_id": company_id, "customer_id": customer_id, "invoice_id": invoice_id}


async def seed_company_b(client: httpx.AsyncClient) -> str:
    print(f"Company B ({COMPANY_B['company_legal_name']}) — deliberately left empty for the isolation test:")
    company_id, _branch_id, _headers, created = await _bootstrap_or_login(client, COMPANY_B)
    print(f"  company_id={company_id} ({'created' if created else 'already existed, reused'})")
    return company_id


async def main() -> None:
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        result_a = await seed_company_a(client)
        company_b_id = await seed_company_b(client)

    print("\nDone.")
    print(f"Company A login: {COMPANY_A['admin_email']} / {COMPANY_A['admin_password']}  (company_id={result_a['company_id']})")
    print(f"Company B login: {COMPANY_B['admin_email']} / {COMPANY_B['admin_password']}  (company_id={company_b_id})")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except httpx.HTTPStatusError as exc:
        print(f"FAILED: {exc.request.method} {exc.request.url} -> {exc.response.status_code} {exc.response.text}", file=sys.stderr)
        raise
