"""Turns a `ReportTable` into a downloadable FastAPI `Response` — the thin
per-endpoint glue every report route calls after building its own table
(same query/service data it already returns as JSON, just re-shaped)."""

from __future__ import annotations

from typing import Literal

from fastapi import Response

from src.shared.reporting.export_render import ReportTable, render_excel, render_pdf

ExportFormat = Literal["pdf", "xlsx"]

_MEDIA_TYPES = {
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def build_export_response(fmt: ExportFormat, filename_base: str, table: ReportTable) -> Response:
    if fmt == "pdf":
        content = render_pdf(table)
    else:
        content = render_excel(table)
    filename = f"{filename_base}.{fmt}"
    return Response(
        content=content,
        media_type=_MEDIA_TYPES[fmt],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
