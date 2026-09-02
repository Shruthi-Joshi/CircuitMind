"""SQLAlchemy ORM models — full relational schema per architecture diagram.

Tables
------
- components             : master catalog (with pgvector embedding)
- suppliers              : distributor definitions
- supplier_stock         : multi-vendor stock / pricing
- boms                   : uploaded BOM headers
- bom_line_items         : parsed line items
- purchase_orders        : generated PO line items (split across vendors)
- audit_logs             : every agent decision + human override
"""
from __future__ import annotations

import datetime
import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, relationship


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class Base(DeclarativeBase):
    pass


# ─── Component Catalog ────────────────────────────────────────────────────────

class Component(Base):
    """Master component catalog — each row holds datasheet specs + an embedding
    that encodes part description/specs for vector similarity search."""

    __tablename__ = "components"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    mpn = Column(String(128), nullable=False, unique=True, index=True, comment="Manufacturer Part Number")
    manufacturer = Column(String(128), nullable=False)
    description = Column(Text, nullable=False, default="")
    category = Column(String(64), nullable=False, default="")
    package = Column(String(32), nullable=False, default="", comment="Footprint / package (e.g. SOIC-8)")
    pin_count = Column(Integer, nullable=False, default=0)
    voltage_min = Column(Float, nullable=True)
    voltage_max = Column(Float, nullable=True)
    datasheet_url = Column(Text, nullable=True)

    # 384-dim embedding (all-MiniLM-L6-v2)
    embedding = Column(Vector(384), nullable=True)

    # Convenience JSON for extra specs
    specs = Column(JSONB, nullable=False, default=dict)

    created_at = Column(DateTime(timezone=True), default=_utcnow)

    stock_entries = relationship("SupplierStock", back_populates="component", lazy="select")


Index("ix_components_embedding_cosine", Component.embedding, postgresql_using="ivfflat")


# ─── Suppliers & Stock ─────────────────────────────────────────────────────────

class Supplier(Base):
    __tablename__ = "suppliers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name = Column(String(128), nullable=False, unique=True)
    region = Column(String(64), nullable=False, default="US")
    shipping_days = Column(Integer, nullable=False, default=3)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    stock_entries = relationship("SupplierStock", back_populates="supplier", lazy="select")


class SupplierStock(Base):
    """Multi-vendor stock / pricing. Represents current inventory + cost
    for a component at a specific supplier."""

    __tablename__ = "supplier_stock"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    component_id = Column(UUID(as_uuid=True), ForeignKey("components.id"), nullable=False)
    supplier_id = Column(UUID(as_uuid=True), ForeignKey("suppliers.id"), nullable=False)
    quantity_available = Column(Integer, nullable=False, default=0)
    unit_price = Column(Float, nullable=False, default=0.0)
    lead_time_days = Column(Integer, nullable=False, default=0, comment="Estimated lead time in days")
    is_in_stock = Column(Boolean, nullable=False, default=True)
    last_checked = Column(DateTime(timezone=True), default=_utcnow)

    component = relationship("Component", back_populates="stock_entries")
    supplier = relationship("Supplier", back_populates="stock_entries")


# ─── BOM ───────────────────────────────────────────────────────────────────────

class BOM(Base):
    """Uploaded BOM header."""

    __tablename__ = "boms"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    filename = Column(String(256), nullable=False)
    status = Column(String(32), nullable=False, default="pending",
                    comment="pending | processing | awaiting_approval | completed | failed")
    uploaded_at = Column(DateTime(timezone=True), default=_utcnow)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    line_items = relationship("BOMLineItem", back_populates="bom", lazy="select")


class BOMLineItem(Base):
    """Individual component row parsed from a BOM."""

    __tablename__ = "bom_line_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    bom_id = Column(UUID(as_uuid=True), ForeignKey("boms.id"), nullable=False)
    line_number = Column(Integer, nullable=False)
    reference_designator = Column(String(64), nullable=False, default="")
    mpn = Column(String(128), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    description = Column(Text, nullable=False, default="")

    # Resolved component reference (null until Market Check agent runs)
    component_id = Column(UUID(as_uuid=True), ForeignKey("components.id"), nullable=True)

    # Stock status after market check
    is_in_stock = Column(Boolean, nullable=True)

    # Alternate match
    alternate_component_id = Column(UUID(as_uuid=True), ForeignKey("components.id"), nullable=True)
    alternate_score = Column(Float, nullable=True, comment="Vector similarity compatibility score")
    alternate_approved = Column(Boolean, nullable=True, comment="Human approval result")

    bom = relationship("BOM", back_populates="line_items")
    component = relationship("Component", foreign_keys=[component_id])
    alternate_component = relationship("Component", foreign_keys=[alternate_component_id])


# ─── Purchase Orders ───────────────────────────────────────────────────────────

class PurchaseOrder(Base):
    """Generated PO line: one row per component-supplier pair (split orders)."""

    __tablename__ = "purchase_orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    bom_id = Column(UUID(as_uuid=True), ForeignKey("boms.id"), nullable=False)
    bom_line_item_id = Column(UUID(as_uuid=True), ForeignKey("bom_line_items.id"), nullable=False)
    component_id = Column(UUID(as_uuid=True), ForeignKey("components.id"), nullable=False)
    supplier_id = Column(UUID(as_uuid=True), ForeignKey("suppliers.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=False)
    total_price = Column(Float, nullable=False)
    lead_time_days = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    bom = relationship("BOM")
    line_item = relationship("BOMLineItem")
    component = relationship("Component")
    supplier = relationship("Supplier")


# ─── Audit Logs (Immutable) ───────────────────────────────────────────────────

class AuditLog(Base):
    """Immutable record of agent decisions and human overrides."""

    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    bom_id = Column(UUID(as_uuid=True), ForeignKey("boms.id"), nullable=True)
    agent_name = Column(String(64), nullable=False)
    action = Column(String(128), nullable=False)
    detail = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
