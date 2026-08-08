"""Pydantic schemas for Inventory, per Phase 10 §6.4."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class WarehouseCreateRequest(BaseModel):
    name: str
    is_default: bool = False


class LocationOut(BaseModel):
    id: UUID
    warehouse_id: UUID
    name: str
    is_virtual: bool

    model_config = {"from_attributes": True}


class WarehouseOut(BaseModel):
    id: UUID
    company_id: UUID
    branch_id: UUID
    name: str
    is_default: bool

    model_config = {"from_attributes": True}


class WarehouseCreateResponse(BaseModel):
    warehouse: WarehouseOut
    default_location: LocationOut


class StockReceiveRequest(BaseModel):
    product_id: UUID
    location_id: UUID
    qty: Decimal
    unit_cost: Decimal


class StockQuantOut(BaseModel):
    product_id: UUID
    location_id: UUID
    qty_on_hand: Decimal
    moving_avg_cost: Decimal

    model_config = {"from_attributes": True}


class LowStockRowOut(BaseModel):
    product_id: UUID
    sku: str
    name: str
    name_ar: str | None
    qty_on_hand: Decimal
    reorder_point: Decimal
    shortfall: Decimal


class StockMoveOut(BaseModel):
    id: UUID
    product_id: UUID
    source_location_id: UUID | None
    dest_location_id: UUID | None
    qty: Decimal
    unit_cost: Decimal
    move_type: str
    source_table: str
    source_id: UUID
    moved_at: datetime

    model_config = {"from_attributes": True}


class TransferCreateRequest(BaseModel):
    product_id: UUID
    source_location_id: UUID
    dest_location_id: UUID
    qty: Decimal


class CycleCountLineIn(BaseModel):
    product_id: UUID
    location_id: UUID
    counted_qty: Decimal


class CycleCountCreateRequest(BaseModel):
    warehouse_id: UUID
    scheduled_date: date
    lines: list[CycleCountLineIn]


class CycleCountLineOut(BaseModel):
    id: UUID
    product_id: UUID
    location_id: UUID
    system_qty: Decimal
    counted_qty: Decimal
    stock_move_id: UUID | None

    model_config = {"from_attributes": True}


class CycleCountOut(BaseModel):
    id: UUID
    company_id: UUID
    warehouse_id: UUID
    status: str
    scheduled_date: date

    model_config = {"from_attributes": True}


class CycleCountDetailResponse(BaseModel):
    cycle_count: CycleCountOut
    lines: list[CycleCountLineOut]


class CardexLineOut(BaseModel):
    id: UUID
    moved_at: datetime
    move_type: str
    source_table: str
    source_id: UUID
    qty: Decimal
    unit_cost: Decimal
    signed_qty: Decimal
    running_qty: Decimal


class ProductCardexResponse(BaseModel):
    product_id: UUID
    opening_qty: Decimal
    lines: list[CardexLineOut]
    closing_qty: Decimal
