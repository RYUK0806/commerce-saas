"""
Orders service — idempotent creation and status state machine.

Status transitions and their inventory effects:
  pending    → confirmed    (no stock change)
  confirmed  → processing   (no stock change)
  processing → shipped      (on_hand −qty, reserved −qty)
  shipped    → delivered     (no stock change)
  pending    → cancelled     (reserved −qty)
  confirmed  → cancelled     (reserved −qty)
  shipped    → returned      (on_hand +qty)
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import tenant_query
from app.dependencies import TenantContext
from app.modules.audit import service as audit
from app.modules.inventory import service as inventory
from app.modules.orders.models import Order, OrderItem

_TRANSITIONS: dict[str, set[str]] = {
    "pending":    {"confirmed", "cancelled"},
    "confirmed":  {"processing", "cancelled"},
    "processing": {"shipped"},
    "shipped":    {"delivered", "returned"},
}


async def create_order(
    db: AsyncSession,
    ctx: TenantContext,
    data: dict,
    items_data: list[dict],
) -> Order:
    """
    Create an order with line items.  Reserves stock for each item.

    If (channel_id, external_order_id) already exists, returns 409
    rather than a duplicate.
    """
    if not items_data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Order must have at least one item")

    order_number = await _next_order_number(db, ctx.tenant_id)
    order = Order(tenant_id=ctx.tenant_id, order_number=order_number, **data)
    db.add(order)

    for item in items_data:
        db.add(OrderItem(tenant_id=ctx.tenant_id, order=order, **item))

    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Duplicate order (same channel + external ID)")

    # Reserve stock for each line item (commit=False: one transaction for the whole order)
    for item in items_data:
        if item.get("variant_id"):
            await inventory.apply_movement(
                db, ctx, item["variant_id"], "reservation",
                quantity=0, reserved_change=item["quantity"],
                reference_type="order", reference_id=order.id,
                note=f"Reserved for order {order_number}",
                commit=False,
            )

    audit.record(db, ctx.tenant_id, ctx.user_id, "order.created", "Order", order.id)
    await db.commit()
    return order


async def get_order(
    db: AsyncSession,
    ctx: TenantContext,
    order_id: UUID,
) -> Order:
    stmt = (
        tenant_query(Order, ctx.tenant_id)
        .where(Order.id == order_id)
        .options(selectinload(Order.items))
    )
    order = (await db.execute(stmt)).scalar_one_or_none()
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    return order


async def list_orders(
    db: AsyncSession,
    ctx: TenantContext,
    status_filter: str | None = None,
) -> list[Order]:
    stmt = tenant_query(Order, ctx.tenant_id).options(selectinload(Order.items))
    if status_filter:
        stmt = stmt.where(Order.status == status_filter)
    stmt = stmt.order_by(Order.created_at.desc())
    return list((await db.execute(stmt)).scalars())


async def transition_status(
    db: AsyncSession,
    ctx: TenantContext,
    order_id: UUID,
    new_status: str,
) -> Order:
    """
    Move an order to a new status.  Validates the transition and
    triggers the corresponding inventory movements.
    """
    order = await get_order(db, ctx, order_id)
    allowed = _TRANSITIONS.get(order.status, set())
    if new_status not in allowed:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Cannot transition from '{order.status}' to '{new_status}'",
        )

    old_status = order.status
    order.status = new_status

    if new_status == "shipped":
        order.shipped_at = datetime.now(timezone.utc)

    # Inventory side-effects
    await _apply_inventory_for_transition(db, ctx, order, old_status, new_status)

    audit.record(
        db, ctx.tenant_id, ctx.user_id, "order.status_changed", "Order",
        order.id, changes={"status": {"old": old_status, "new": new_status}},
    )
    await db.commit()
    return order


async def _apply_inventory_for_transition(
    db: AsyncSession,
    ctx: TenantContext,
    order: Order,
    old_status: str,
    new_status: str,
) -> None:
    for item in order.items:
        if item.variant_id is None:
            continue

        if new_status == "shipped":
            await inventory.apply_movement(
                db, ctx, item.variant_id, "sale",
                quantity=-item.quantity, reserved_change=-item.quantity,
                reference_type="order", reference_id=order.id, commit=False,
            )
        elif new_status == "cancelled":
            await inventory.apply_movement(
                db, ctx, item.variant_id, "release",
                quantity=0, reserved_change=-item.quantity,
                reference_type="order", reference_id=order.id, commit=False,
            )
        elif new_status == "returned":
            await inventory.apply_movement(
                db, ctx, item.variant_id, "return",
                quantity=item.quantity, reserved_change=0,
                reference_type="order", reference_id=order.id, commit=False,
            )


async def _next_order_number(db: AsyncSession, tenant_id: UUID) -> str:
    result = await db.scalar(
        select(func.count()).select_from(Order).where(Order.tenant_id == tenant_id)
    )
    return f"ORD-{(result or 0) + 1:05d}"
