"""Add fiscal_year_start_month to company (Dashboard KPIs / P0-8)

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-08-10 00:00:00.000000

P0-8 audit finding: the Dashboard's "current period" KPIs and trend
chart were hardcoded to a calendar year (Jan 1 - Dec 31) with no
concept of a fiscal year anywhere in the schema — `company` had no
field for it at all. Adds `fiscal_year_start_month` (1-12, default 1 =
January, so every existing company's behavior is unchanged unless an
Owner deliberately configures otherwise) so the frontend can compute
the real "fiscal year to date" range instead of assuming Jan-Dec.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "company",
        sa.Column("fiscal_year_start_month", sa.SmallInteger(), nullable=False, server_default="1"),
    )
    op.create_check_constraint(
        "ck_company_fiscal_year_start_month",
        "company",
        "fiscal_year_start_month BETWEEN 1 AND 12",
    )


def downgrade() -> None:
    op.drop_constraint("ck_company_fiscal_year_start_month", "company", type_="check")
    op.drop_column("company", "fiscal_year_start_month")
