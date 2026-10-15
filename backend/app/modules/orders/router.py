"""
Order routes — creation, listing, status transitions.
"""

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import TenantContext, get_db, get_tenant
from app.modules.orders import service

router = APIRouter(prefix="/orders", tags=["orders"])


# --- Schemas ---

class OrderItemIn(BaseModel):
    variant_id: UUID | None = None
    sku: str = Field(max_length=100)
    product_name: str = Field(max_length=500)
    variant_name: str = Field(max_length=255)
    quantity: int = Field(ge=1)
    unit_price: Decimal = Field(ge=0, decimal_places=2)
    total_price: Decimal = Field(ge=0, decimal_places=2)


class OrderCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    channel_id: UUID | None = None
    external_order_id: str | None = Field(default=None, max_length=255)
    subtotal: Decimal = Field(ge=0, decimal_places=2)
    tax_amount: Decimal = Field(default=Decimal(0), ge=0, decimal_places=2)
    shipping_amount: Decimal = Field(default=Decimal(0), ge=0, decimal_places=2)
    total_amount: Decimal = Field(ge=0, decimal_places=2)
    currency: str = Field(default="INR", max_length=3)
    customer_name: str | None = Field(default=None, max_length=255)
    customer_email: str | None = Field(default=None, max_length=255)
    shipping_address: dict | None = None
    fulfillment_type: str = Field(default="self", pattern=r"^(self|fba|third_party)$")
    notes: str | None = None
    items: list[OrderItemIn] = Field(min_length=1)


class StatusUpdate(BaseModel):
    status: str = Field(pattern=r"^(confirmed|processing|shipped|delivered|cancelled|returned)$")


# --- Helpers ---

def _order_out(o) -> dict:
    return {
        "id": o.id,
        "order_number": o.order_number,
        "status": o.status,
        "channel_id": o.channel_id,
        "external_order_id": o.external_order_id,
        "subtotal": o.subtotal,
        "tax_amount": o.tax_amount,
        "shipping_amount": o.shipping_amount,
        "total_amount": o.total_amount,
        "currency": o.currency,
        "customer_name": o.customer_name,
        "customer_email": o.customer_email,
        "ordered_at": o.ordered_at,
        "shipped_at": o.shipped_at,
        "items": [
            {
                "id": i.id, "sku": i.sku, "product_name": i.product_name,
                "variant_name": i.variant_name, "quantity": i.quantity,
                "unit_price": i.unit_price, "total_price": i.total_price,
            }
            for i in o.items
        ],
    }


# --- Routes ---

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_order(
    body: OrderCreate,
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    data = body.model_dump(exclude={"items"})
    items = [i.model_dump() for i in body.items]
    order = await service.create_order(db, ctx, data, items)
    order = await service.get_order(db, ctx, order.id)
    return _order_out(order)


@router.get("")
async def list_orders(
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
    status_filter: str | None = Query(None, alias="status"),
):
    orders = await service.list_orders(db, ctx, status_filter)
    return [_order_out(o) for o in orders]


@router.get("/{order_id}")
async def get_order(
    order_id: UUID,
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    return _order_out(await service.get_order(db, ctx, order_id))


@router.patch("/{order_id}/status")
async def update_status(
    order_id: UUID,
    body: StatusUpdate,
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    order = await service.transition_status(db, ctx, order_id, body.status)
    return _order_out(order)
