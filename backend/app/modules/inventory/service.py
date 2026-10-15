"""
Inventory service — the only way stock levels change.

Every write locks the InventoryItem row (SELECT FOR UPDATE) and
creates a StockMovement in the same transaction.  The caller
passes quantity (change to on_hand) and reserved_change (change
to reserved); the service validates, applies, snapshots, audits,
and commits.
"""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import tenant_query
from app.dependencies import TenantContext
from app.modules.audit import service as audit
from app.modules.inventory.models import InventoryItem, StockMovement


async def get_or_create_item(
    db: AsyncSession,
    ctx: TenantContext,
    variant_id: UUID,
    warehouse: str = "default",
) -> InventoryItem:
    """Return the InventoryItem for this variant+warehouse, creating it if absent."""
    stmt = (
        tenant_query(InventoryItem, ctx.tenant_id)
        .where(InventoryItem.variant_id == variant_id, InventoryItem.warehouse == warehouse)
    )
    item = (await db.execute(stmt)).scalar_one_or_none()
    if item is None:
        item = InventoryItem(tenant_id=ctx.tenant_id, variant_id=variant_id, warehouse=warehouse)
        db.add(item)
        await db.flush()
    return item


async def apply_movement(
    db: AsyncSession,
    ctx: TenantContext,
    variant_id: UUID,
    movement_type: str,
    quantity: int,
    reserved_change: int = 0,
    warehouse: str = "default",
    reference_type: str | None = None,
    reference_id: UUID | None = None,
    note: str | None = None,
    performed_by: str | None = None,
    commit: bool = True,
) -> StockMovement:
    """
    The single entry point for all stock changes.

    Locks the InventoryItem row, validates the result won't go
    negative, applies the deltas, and writes the movement record.
    """
    # Lock the row for the duration of this transaction
    stmt = (
        select(InventoryItem)
        .where(
            InventoryItem.tenant_id == ctx.tenant_id,
            InventoryItem.variant_id == variant_id,
            InventoryItem.warehouse == warehouse,
        )
        .with_for_update()
    )
    item = (await db.execute(stmt)).scalar_one_or_none()

    if item is None:
        item = InventoryItem(tenant_id=ctx.tenant_id, variant_id=variant_id, warehouse=warehouse)
        db.add(item)
        await db.flush()
        # re-lock the newly created row
        item = (await db.execute(
            select(InventoryItem).where(InventoryItem.id == item.id).with_for_update()
        )).scalar_one()

    new_on_hand = item.quantity_on_hand + quantity
    new_reserved = item.quantity_reserved + reserved_change

    if new_on_hand < 0:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Insufficient stock: have {item.quantity_on_hand}, tried to remove {abs(quantity)}",
        )
    if new_reserved < 0:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Cannot unreserve more than reserved: have {item.quantity_reserved}, tried {reserved_change}",
        )
    if new_reserved > new_on_hand:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Cannot reserve more than on hand: on_hand={new_on_hand}, reserved would be {new_reserved}",
        )

    item.quantity_on_hand = new_on_hand
    item.quantity_reserved = new_reserved

    movement = StockMovement(
        tenant_id=ctx.tenant_id,
        inventory_item_id=item.id,
        movement_type=movement_type,
        quantity=quantity,
        reserved_change=reserved_change,
        reference_type=reference_type,
        reference_id=reference_id,
        note=note,
        performed_by=performed_by or ctx.user_id,
        quantity_after=new_on_hand,
        reserved_after=new_reserved,
    )
    db.add(movement)

    audit.record(
        db, ctx.tenant_id, ctx.user_id, f"inventory.{movement_type}", "InventoryItem",
        item.id, changes={"quantity": quantity, "reserved_change": reserved_change},
    )
    if commit:
        await db.commit()
    return movement


async def get_stock(
    db: AsyncSession,
    ctx: TenantContext,
    variant_id: UUID,
    warehouse: str = "default",
) -> InventoryItem | None:
    stmt = (
        tenant_query(InventoryItem, ctx.tenant_id)
        .where(InventoryItem.variant_id == variant_id, InventoryItem.warehouse == warehouse)
    )
    return (await db.execute(stmt)).scalar_one_or_none()
