"""Turns a `ReportTable` into a downloadable FastAPI `Response` — the thin
per-endpoint glue every report route calls after building its own table
(same query/service data it already returns as JSON, just re-shaped)."""

from __future__ import annotations

from typing import Literal
from urllib.parse import quote

from fastapi import Response

from src.shared.reporting.export_render import ReportTable, render_excel, render_pdf

ExportFormat = Literal["pdf", "xlsx"]

_MEDIA_TYPES = {
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _content_disposition(filename: str) -> str:
    """HTTP header values are Latin-1 only (Starlette raises UnicodeEncodeError
    -- a 500, not a graceful fallback -- the instant a header value falls
    outside that range), but `filename` is routinely a partner/company/product
    name, and this is a Saudi ERP: that name is very often Arabic. Owner-
    reported: Vendor Subledger's PDF/Excel export silently "didn't work" for
    شركة القارات الخمسة -- reproduced directly: constructing the Response
    itself throws before a single byte is sent, for ANY export whose filename
    carries a non-Latin-1 character, across every report in the app (this
    helper is shared by Inventory/Reporting/Fixed Assets/Accounting/Payments).
    RFC 6266 fixes this correctly: an ASCII-safe `filename=` for old clients
    that don't parse the extended form, plus the real name UTF-8-percent-
    encoded in `filename*=`, which every modern browser prefers and decodes
    correctly."""
    ascii_fallback = filename.encode("ascii", "ignore").decode("ascii").strip() or "report"
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(filename)}"


def build_export_response(fmt: ExportFormat, filename_base: str, table: ReportTable) -> Response:
    if fmt == "pdf":
        content = render_pdf(table)
    else:
        content = render_excel(table)
    filename = f"{filename_base}.{fmt}"
    return Response(
        content=content,
        media_type=_MEDIA_TYPES[fmt],
        headers={"Content-Disposition": _content_disposition(filename)},
    )
