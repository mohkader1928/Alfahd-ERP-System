"""SQLAlchemy ORM models for Inventory, mirroring Phase 7 §5 DDL."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.infrastructure.db.base import Base


class Warehouse(Base):
    __tablename__ = "warehouse"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))


class Location(Base):
    __tablename__ = "location"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("warehouse.id"), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("location.id"), nullable=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    is_virtual: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))


MOVE_TYPES = ("receipt", "delivery", "transfer", "adjustment")


class StockMove(Base):
    __tablename__ = "stock_move"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    source_location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("location.id"), nullable=True
    )
    dest_location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("location.id"), nullable=True
    )
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    move_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_table: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    moved_at: Mapped[datetime] = mapped_column(server_default=text("now()"), nullable=False)
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        CheckConstraint(f"move_type IN {MOVE_TYPES}", name="ck_stock_move_type"),
        CheckConstraint("qty > 0", name="ck_stock_move_qty_positive"),
        Index("ix_stock_move_product_dest", "product_id", "dest_location_id"),
    )


class StockQuant(Base):
    __tablename__ = "stock_quant"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    location_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("location.id"), nullable=False)
    qty_on_hand: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, server_default=text("0"))
    moving_avg_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default=text("0"))

    __table_args__ = (UniqueConstraint("product_id", "location_id", name="ux_stock_quant_product_location"),)


class StockLayer(Base):
    __tablename__ = "stock_layer"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    location_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("location.id"), nullable=False)
    qty_remaining: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    received_at: Mapped[datetime] = mapped_column(server_default=text("now()"), nullable=False)

    __table_args__ = (
        CheckConstraint("qty_remaining >= 0", name="ck_stock_layer_nonnegative"),
        Index("ix_stock_layer_fifo", "product_id", "location_id", "received_at"),
    )


class CycleCount(Base):
    __tablename__ = "cycle_count"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("warehouse.id"), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="draft")
    scheduled_date: Mapped[date] = mapped_column(nullable=False)

    __table_args__ = (CheckConstraint("status IN ('draft','counted','approved')", name="ck_cycle_count_status"),)


class CycleCountLine(Base):
    __tablename__ = "cycle_count_line"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    cycle_count_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cycle_count.id"), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    location_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("location.id"), nullable=False)
    system_qty: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    counted_qty: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    stock_move_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("stock_move.id"), nullable=True)
