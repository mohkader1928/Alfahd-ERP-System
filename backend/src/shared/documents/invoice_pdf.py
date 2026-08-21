"""Sales Invoice PDF — Document Delivery (Product Owner audit finding: this
system had zero PDF for the actual sales invoice document; the Standard
Reporting Framework only ever covered tabular reports, not a real business
document layout). Same WeasyPrint HTML/CSS -> PDF technique as
`shared/reporting/export_render.py` (correct Arabic bidi/glyph-joining via
Pango, no hand-rolled canvas rendering) — a single-document layout instead
of a table: letterhead, bill-to block, line items, totals, and the
ZATCA Phase-1 QR code (same TLV payload the on-screen invoice page already
renders via `react-qr-code` — `qrcode` regenerates the identical image
server-side for the PDF/email copy).
"""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from html import escape as h
from pathlib import Path

import qrcode
from weasyprint import HTML

from src.shared.config.settings import get_settings
from src.shared.documents.signature_footer import SIGNATURE_FOOTER_CSS, render_signature_footer_html


@dataclass(frozen=True)
class InvoiceLineRow:
    description: str
    qty: Decimal
    unit_price: Decimal
    tax_rate_percent: Decimal
    line_total: Decimal
    tax_amount: Decimal


@dataclass(frozen=True)
class InvoiceDocument:
    number: str
    invoice_date: date
    due_date: date | None
    invoice_type: str
    subtotal_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    lines: list[InvoiceLineRow]
    company_name: str
    company_name_ar: str
    company_vat_number: str
    company_logo_path: str | None
    partner_name: str
    partner_vat_number: str | None
    qr_payload: str | None
    warehouse_name: str | None = None
    lang: str = "ar"


def _logo_data_uri(logo_path: str | None) -> str | None:
    if not logo_path:
        return None
    settings = get_settings()
    path = Path(settings.media_root) / logo_path
    if not path.is_file():
        return None
    ext = path.suffix.lstrip(".").lower() or "png"
    mime = "jpeg" if ext == "jpg" else ext
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/{mime};base64,{encoded}"


def _qr_data_uri(payload: str | None) -> str | None:
    if not payload:
        return None
    img = qrcode.make(payload)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


_TITLES = {"ar": "فاتورة ضريبية", "en": "Tax Invoice"}
_LABELS = {
    "ar": {
        "invoice_no": "رقم الفاتورة",
        "invoice_date": "تاريخ الفاتورة",
        "due_date": "تاريخ الاستحقاق",
        "warehouse": "المستودع",
        "bill_to": "فاتورة إلى",
        "vat_number": "الرقم الضريبي",
        "description": "الوصف",
        "qty": "الكمية",
        "unit_price": "سعر الوحدة",
        "tax_rate": "نسبة الضريبة",
        "tax_amount": "مبلغ الضريبة",
        "line_total": "الإجمالي",
        "subtotal": "المجموع الفرعي",
        "total_tax": "إجمالي الضريبة",
        "grand_total": "الإجمالي شامل الضريبة",
    },
    "en": {
        "invoice_no": "Invoice No.",
        "invoice_date": "Invoice Date",
        "due_date": "Due Date",
        "warehouse": "Warehouse",
        "bill_to": "Bill To",
        "vat_number": "VAT Number",
        "description": "Description",
        "qty": "Qty",
        "unit_price": "Unit Price",
        "tax_rate": "Tax %",
        "tax_amount": "Tax Amount",
        "line_total": "Line Total",
        "subtotal": "Subtotal",
        "total_tax": "Total Tax",
        "grand_total": "Grand Total",
    },
}


def render_invoice_pdf(doc: InvoiceDocument) -> bytes:
    lang = doc.lang if doc.lang in _LABELS else "ar"
    labels = _LABELS[lang]
    dir_attr = "rtl" if lang == "ar" else "ltr"
    company_name = doc.company_name_ar if lang == "ar" and doc.company_name_ar else doc.company_name

    logo_uri = _logo_data_uri(doc.company_logo_path)
    qr_uri = _qr_data_uri(doc.qr_payload)

    line_rows = "".join(
        f"""<tr>
            <td>{h(line.description)}</td>
            <td class="num">{line.qty}</td>
            <td class="num">{line.unit_price}</td>
            <td class="num">{line.tax_rate_percent}%</td>
            <td class="num">{line.tax_amount}</td>
            <td class="num">{line.line_total}</td>
        </tr>"""
        for line in doc.lines
    )

    html_doc = f"""<!doctype html>
<html dir="{dir_attr}" lang="{lang}">
<head>
<meta charset="utf-8">
<style>
  @page {{ size: A4; margin: 16mm 12mm; }}
  body {{ font-family: "Noto Sans Arabic", "Noto Naskh Arabic", sans-serif; font-size: 10pt; color: #1a1a1a; }}
  .header {{ display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 2px solid #1a1a1a; padding-bottom: 8pt; margin-bottom: 12pt; }}
  .logo {{ max-height: 50pt; max-width: 140pt; }}
  h1 {{ font-size: 16pt; margin: 0 0 4pt 0; }}
  .company {{ font-size: 11pt; font-weight: 700; margin: 0; }}
  .vat {{ font-size: 9pt; color: #555; margin: 2pt 0 0 0; }}
  .meta {{ display: flex; justify-content: space-between; margin-bottom: 14pt; }}
  .meta div {{ font-size: 9.5pt; }}
  .meta dt {{ color: #666; display: inline; }}
  .meta dd {{ display: inline; margin: 0 0 0 4pt; font-weight: 600; }}
  .bill-to {{ font-size: 9.5pt; margin-bottom: 14pt; }}
  .bill-to .label {{ color: #666; font-size: 8.5pt; text-transform: uppercase; }}
  .bill-to .name {{ font-weight: 700; font-size: 11pt; }}
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 14pt; }}
  th, td {{ border: 1px solid #ccc; padding: 5px 7px; font-variant-numeric: tabular-nums; }}
  th {{ background: #f2f2f2; font-weight: 700; text-align: {"right" if dir_attr == "rtl" else "left"}; }}
  td.num, th.num {{ text-align: end; }}
  .totals {{ width: 45%; margin-{"left" if dir_attr == "rtl" else "right"}: auto; }}
  .totals table {{ margin: 0; }}
  .totals td {{ border: none; padding: 3px 4px; }}
  .totals tr.grand td {{ border-top: 2px solid #1a1a1a; font-weight: 700; font-size: 11pt; }}
  .footer {{ display: flex; justify-content: space-between; align-items: center; margin-top: 20pt; }}
  .qr {{ width: 90pt; height: 90pt; }}
{SIGNATURE_FOOTER_CSS}
</style>
</head>
<body>
  <div class="header">
    <div>
      <p class="company">{h(company_name)}</p>
      <p class="vat">{h(labels["vat_number"])}: {h(doc.company_vat_number)}</p>
    </div>
    {f'<img class="logo" src="{logo_uri}">' if logo_uri else ""}
  </div>
  <h1>{h(_TITLES[lang])}</h1>
  <div class="meta">
    <div><dt>{h(labels["invoice_no"])}:</dt><dd>{h(doc.number)}</dd></div>
    <div><dt>{h(labels["invoice_date"])}:</dt><dd>{doc.invoice_date.isoformat()}</dd></div>
    {f'<div><dt>{h(labels["due_date"])}:</dt><dd>{doc.due_date.isoformat()}</dd></div>' if doc.due_date else ""}
    {f'<div><dt>{h(labels["warehouse"])}:</dt><dd>{h(doc.warehouse_name)}</dd></div>' if doc.warehouse_name else ""}
  </div>
  <div class="bill-to">
    <p class="label">{h(labels["bill_to"])}</p>
    <p class="name">{h(doc.partner_name)}</p>
    {f'<p>{h(labels["vat_number"])}: {h(doc.partner_vat_number)}</p>' if doc.partner_vat_number else ""}
  </div>
  <table>
    <thead>
      <tr>
        <th>{h(labels["description"])}</th>
        <th class="num">{h(labels["qty"])}</th>
        <th class="num">{h(labels["unit_price"])}</th>
        <th class="num">{h(labels["tax_rate"])}</th>
        <th class="num">{h(labels["tax_amount"])}</th>
        <th class="num">{h(labels["line_total"])}</th>
      </tr>
    </thead>
    <tbody>{line_rows}</tbody>
  </table>
  <div class="totals">
    <table>
      <tr><td>{h(labels["subtotal"])}</td><td class="num">{doc.subtotal_amount}</td></tr>
      <tr><td>{h(labels["total_tax"])}</td><td class="num">{doc.tax_amount}</td></tr>
      <tr class="grand"><td>{h(labels["grand_total"])}</td><td class="num">{doc.total_amount}</td></tr>
    </table>
  </div>
  <div class="footer">
    {f'<img class="qr" src="{qr_uri}">' if qr_uri else "<span></span>"}
  </div>
  {render_signature_footer_html(lang)}
</body>
</html>"""

    return HTML(string=html_doc).write_pdf()
