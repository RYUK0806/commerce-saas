"""
Inventory routes — stock movements and levels.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import TenantContext, get_db, get_tenant
from app.modules.inventory import service

router = APIRouter(prefix="/inventory", tags=["inventory"])


class MovementIn(BaseModel):
    variant_id: UUID
    movement_type: str = Field(pattern=r"^(purchase|sale|return|adjustment|reservation|release|damage|transfer)$")
    quantity: int
    reserved_change: int = 0
    warehouse: str = "default"
    reference_type: str | None = None
    reference_id: UUID | None = None
    note: str | None = None


@router.post("/movements", status_code=status.HTTP_201_CREATED)
async def record_movement(
    body: MovementIn,
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    m = await service.apply_movement(
        db, ctx, body.variant_id, body.movement_type, body.quantity,
        body.reserved_change, body.warehouse, body.reference_type,
        body.reference_id, body.note,
    )
    return {
        "id": m.id,
        "movement_type": m.movement_type,
        "quantity": m.quantity,
        "reserved_change": m.reserved_change,
        "quantity_after": m.quantity_after,
        "reserved_after": m.reserved_after,
    }


@router.get("/stock/{variant_id}")
async def get_stock(
    variant_id: UUID,
    warehouse: str = "default",
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    item = await service.get_stock(db, ctx, variant_id, warehouse)
    if item is None:
        return {"variant_id": variant_id, "warehouse": warehouse, "on_hand": 0, "reserved": 0, "available": 0}
    return {
        "variant_id": variant_id,
        "warehouse": warehouse,
        "on_hand": item.quantity_on_hand,
        "reserved": item.quantity_reserved,
        "available": item.quantity_available,
        "is_low_stock": item.is_low_stock,
    }
