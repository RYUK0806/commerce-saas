"""
Inventory module models — the source of truth for stock.

Two tables, one iron rule:

  InventoryItem  = current stock levels for a variant at a location
  StockMovement  = every change that ever happened to that stock

The iron rule:
  quantity_on_hand MUST equal the sum of all StockMovement amounts
  for that item. If they disagree, something is broken.

Why two tables instead of just tracking movements?
Reading the current stock level is the most frequent query in the
system — every order check, every listing sync, every dashboard load.
Summing thousands of movement rows every time would be slow.
So InventoryItem caches the current totals, and StockMovement is
the audit trail that proves those totals are correct.

Every write to InventoryItem MUST also create a StockMovement row
in the same database transaction. This is enforced in the service
layer (inventory/service.py), never by direct column updates.

Stock breakdown:
  quantity_on_hand  = total physical stock you have
  quantity_reserved = stock claimed by orders not yet shipped
  quantity_available = on_hand - reserved (what you can still sell)

  This is computed, not stored: available = on_hand - reserved
  Storing it would create a third number that could drift.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class InventoryItem(Base):
    """
    Current stock levels for one variant at one location.

    One row per (tenant, variant, warehouse).
    If a business has 3 warehouses and a variant is stocked
    in 2 of them, that's 2 InventoryItem rows.

    For MVP, we use a single default warehouse per tenant.
    The warehouse column is here from day one so we don't
    need a migration when multi-warehouse lands.
    """

    __tablename__ = "inventory_items"

    # --- Tenant isolation ---
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    # --- What this stock is ---
    variant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("variants.id", ondelete="CASCADE"),
        nullable=False,
    )

    # --- Where this stock is ---
    warehouse: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="default",
        server_default="default",
        comment="Warehouse or location name. MVP uses 'default'.",
    )

    # --- Stock quantities ---
    # These are ONLY modified through the service layer,
    # which creates a StockMovement in the same transaction.

    quantity_on_hand: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Total physical stock at this location",
    )

    quantity_reserved: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Stock claimed by unshipped orders",
    )

    # quantity_available is NOT a column — it's computed:
    # available = on_hand - reserved
    # Storing it would create drift risk.
    @property
    def quantity_available(self) -> int:
        """Stock that can still be sold right now."""
        return self.quantity_on_hand - self.quantity_reserved

    # --- Safety stock ---
    low_stock_threshold: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=10,
        server_default="10",
        comment="Alert when available stock drops below this",
    )

    # --- Relationships ---
    variant: Mapped["Variant"] = relationship(
        "app.modules.catalog.models.Variant",
    )

    movements: Mapped[list["StockMovement"]] = relationship(
        back_populates="inventory_item",
        order_by="StockMovement.created_at.desc()",
    )

    __table_args__ = (
        # One inventory record per variant per warehouse per tenant
        UniqueConstraint(
            "tenant_id", "variant_id", "warehouse",
            name="uq_inventory_tenant_variant_warehouse",
        ),
    )

    @property
    def is_low_stock(self) -> bool:
        """True if available stock is at or below the alert threshold."""
        return self.quantity_available <= self.low_stock_threshold

    def __repr__(self) -> str:
        return (
            f"<InventoryItem variant={self.variant_id} "
            f"on_hand={self.quantity_on_hand} "
            f"reserved={self.quantity_reserved} "
            f"available={self.quantity_available}>"
        )


class StockMovement(Base):
    """
    An immutable record of a stock change. The audit trail.

    Every time stock changes — a purchase order arrives, an order
    ships, a return comes back, someone does a manual count — a
    StockMovement row is created. These rows are NEVER updated
    or deleted. They are append-only.

    The sum of all movement quantities for an InventoryItem must
    equal that item's quantity_on_hand. This invariant is checked
    by the reconciliation job.

    Movement types and their typical quantity signs:
      purchase      +   Stock received from supplier
      sale          -   Stock sold and shipped
      return        +   Customer returned an item
      adjustment    +/- Manual correction (count discrepancy)
      reservation   0   Reserved for an order (changes reserved, not on_hand)
      release       0   Reservation cancelled (unreserves stock)
      damage        -   Stock written off as damaged
      transfer      +/- Moved between warehouses

    The quantity column tracks changes to on_hand.
    The reserved_change column tracks changes to reserved.
    A sale: quantity=-1, reserved_change=-1 (shipped, so unreserve too)
    A reservation: quantity=0, reserved_change=+1 (on_hand unchanged)
    """

    __tablename__ = "stock_movements"

    # --- Tenant isolation ---
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    # --- Which inventory item changed ---
    inventory_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inventory_items.id", ondelete="CASCADE"),
        nullable=False,
    )

    # --- What happened ---
    movement_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="purchase | sale | return | adjustment | reservation | release | damage | transfer",
    )

    # --- How much changed ---
    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Change to on_hand. Positive=increase, negative=decrease.",
    )

    reserved_change: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Change to reserved. +1 for reservation, -1 when shipped.",
    )

    # --- Context ---
    # What triggered this movement? An order? A manual adjustment?
    reference_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="What triggered this: 'order', 'manual', 'reconciliation'",
    )

    reference_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="ID of the order, adjustment, etc. that caused this",
    )

    # Who did it and why
    note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Human-readable explanation, e.g. 'Manual count correction'",
    )

    performed_by: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Clerk user ID of who triggered this, or 'system'",
    )

    # --- Snapshot at time of movement ---
    # What was the stock level AFTER this movement?
    # This makes the audit trail self-contained — you can verify
    # the running total without replaying from the beginning.
    quantity_after: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="quantity_on_hand AFTER this movement was applied",
    )

    reserved_after: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="quantity_reserved AFTER this movement was applied",
    )

    # --- Relationships ---
    inventory_item: Mapped["InventoryItem"] = relationship(
        back_populates="movements",
    )

    def __repr__(self) -> str:
        return (
            f"<StockMovement {self.movement_type} "
            f"qty={self.quantity:+d} "
            f"reserved={self.reserved_change:+d}>"
        )
