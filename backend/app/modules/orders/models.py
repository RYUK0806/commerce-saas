"""
Orders module models — order processing with idempotency.

Two tables:

  Order      = an order from any channel (Amazon, website, manual)
  OrderItem  = a line item within an order (one variant, one quantity)

The idempotency rule:
  UniqueConstraint on (channel_id, external_order_id) guarantees
  that processing the same Amazon order notification twice doesn't
  create a duplicate order. The database rejects the second insert.

Order lifecycle:
  pending → confirmed → processing → shipped → delivered
                                   → cancelled
                                   → returned

Each status transition triggers inventory changes via StockMovement:
  pending:    reserve stock (reserved_change=+1)
  cancelled:  release reservation (reserved_change=-1)
  shipped:    deduct stock (quantity=-1, reserved_change=-1)
  returned:   add stock back (quantity=+1)
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
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, TenantScopedMixin


class Order(TenantScopedMixin, Base):
    """
    An order from any sales channel.

    Amazon sends an order notification → we create an Order row
    with external_order_id = Amazon's order ID. If Amazon sends
    the same notification again (duplicate webhook, retry, etc.),
    the unique constraint blocks the duplicate.
    """

    __tablename__ = "orders"

    # --- Source channel ---
    channel_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("channels.id", ondelete="SET NULL"),
        nullable=True,
        comment="Which channel this order came from. Null for manual orders.",
    )

    # --- External identity (idempotency key) ---
    external_order_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Order ID on the marketplace (Amazon order ID, etc.)",
    )

    # --- Order details ---
    order_number: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Internal order number (displayed to the user)",
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
        comment="pending | confirmed | processing | shipped | delivered | cancelled | returned",
    )

    # --- Money ---
    subtotal: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=0,
        comment="Sum of line items before tax and shipping",
    )

    tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=0,
    )

    shipping_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=0,
    )

    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=0,
        comment="Final amount: subtotal + tax + shipping",
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="INR",
        server_default="INR",
    )

    # --- Customer info ---
    customer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    customer_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # --- Shipping address (as JSON — keeps the schema simple) ---
    shipping_address: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Shipping address fields as JSON",
    )

    # --- Timestamps ---
    ordered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="When the order was placed (marketplace timestamp if available)",
    )

    shipped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # --- Fulfillment ---
    fulfillment_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="self",
        server_default="self",
        comment="self | fba (Fulfilled by Amazon) | third_party",
    )

    tracking_number: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tracking_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Notes ---
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Internal notes about this order",
    )

    # --- Channel-specific raw data ---
    raw_data: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Original order payload from the channel (for debugging)",
    )

    # --- Relationships ---
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        # THE idempotency constraint.
        # Same channel + same external order ID = duplicate.
        # nullable external_order_id means manual orders skip this.
        UniqueConstraint(
            "channel_id", "external_order_id",
            name="uq_order_channel_external_id",
        ),
    )

    def __repr__(self) -> str:
        return f"<Order {self.order_number} status={self.status}>"


class OrderItem(TenantScopedMixin, Base):
    """
    A line item in an order — one variant, one quantity.

    An order for "2x Ghee 1L + 1x Ghee 500ml" has two OrderItems.

    Each item records:
    - Which variant was ordered
    - How many units
    - The price at time of purchase (snapshot — not a live reference
      to the current variant price, which might change)
    """

    __tablename__ = "order_items"

    # --- Parent order ---
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )

    # --- What was ordered ---
    variant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("variants.id", ondelete="SET NULL"),
        nullable=True,
        comment="Null if the variant was later deleted (order history preserved)",
    )

    # --- Snapshot at time of purchase ---
    # These are copied from the variant when the order is created.
    # If the variant price changes tomorrow, this order still shows
    # what the customer actually paid.
    sku: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="SKU at time of purchase (snapshot)",
    )

    product_name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Product name at time of purchase (snapshot)",
    )

    variant_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Variant name at time of purchase (snapshot)",
    )

    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Number of units ordered",
    )

    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        comment="Price per unit at time of purchase",
    )

    total_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        comment="quantity × unit_price",
    )

    # --- Relationships ---
    order: Mapped["Order"] = relationship(back_populates="items")

    def __repr__(self) -> str:
        return f"<OrderItem {self.sku} x{self.quantity}>"
