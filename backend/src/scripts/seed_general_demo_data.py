"""General testing demo data — 10 records per master data type, 10
transactions per business module.

Deliberately a SEPARATE company from the Owner Acceptance environments
(seed_owner_acceptance_m1a.py's Companies A/B/C): those scripts' own
documentation (docs/owner-acceptance-m1a.md, docs/owner-acceptance-m1b.md)
quotes exact row counts and balances that a broader dataset would break.
This script exists purely so there is a realistically-populated company to
click around in -- not a replacement for those precise walkthroughs, and
not the full ~100-record Milestone 3 mechanism described in
docs/master-execution-plan.md Section F (that remains separate, larger,
not-yet-started work).

Same rules as every other seed script in this project:
  - Real HTTP API only (bootstrap, Identity, Sales, Purchasing, Inventory,
    Accounting, Payments) -- no direct SQL, no superuser, no RLS bypass.
  - Idempotent: safe to run more than once. Master data is looked up by
    name before creating. Transactional batches (invoices, bills,
    transfers, journal entries, payments) are skipped as a whole once at
    least 10 of that type already exist for this company, rather than
    doing fragile per-item duplicate detection for 10 similar records.
  - Scoped to its own dedicated company -- never touches any other
    company's data.

Run with:  docker exec erp-nucleus-api-1 python -m src.scripts.seed_general_demo_data
"""

import asyncio
import sys
from datetime import date

import httpx

BASE_URL = "http://localhost:8000"

COMPANY = {
    "tenant_legal_name": "General Demo Holding",
    "company_legal_name": "General Demo Trading Co.",
    "company_legal_name_ar": "شركة العرض التجريبي العام للتجارة",
    "vat_number": "300000000000401",
    "base_currency_code": "SAR",
    "valuation_method": "average",
    "admin_email": "demo-general@example.com",
    "admin_full_name": "General Demo Admin",
    "admin_password": "GeneralDemo!2026",
}

TAX_RATE_PLACEHOLDER = "00000000-0000-0000-0000-000000000001"

CATEGORIES = [
    "Electronics",
    "Office Supplies",
    "Furniture",
    "Food & Beverage",
    "Building Materials",
    "Textiles",
    "Packaging",
    "Tools & Hardware",
    "Cleaning Supplies",
    "Stationery",
]

# code, name
UOMS = [
    ("PCS", "Piece"),
    ("BOX", "Box"),
    ("KG", "Kilogram"),
    ("LTR", "Liter"),
    ("MTR", "Meter"),
    ("CTN", "Carton"),
    ("PLT", "Pallet"),
    ("DZN", "Dozen"),
    ("ROL", "Roll"),
    ("SET", "Set"),
]

CUSTOMERS = [
    "Al-Faisal Trading Co.",
    "Riyadh Modern Furniture LLC",
    "Jeddah Fresh Foods Est.",
    "Dammam Electronics Hub",
    "Al-Khobar Office Solutions",
    "Makkah Building Supplies Co.",
    "Madinah Textile Trading",
    "Eastern Province Hardware LLC",
    "Tabuk Packaging Industries",
    "Abha Stationery & Supplies",
]

VENDORS = [
    "Gulf Steel Manufacturing Co.",
    "Saudi Paper Products Ltd.",
    "National Plastics Industries",
    "Al-Rajhi Building Materials",
    "Red Sea Textiles Mills",
    "Riyadh Electronics Distributors",
    "Jazan Food Processing Co.",
    "Qassim Furniture Factory",
    "Yanbu Chemical Supplies",
    "Al-Hasa Agricultural Equipment",
]

# sku, name, category, uom_code, sales_price, cost_price
PRODUCTS = [
    ("GD-001", "Laptop Stand", "Electronics", "PCS", "150.00", "90.00"),
    ("GD-002", "A4 Paper Ream", "Office Supplies", "BOX", "25.00", "15.00"),
    ("GD-003", "Office Desk", "Furniture", "PCS", "800.00", "500.00"),
    ("GD-004", "Bottled Water 500ml (Case)", "Food & Beverage", "CTN", "30.00", "18.00"),
    ("GD-005", "Cement Bag 50kg", "Building Materials", "PCS", "20.00", "12.00"),
    ("GD-006", "Cotton Fabric Roll", "Textiles", "ROL", "120.00", "70.00"),
    ("GD-007", "Cardboard Box (Large)", "Packaging", "PCS", "5.00", "3.00"),
    ("GD-008", "Hammer Set", "Tools & Hardware", "SET", "90.00", "55.00"),
    ("GD-009", "Multi-Surface Cleaner", "Cleaning Supplies", "LTR", "15.00", "8.00"),
    ("GD-010", "Ballpoint Pen (Dozen)", "Stationery", "DZN", "12.00", "6.00"),
]


async def _bootstrap_or_login(client: httpx.AsyncClient) -> tuple[str, str, dict]:
    boot_resp = await client.post("/api/v1/identity/bootstrap", json=COMPANY)
    if boot_resp.status_code == 201:
        body = boot_resp.json()
        company_id, branch_id = body["company_id"], body["branch_id"]
    else:
        company_id = branch_id = None

    login_resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": COMPANY["admin_email"], "password": COMPANY["admin_password"]},
    )
    login_resp.raise_for_status()
    token = login_resp.json()["access_token"]

    if company_id is None:
        import base64
        import json as _json

        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        claims = _json.loads(base64.urlsafe_b64decode(payload_b64))
        first = claims["authorized_companies"][0]
        company_id, branch_id = first.split(":") if ":" in first else (first, None)

    headers = {
        "Authorization": f"Bearer {token}",
        "X-Company-Id": company_id,
        "X-Branch-Id": branch_id,
    }
    return company_id, branch_id, headers


async def _seed_categories(client, headers) -> dict:
    existing = (await client.get("/api/v1/identity/product-categories", headers=headers)).json()
    by_name = {c["name"]: c["id"] for c in existing}
    for name in CATEGORIES:
        if name in by_name:
            continue
        resp = await client.post(
            "/api/v1/identity/product-categories", headers=headers, json={"name": name}
        )
        resp.raise_for_status()
        by_name[name] = resp.json()["id"]
    print(f"  Categories: {len(by_name)} present (target {len(CATEGORIES)})")
    return by_name


async def _seed_uoms(client, headers) -> dict:
    existing = (await client.get("/api/v1/identity/uom", headers=headers)).json()
    by_code = {u["code"]: u["id"] for u in existing}
    for code, name in UOMS:
        if code in by_code:
            continue
        resp = await client.post(
            "/api/v1/identity/uom", headers=headers, json={"code": code, "name": name}
        )
        resp.raise_for_status()
        by_code[code] = resp.json()["id"]
    print(f"  Units of measure: {len(by_code)} present (target {len(UOMS)})")
    return by_code


async def _seed_partners(
    client, headers, names: list[str], *, is_customer: bool, is_vendor: bool
) -> dict:
    existing = (await client.get("/api/v1/identity/partners", headers=headers)).json()
    by_name = {p["name"]: p["id"] for p in existing}
    for name in names:
        if name in by_name:
            continue
        resp = await client.post(
            "/api/v1/identity/partners",
            headers=headers,
            json={"name": name, "is_customer": is_customer, "is_vendor": is_vendor},
        )
        resp.raise_for_status()
        by_name[name] = resp.json()["id"]
    return {name: by_name[name] for name in names}


async def _seed_products(client, headers, categories: dict, uoms: dict) -> dict:
    existing = (await client.get("/api/v1/identity/products", headers=headers)).json()
    by_sku = {p["sku"]: p["id"] for p in existing}
    for sku, name, category, uom_code, sales_price, cost_price in PRODUCTS:
        if sku in by_sku:
            continue
        resp = await client.post(
            "/api/v1/identity/products",
            headers=headers,
            json={
                "sku": sku,
                "name": name,
                "category_id": categories.get(category),
                "uom_id": uoms.get(uom_code),
                "sales_price": sales_price,
                "cost_price": cost_price,
            },
        )
        resp.raise_for_status()
        by_sku[sku] = resp.json()["id"]
    print(f"  Products: {len(by_sku)} present (target {len(PRODUCTS)})")
    return {sku: by_sku[sku] for sku, *_ in PRODUCTS}


async def _ensure_warehouses(client, headers) -> tuple[str, str]:
    """Returns (main_location_id, secondary_location_id). A fresh company
    has no default warehouse (see docs/17f-subledgers-and-aging.md /
    test_payments_subledger_m1b_smoke.py for the same, already-documented
    gap) -- created explicitly here, the same real step a user takes from
    the Inventory screen."""
    existing = (await client.get("/api/v1/inventory/warehouses", headers=headers)).json()
    main = next((w for w in existing if w["name"] == "Main Warehouse"), None)
    secondary = next((w for w in existing if w["name"] == "Secondary Warehouse"), None)

    if main is None:
        resp = await client.post(
            "/api/v1/inventory/warehouses",
            headers=headers,
            json={"name": "Main Warehouse", "is_default": True},
        )
        resp.raise_for_status()
        body = resp.json()
        main_id, main_location_id = body["warehouse"]["id"], body["default_location"]["id"]
    else:
        main_id = main["id"]
        locations = (
            await client.get(f"/api/v1/inventory/warehouses/{main_id}/locations", headers=headers)
        ).json()
        main_location_id = locations[0]["id"]

    if secondary is None:
        resp = await client.post(
            "/api/v1/inventory/warehouses",
            headers=headers,
            json={"name": "Secondary Warehouse", "is_default": False},
        )
        resp.raise_for_status()
        body = resp.json()
        secondary_location_id = body["default_location"]["id"]
    else:
        locations = (
            await client.get(
                f"/api/v1/inventory/warehouses/{secondary['id']}/locations", headers=headers
            )
        ).json()
        secondary_location_id = locations[0]["id"]

    return main_location_id, secondary_location_id


async def _seed_sales_invoices(client, headers, customers: dict, products: dict) -> None:
    invoices = (await client.get("/api/v1/sales/invoices", headers=headers)).json()
    real_invoices = [i for i in invoices if i["invoice_type"] != "credit_note"]
    if len(real_invoices) >= 10:
        print(f"  Sales invoices: {len(real_invoices)} already present (skip)")
        return

    product_ids = list(products.values())
    customer_ids = list(customers.values())
    created = 0
    for i in range(10):
        customer_id = customer_ids[i]
        product_id = product_ids[i % len(product_ids)]
        qty = str(2 + (i % 4))
        quote_resp = await client.post(
            "/api/v1/sales/quotations",
            headers=headers,
            json={
                "partner_id": customer_id,
                "quote_date": str(date.today()),
                "lines": [
                    {
                        "product_id": product_id,
                        "qty": qty,
                        "unit_price": PRODUCTS[i % len(PRODUCTS)][4],
                        "tax_rate_id": TAX_RATE_PLACEHOLDER,
                    }
                ],
            },
        )
        quote_resp.raise_for_status()
        order_resp = await client.post(
            f"/api/v1/sales/quotations/{quote_resp.json()['id']}:confirm", headers=headers
        )
        order_resp.raise_for_status()
        invoice_resp = await client.post(
            f"/api/v1/sales/orders/{order_resp.json()['id']}:invoice", headers=headers
        )
        invoice_resp.raise_for_status()
        invoice = invoice_resp.json()["invoice"]

        # Vary settlement state: every 3rd invoice fully paid, every 4th
        # left unpaid, one credit-noted, the rest partially paid -- so
        # Subledgers/Aging/Statements all have something real to show.
        if i % 4 == 3:
            pass  # left unpaid
        elif i == 9:
            await client.post(
                f"/api/v1/sales/invoices/{invoice['id']}:credit-note",
                headers=headers,
                json={"reason": "Demo return"},
            )
        else:
            cash_accounts = (
                await client.get("/api/v1/accounting/chart-of-accounts", headers=headers)
            ).json()
            cash_id = next(a["id"] for a in cash_accounts if a["code"] == "1100")
            balance = (
                await client.get(
                    f"/api/v1/payments/balance/sales-invoice/{invoice['id']}", headers=headers
                )
            ).json()
            amount = (
                balance["balance_due"]
                if i % 3 == 0
                else str(round(float(balance["balance_due"]) / 2, 2))
            )
            await client.post(
                "/api/v1/payments/payments",
                headers=headers,
                json={
                    "partner_id": customer_id,
                    "payment_type": "customer",
                    "payment_date": str(date.today()),
                    "amount": amount,
                    "account_id": cash_id,
                    "reference": f"General Demo — customer payment {i + 1}",
                    "allocations": [{"sales_invoice_id": invoice["id"], "amount": amount}],
                },
            )
        created += 1
    print(f"  Sales invoices: created {created} (mixed paid/partial/unpaid/credit-noted)")


async def _seed_vendor_bills(
    client, headers, vendors: dict, products: dict, main_location_id: str
) -> None:
    bills = (await client.get("/api/v1/purchasing/vendor-bills", headers=headers)).json()
    if len(bills) >= 10:
        print(f"  Vendor bills: {len(bills)} already present (skip)")
        return

    product_ids = list(products.values())
    vendor_ids = list(vendors.values())
    cash_accounts = (
        await client.get("/api/v1/accounting/chart-of-accounts", headers=headers)
    ).json()
    cash_id = next(a["id"] for a in cash_accounts if a["code"] == "1100")
    created = 0
    for i in range(10):
        vendor_id = vendor_ids[i]
        product_id = product_ids[i % len(product_ids)]
        qty = str(5 + (i % 6))
        unit_price = PRODUCTS[i % len(PRODUCTS)][5]  # cost price
        po_resp = await client.post(
            "/api/v1/purchasing/orders",
            headers=headers,
            json={
                "partner_id": vendor_id,
                "order_date": str(date.today()),
                "lines": [
                    {
                        "product_id": product_id,
                        "qty": qty,
                        "unit_price": unit_price,
                        "tax_rate_id": TAX_RATE_PLACEHOLDER,
                    }
                ],
            },
        )
        po_resp.raise_for_status()
        po_id = po_resp.json()["id"]
        (
            await client.post(f"/api/v1/purchasing/orders/{po_id}:confirm", headers=headers)
        ).raise_for_status()
        po_detail = (await client.get(f"/api/v1/purchasing/orders/{po_id}", headers=headers)).json()
        po_line_id = po_detail["lines"][0]["id"]
        (
            await client.post(
                f"/api/v1/purchasing/orders/{po_id}/goods-receipts",
                headers=headers,
                json={"lines": [{"purchase_order_line_id": po_line_id, "qty": qty}]},
            )
        ).raise_for_status()
        bill_resp = await client.post(
            f"/api/v1/purchasing/orders/{po_id}/vendor-bills",
            headers=headers,
            json={
                "lines": [
                    {"purchase_order_line_id": po_line_id, "qty": qty, "unit_price": unit_price}
                ]
            },
        )
        bill_resp.raise_for_status()
        approve_resp = await client.post(
            f"/api/v1/purchasing/vendor-bills/{bill_resp.json()['id']}:approve", headers=headers
        )
        approve_resp.raise_for_status()
        bill = approve_resp.json()

        if i % 4 != 3:  # leave every 4th bill unpaid, pay the rest
            vbalance = (
                await client.get(
                    f"/api/v1/payments/balance/vendor-bill/{bill['id']}", headers=headers
                )
            ).json()
            amount = (
                vbalance["balance_due"]
                if i % 3 != 1
                else str(round(float(vbalance["balance_due"]) / 2, 2))
            )
            await client.post(
                "/api/v1/payments/payments",
                headers=headers,
                json={
                    "partner_id": vendor_id,
                    "payment_type": "vendor",
                    "payment_date": str(date.today()),
                    "amount": amount,
                    "account_id": cash_id,
                    "reference": f"General Demo — vendor payment {i + 1}",
                    "allocations": [{"vendor_bill_id": bill["id"], "amount": amount}],
                },
            )
        created += 1
    print(
        f"  Vendor bills: created {created} (mixed paid/partial/unpaid), goods received into Main Warehouse"
    )


async def _seed_transfers(
    client, headers, products: dict, main_location_id: str, secondary_location_id: str
) -> None:
    moves = (await client.get("/api/v1/inventory/stock/moves", headers=headers)).json()
    transfer_moves = [m for m in moves if m.get("move_type") == "transfer"]
    if len(transfer_moves) >= 10:
        print(f"  Inventory transfers: {len(transfer_moves)} already present (skip)")
        return

    product_ids = list(products.values())
    created = 0
    for i in range(10):
        product_id = product_ids[i % len(product_ids)]
        resp = await client.post(
            "/api/v1/inventory/transfers",
            headers=headers,
            json={
                "product_id": product_id,
                "source_location_id": main_location_id,
                "dest_location_id": secondary_location_id,
                "qty": "1",
            },
        )
        if resp.status_code == 201:
            created += 1
        # Insufficient stock for a product not yet received is possible if
        # ordering shifted between runs -- non-fatal, just move to the next.
    print(f"  Inventory transfers: created {created} (Main -> Secondary Warehouse)")


async def _seed_journal_entries(client, headers) -> None:
    entries = (await client.get("/api/v1/accounting/journal-entries", headers=headers)).json()
    demo_entries = [e for e in entries if e.get("reference", "").startswith("General Demo — JE")]
    if len(demo_entries) >= 10:
        print(f"  Journal entries: {len(demo_entries)} already present (skip)")
        return

    accounts = (await client.get("/api/v1/accounting/chart-of-accounts", headers=headers)).json()
    cash_id = next(a["id"] for a in accounts if a["code"] == "1100")
    opex_id = next(a["id"] for a in accounts if a["code"] == "5200")
    capital_id = next(a["id"] for a in accounts if a["code"] == "3100")

    # (description, debit_account, credit_account, amount)
    entries_spec = [
        ("Owner capital top-up", cash_id, capital_id, "5000.00"),
        ("Office rent", opex_id, cash_id, "1200.00"),
        ("Electricity bill", opex_id, cash_id, "350.00"),
        ("Water bill", opex_id, cash_id, "80.00"),
        ("Internet & phone", opex_id, cash_id, "220.00"),
        ("Office supplies purchase", opex_id, cash_id, "150.00"),
        ("Vehicle fuel", opex_id, cash_id, "300.00"),
        ("Bank service charge", opex_id, cash_id, "45.00"),
        ("Marketing expense", opex_id, cash_id, "600.00"),
        ("Cleaning service", opex_id, cash_id, "180.00"),
    ]
    created = 0
    for idx, (description, debit_account, credit_account, amount) in enumerate(
        entries_spec, start=1
    ):
        reference = f"General Demo — JE {idx}: {description}"
        create_resp = await client.post(
            "/api/v1/accounting/journal-entries",
            headers=headers,
            json={
                "journal_code": "GEN",
                "entry_date": str(date.today()),
                "reference": reference,
                "lines": [
                    {"account_id": debit_account, "debit": amount, "credit": 0},
                    {"account_id": credit_account, "debit": 0, "credit": amount},
                ],
            },
        )
        create_resp.raise_for_status()
        entry_id = create_resp.json()["id"]
        (
            await client.post(
                f"/api/v1/accounting/journal-entries/{entry_id}:post", headers=headers
            )
        ).raise_for_status()
        created += 1
    print(f"  Journal entries: created {created}")


async def seed(client: httpx.AsyncClient) -> str:
    print(f"Company ({COMPANY['company_legal_name']}):")
    company_id, branch_id, headers = await _bootstrap_or_login(client)
    print(f"  company_id={company_id}")

    categories = await _seed_categories(client, headers)
    uoms = await _seed_uoms(client, headers)
    customers = await _seed_partners(client, headers, CUSTOMERS, is_customer=True, is_vendor=False)
    print(f"  Customers: {len(customers)} present (target {len(CUSTOMERS)})")
    vendors = await _seed_partners(client, headers, VENDORS, is_customer=False, is_vendor=True)
    print(f"  Vendors: {len(vendors)} present (target {len(VENDORS)})")
    products = await _seed_products(client, headers, categories, uoms)
    main_location_id, secondary_location_id = await _ensure_warehouses(client, headers)

    # Vendor bills first -- they receive stock into Main Warehouse, which
    # the inventory transfers below need in order to have something to move.
    await _seed_vendor_bills(client, headers, vendors, products, main_location_id)
    await _seed_sales_invoices(client, headers, customers, products)
    await _seed_transfers(client, headers, products, main_location_id, secondary_location_id)
    await _seed_journal_entries(client, headers)

    return company_id


async def main() -> None:
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=60) as client:
        company_id = await seed(client)

    print("\nDone.")
    print(
        f"Login: {COMPANY['admin_email']} / {COMPANY['admin_password']}  (company_id={company_id})"
    )
    print(
        "Payments (customer + vendor combined) satisfy the '10 transactions in the Payments module' target too."
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except httpx.HTTPStatusError as exc:
        print(
            f"FAILED: {exc.request.method} {exc.request.url} -> {exc.response.status_code} {exc.response.text}",
            file=sys.stderr,
        )
        raise
