"""Shared sign-off footer — Owner request: every PDF this system produces
(individual documents and tabular reports alike) ends with the same
three-line block: "Prepared by" / "Reviewed by" side by side, and
"Approved by" centered on its own line below. `justify-content:
space-between` on a flex row whose two children follow document order
(prepared, then reviewed) auto-flips with the page's own `dir` — under
`dir="rtl"` the first child lands on the visual right and the second on
the left (matching the Owner's literal "Prepared by on the right,
Reviewed by on the left"); under `dir="ltr"` the same markup mirrors to
the equally-conventional English reading order (Prepared left, Reviewed
right) with no extra logic needed.

The one genuinely shared HTML/CSS fragment across the PDF machinery —
every other block (header, meta, table styling) is deliberately
duplicated per document (see each file's own docstring for why), but a
sign-off footer is identical in every one of them, so it's written once
here and imported everywhere instead.
"""

from __future__ import annotations

from html import escape as h

_LABELS = {
    "ar": {"prepared_by": "أعد بواسطة", "reviewed_by": "روجع بواسطة", "approved_by": "أعتمد بواسطة"},
    "en": {"prepared_by": "Prepared by", "reviewed_by": "Reviewed by", "approved_by": "Approved by"},
}

# Meant to be interpolated straight into each document's own <style> block.
SIGNATURE_FOOTER_CSS = """
  .signature-footer { margin-top: 28pt; padding-top: 10pt; }
  .sig-row { display: flex; justify-content: space-between; margin-bottom: 20pt; }
  .sig-row.sig-row-single { justify-content: center; }
  .sig-block { display: flex; flex-direction: column; gap: 4pt; width: 42%; }
  .sig-row-single .sig-block { align-items: center; }
  .sig-label { font-size: 9pt; color: #444; font-weight: 600; }
  .sig-line { border-bottom: 1px solid #999; height: 16pt; }
"""


def render_signature_footer_html(lang: str) -> str:
    labels = _LABELS[lang] if lang in _LABELS else _LABELS["ar"]
    return f"""<div class="signature-footer">
    <div class="sig-row">
      <div class="sig-block"><span class="sig-label">{h(labels["prepared_by"])}</span><span class="sig-line"></span></div>
      <div class="sig-block"><span class="sig-label">{h(labels["reviewed_by"])}</span><span class="sig-line"></span></div>
    </div>
    <div class="sig-row sig-row-single">
      <div class="sig-block"><span class="sig-label">{h(labels["approved_by"])}</span><span class="sig-line"></span></div>
    </div>
  </div>"""
