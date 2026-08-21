"""Matches `frontend/lib/format-currency.ts` and `format-date.ts` exactly —
Western digits, en-US grouping, 2 decimals — so a report's PDF/Excel export
shows the same numbers, in the same shape, as its on-screen version."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal


def format_amount(value: Decimal | str | float | None, currency: str = "SAR") -> str:
    if value is None:
        value = Decimal(0)
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return f"{value:,.2f} {currency}"


def format_qty(value: Decimal | str | float | None) -> str:
    """Reports carry internal quantities at up to 6 decimal places
    (StockQuant/StockMove/StockLayer are NUMERIC(18,6), kept that precise
    so moving-average costing never loses a fraction), but that precision
    is noise on a printed report -- Owner request: cap every displayed
    quantity at 2 decimal places, same as `format_amount`, while still
    dropping trailing zeros for whole/near-whole quantities."""
    if value is None:
        value = Decimal(0)
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return f"{value:,.2f}".rstrip("0").rstrip(".") or "0"


def format_date_str(value: date | datetime | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value[:10]
    return value.strftime("%Y-%m-%d")
