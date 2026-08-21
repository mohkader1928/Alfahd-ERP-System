"""Cycle Count PDF — Owner request: a physical stocktake adjustment
needs a real, printable/archivable document (System Qty vs Actual Qty
vs Variance per line, with the count's own document number), not just
an on-screen table. Same WeasyPrint HTML/CSS -> PDF technique as
`quotation_pdf.py` — deliberately its own document (not a shared base
class), same reasoning: a cycle count has no VAT/ZATCA concerns at all
(it's an internal warehouse document, not a tax or sales document): no
VAT number block, no tax column, no QR code, no customer.
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


@dataclass(frozen=True)
class CycleCountLineRow:
    product_name: str
    product_sku: str
    location_name: str
    system_qty: Decimal
    counted_qty: Decimal
    variance_qty: Decimal


@dataclass(frozen=True)
class CycleCountDocument:
    number: str
    scheduled_date: date
    status: str
    warehouse_name: str
    lines: list[CycleCountLineRow]
    company_name: str
    company_name_ar: str
    company_logo_path: str | None
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


_TITLES = {"ar": "مستند جرد دوري", "en": "Cycle Count Document"}
_STATUS_LABELS = {
    "ar": {"draft": "مسودة", "counted": "تم الجرد", "approved": "معتمد"},
    "en": {"draft": "Draft", "counted": "Counted", "approved": "Approved"},
}
_LABELS = {
    "ar": {
        "number": "رقم المستند",
        "scheduled_date": "تاريخ الجرد",
        "warehouse": "المستودع",
        "status": "الحالة",
        "product": "الصنف",
        "sku": "الرمز",
        "location": "الموقع",
        "system_qty": "الكمية بالنظام",
        "counted_qty": "الكمية المجرودة",
        "variance": "الفرق (زيادة/نقص)",
    },
    "en": {
        "number": "Document No.",
        "scheduled_date": "Count Date",
        "warehouse": "Warehouse",
        "status": "Status",
        "product": "Product",
        "sku": "SKU",
        "location": "Location",
        "system_qty": "System Qty",
        "counted_qty": "Counted Qty",
        "variance": "Variance (Surplus/Shortage)",
    },
}


def render_cycle_count_pdf(doc: CycleCountDocument) -> bytes:
    lang = doc.lang if doc.lang in _LABELS else "ar"
    labels = _LABELS[lang]
    dir_attr = "rtl" if lang == "ar" else "ltr"
    company_name = doc.company_name_ar if lang == "ar" and doc.company_name_ar else doc.company_name
    status_label = _STATUS_LABELS[lang].get(doc.status, doc.status)

    logo_uri = _logo_data_uri(doc.company_logo_path)

    def _fmt(qty: Decimal) -> str:
        return f"{qty:.2f}".rstrip("0").rstrip(".") if qty == qty.to_integral_value() else f"{qty:.2f}"

    line_rows = "".join(
        f"""<tr>
            <td>{h(line.product_name)}</td>
            <td>{h(line.product_sku)}</td>
            <td>{h(line.location_name)}</td>
            <td class="num">{_fmt(line.system_qty)}</td>
            <td class="num">{_fmt(line.counted_qty)}</td>
            <td class="num {'variance-neg' if line.variance_qty < 0 else 'variance-pos' if line.variance_qty > 0 else ''}">
              {"+" + _fmt(line.variance_qty) if line.variance_qty > 0 else _fmt(line.variance_qty)}
            </td>
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
  .meta {{ display: flex; flex-wrap: wrap; gap: 4pt 20pt; margin-bottom: 14pt; }}
  .meta div {{ font-size: 9.5pt; }}
  .meta dt {{ color: #666; display: inline; }}
  .meta dd {{ display: inline; margin: 0 0 0 4pt; font-weight: 600; }}
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 14pt; }}
  th, td {{ border: 1px solid #ccc; padding: 5px 7px; font-variant-numeric: tabular-nums; }}
  th {{ background: #f2f2f2; font-weight: 700; text-align: {"right" if dir_attr == "rtl" else "left"}; }}
  td.num, th.num {{ text-align: end; }}
  .variance-pos {{ color: #0a7a2f; font-weight: 700; }}
  .variance-neg {{ color: #c0392b; font-weight: 700; }}
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
    <div><dt>{h(labels["number"])}:</dt><dd>{h(doc.number)}</dd></div>
    <div><dt>{h(labels["scheduled_date"])}:</dt><dd>{doc.scheduled_date.isoformat()}</dd></div>
    <div><dt>{h(labels["warehouse"])}:</dt><dd>{h(doc.warehouse_name)}</dd></div>
    <div><dt>{h(labels["status"])}:</dt><dd>{h(status_label)}</dd></div>
  </div>
  <table>
    <thead>
      <tr>
        <th>{h(labels["product"])}</th>
        <th>{h(labels["sku"])}</th>
        <th>{h(labels["location"])}</th>
        <th class="num">{h(labels["system_qty"])}</th>
        <th class="num">{h(labels["counted_qty"])}</th>
        <th class="num">{h(labels["variance"])}</th>
      </tr>
    </thead>
    <tbody>{line_rows}</tbody>
  </table>
</body>
</html>"""

    return HTML(string=html_doc).write_pdf()
