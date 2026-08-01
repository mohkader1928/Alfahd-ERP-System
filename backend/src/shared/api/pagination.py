"""Phase 17A: shared pagination contract for future list/report endpoints.

Not wired into any existing route yet — every current `list_by_company()`
endpoint returns a bare `list[XOut]` and stays that way in this phase to
avoid a breaking API/frontend contract change with no foundation-phase
benefit. New list and report endpoints built from Phase 17B onward should
use `PageParams`/`Page` instead of inventing their own paging shape per
module, per the "one filter system → all reports" principle in the
Phase 17A brief.
"""

from pydantic import BaseModel, Field


class PageParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=500)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int
