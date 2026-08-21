"""Sales Quotation PDF — Product Owner request: quotations sent to a
customer need a real document (not just an on-screen table), showing each
line's product image and the customer's payment terms. Same WeasyPrint
HTML/CSS -> PDF technique as `invoice_pdf.py` — deliberately its own
document (not a shared base class) since a quotation has no VAT/ZATCA
concerns at all (it's a pre-sale document, not a tax document): no VAT
number block, no tax column, no QR code.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from html import escape as h
from pathlib import Path

from weasyprint import HTML

from src.shared.config.settings import get_settings
from src.shared.documents.signature_footer import SIGNATURE_FOOTER_CSS, render_signature_footer_html


@dataclass(frozen=True)
class QuotationLineRow:
    product_name: str
    product_image_path: str | None
    qty: Decimal
    unit_price: Decimal
    line_total: Decimal


@dataclass(frozen=True)
class QuotationDocument:
    number: str
    quote_date: date
    total_amount: Decimal
    lines: list[QuotationLineRow]
    company_name: str
    company_name_ar: str
    company_logo_path: str | None
    partner_name: str
    payment_terms: str | None
    warehouse_name: str | None = None
    lang: str = "ar"


def _image_data_uri(image_path: str | None) -> str | None:
    if not image_path:
        return None
    settings = get_settings()
    path = Path(settings.media_root) / image_path
    if not path.is_file():
        return None
    ext = path.suffix.lstrip(".").lower() or "png"
    mime = "jpeg" if ext == "jpg" else ext
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/{mime};base64,{encoded}"


_TITLES = {"ar": "عرض سعر", "en": "Price Quotation"}
_LABELS = {
    "ar": {
        "quote_no": "رقم عرض السعر",
        "quote_date": "التاريخ",
        "warehouse": "المستودع",
        "to": "إلى",
        "product": "الصنف",
        "qty": "الكمية",
        "unit_price": "سعر الوحدة",
        "line_total": "الإجمالي",
        "grand_total": "الإجمالي",
        "payment_terms": "شروط الدفع",
    },
    "en": {
        "quote_no": "Quotation No.",
        "quote_date": "Date",
        "warehouse": "Warehouse",
        "to": "To",
        "product": "Product",
        "qty": "Qty",
        "unit_price": "Unit Price",
        "line_total": "Line Total",
        "grand_total": "Grand Total",
        "payment_terms": "Payment Terms",
    },
}


def render_quotation_pdf(doc: QuotationDocument) -> bytes:
    lang = doc.lang if doc.lang in _LABELS else "ar"
    labels = _LABELS[lang]
    dir_attr = "rtl" if lang == "ar" else "ltr"
    company_name = doc.company_name_ar if lang == "ar" and doc.company_name_ar else doc.company_name

    logo_uri = _image_data_uri(doc.company_logo_path)

    line_rows = "".join(
        f"""<tr>
            <td class="product-cell">
              {f'<img class="product-img" src="{_image_data_uri(line.product_image_path)}">' if _image_data_uri(line.product_image_path) else '<span class="no-img"></span>'}
              <span>{h(line.product_name)}</span>
            </td>
            <td class="num">{line.qty}</td>
            <td class="num">{line.unit_price}</td>
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
  .product-cell {{ display: flex; align-items: center; gap: 8pt; }}
  .product-img {{ width: 28pt; height: 28pt; object-fit: cover; border-radius: 3pt; border: 1px solid #ddd; }}
  .no-img {{ width: 28pt; height: 28pt; flex-shrink: 0; }}
  .totals {{ width: 45%; margin-{"left" if dir_attr == "rtl" else "right"}: auto; margin-bottom: 14pt; }}
  .totals table {{ margin: 0; }}
  .totals td {{ border: none; padding: 3px 4px; }}
  .totals tr.grand td {{ border-top: 2px solid #1a1a1a; font-weight: 700; font-size: 11pt; }}
  .terms {{ font-size: 9.5pt; margin-top: 16pt; padding-top: 8pt; border-top: 1px solid #ccc; }}
  .terms .label {{ color: #666; font-size: 8.5pt; text-transform: uppercase; margin-bottom: 3pt; }}
{SIGNATURE_FOOTER_CSS}
</style>
</head>
<body>
  <div class="header">
    <div>
      <p class="company">{h(company_name)}</p>
    </div>
    {f'<img class="logo" src="{logo_uri}">' if logo_uri else ""}
  </div>
  <h1>{h(_TITLES[lang])}</h1>
  <div class="meta">
    <div><dt>{h(labels["quote_no"])}:</dt><dd>{h(doc.number)}</dd></div>
    <div><dt>{h(labels["quote_date"])}:</dt><dd>{doc.quote_date.isoformat()}</dd></div>
    {f'<div><dt>{h(labels["warehouse"])}:</dt><dd>{h(doc.warehouse_name)}</dd></div>' if doc.warehouse_name else ""}
  </div>
  <div class="bill-to">
    <p class="label">{h(labels["to"])}</p>
    <p class="name">{h(doc.partner_name)}</p>
  </div>
  <table>
    <thead>
      <tr>
        <th>{h(labels["product"])}</th>
        <th class="num">{h(labels["qty"])}</th>
        <th class="num">{h(labels["unit_price"])}</th>
        <th class="num">{h(labels["line_total"])}</th>
      </tr>
    </thead>
    <tbody>{line_rows}</tbody>
  </table>
  <div class="totals">
    <table>
      <tr class="grand"><td>{h(labels["grand_total"])}</td><td class="num">{doc.total_amount}</td></tr>
    </table>
  </div>
  {f'<div class="terms"><p class="label">{h(labels["payment_terms"])}</p><p>{h(doc.payment_terms)}</p></div>' if doc.payment_terms else ""}
  {render_signature_footer_html(lang)}
</body>
</html>"""

    return HTML(string=html_doc).write_pdf()
