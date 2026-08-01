"""CSV export (FR-RPT-002). A .csv opens natively in Excel, so this single
implementation satisfies the "Excel/CSV" requirement without adding a
binary-XLSX-writing dependency to the nucleus. PDF export (FR-RPT-001) is
deferred — see Phase 9's exporters/ note; rendering a print-quality PDF
(letterhead, pagination) is a frontend concern for the nucleus rather than
a server-side library choice worth making before the frontend exists.
"""

import csv
import io
from typing import Any


def rows_to_csv(fieldnames: list[str], rows: list[dict[str, Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()
