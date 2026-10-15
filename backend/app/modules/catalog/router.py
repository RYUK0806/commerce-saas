"""
Catalog routes — product and variant CRUD.

All routes require tenant membership via get_tenant.
"""

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import TenantContext, get_db, get_tenant
from app.modules.catalog import service

router = APIRouter(prefix="/products", tags=["catalog"])


# --- Schemas ---

class VariantIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    sku: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=255)
    price: Decimal = Field(ge=0, decimal_places=2)
    compare_at_price: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    cost_price: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    currency: str = Field(default="INR", max_length=3)
    weight_grams: int | None = None
    barcode: str | None = Field(default=None, max_length=50)


class ProductCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=500)
    brand: str | None = Field(default=None, max_length=255)
    category: str | None = Field(default=None, max_length=255)
    description: str | None = None
    hsn_code: str | None = Field(default=None, max_length=20)
    tax_rate: Decimal | None = Field(default=None, ge=0, le=100, decimal_places=2)
    attributes: dict | None = None
    variants: list[VariantIn] | None = None


class ProductUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=500)
    brand: str | None = None
    category: str | None = None
    description: str | None = None
    status: str | None = Field(default=None, pattern=r"^(draft|active|archived)$")
    hsn_code: str | None = None
    tax_rate: Decimal | None = Field(default=None, ge=0, le=100, decimal_places=2)
    attributes: dict | None = None


class VariantUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    sku: str | None = Field(default=None, min_length=1, max_length=100)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    price: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    compare_at_price: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    cost_price: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    currency: str | None = Field(default=None, max_length=3)
    weight_grams: int | None = None
    barcode: str | None = None
    is_active: bool | None = None


# --- Helpers ---

def _product_out(p) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "brand": p.brand,
        "category": p.category,
        "description": p.description,
        "status": p.status,
        "hsn_code": p.hsn_code,
        "tax_rate": p.tax_rate,
        "attributes": p.attributes,
        "variants": [_variant_out(v) for v in p.variants],
        "images": [{"id": img.id, "url": img.url, "alt_text": img.alt_text, "is_primary": img.is_primary} for img in p.images],
        "created_at": p.created_at,
    }


def _variant_out(v) -> dict:
    return {
        "id": v.id,
        "sku": v.sku,
        "name": v.name,
        "price": v.price,
        "compare_at_price": v.compare_at_price,
        "cost_price": v.cost_price,
        "currency": v.currency,
        "weight_grams": v.weight_grams,
        "barcode": v.barcode,
        "is_active": v.is_active,
    }


# --- Routes ---

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_product(
    body: ProductCreate,
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    data = body.model_dump(exclude={"variants"}, exclude_unset=True)
    variants = [v.model_dump() for v in body.variants] if body.variants else None
    product = await service.create_product(db, ctx, data, variants)
    # reload with relationships
    product = await service.get_product(db, ctx, product.id)
    return _product_out(product)


@router.get("")
async def list_products(
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
    status_filter: str | None = Query(None, alias="status", pattern=r"^(draft|active|archived)$"),
):
    products = await service.list_products(db, ctx, status_filter)
    return [_product_out(p) for p in products]


@router.get("/{product_id}")
async def get_product(
    product_id: UUID,
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    return _product_out(await service.get_product(db, ctx, product_id))


@router.patch("/{product_id}")
async def update_product(
    product_id: UUID,
    body: ProductUpdate,
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    data = body.model_dump(exclude_unset=True)
    if not data:
        return _product_out(await service.get_product(db, ctx, product_id))
    product = await service.update_product(db, ctx, product_id, data)
    product = await service.get_product(db, ctx, product.id)
    return _product_out(product)


@router.post("/{product_id}/variants", status_code=status.HTTP_201_CREATED)
async def create_variant(
    product_id: UUID,
    body: VariantIn,
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    variant = await service.create_variant(db, ctx, product_id, body.model_dump())
    return _variant_out(variant)


@router.patch("/variants/{variant_id}")
async def update_variant(
    variant_id: UUID,
    body: VariantUpdate,
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    data = body.model_dump(exclude_unset=True)
    if not data:
        return _variant_out(await service._get_variant(db, ctx, variant_id))
    return _variant_out(await service.update_variant(db, ctx, variant_id, data))


@router.delete("/variants/{variant_id}", status_code=status.HTTP_200_OK)
async def delete_variant(
    variant_id: UUID,
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    await service.delete_variant(db, ctx, variant_id)
    return {"detail": "Variant deleted"}
