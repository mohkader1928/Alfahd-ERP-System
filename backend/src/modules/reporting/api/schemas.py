from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class DashboardSummaryOut(BaseModel):
    period_start: date
    period_end: date
    period_sales_total: Decimal
    period_purchases_total: Decimal
    receivables_balance: Decimal
    payables_balance: Decimal
