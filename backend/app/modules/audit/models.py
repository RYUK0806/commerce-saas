"""
Audit log — who did what, when.

One table, append-only. Every important action in the system
gets a row here: product created, order status changed, channel
connected, credentials rotated, user role changed.

This is not the same as StockMovement. StockMovement tracks
inventory arithmetic. AuditLog tracks business actions.

Audit rows are NEVER updated or deleted.
"""

import uuid

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, TenantScopedMixin


class AuditLog(TenantScopedMixin, Base):
    """
    An immutable record of a business action.

    Examples:
      actor=user_2abc action=product.created entity=Product entity_id=xxx
      actor=user_2abc action=order.status_changed entity=Order entity_id=xxx
        changes={"status": {"old": "pending", "new": "shipped"}}
      actor=system action=channel.sync_failed entity=Channel entity_id=xxx
    """

    __tablename__ = "audit_logs"

    # --- Who ---
    actor: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Clerk user ID, or 'system' for automated actions",
    )

    # --- What ---
    action: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Dotted action name: product.created, order.status_changed",
    )

    # --- On what ---
    entity_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Model name: Product, Order, Channel, Membership",
    )

    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="ID of the affected row",
    )

    # --- Details ---
    changes: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment='What changed: {"field": {"old": x, "new": y}}',
    )

    metadata_: Mapped[dict | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
        comment="Extra context (IP address, user agent, etc.)",
    )

    # --- Human-readable summary ---
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Plain English: 'Krish changed order #1042 status to shipped'",
    )
