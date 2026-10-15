"""
Catalog service — product and variant CRUD, tenant-scoped.

Services commit their own transaction (see audit/service.py).
"""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import tenant_query
from app.dependencies import TenantContext
from app.modules.audit import service as audit
from app.modules.catalog.models import Product, ProductImage, Variant


# --- Products ---

async def create_product(
    db: AsyncSession,
    ctx: TenantContext,
    data: dict,
    variants_data: list[dict] | None = None,
) -> Product:
    product = Product(tenant_id=ctx.tenant_id, **data)
    db.add(product)

    if variants_data:
        for v in variants_data:
            db.add(Variant(tenant_id=ctx.tenant_id, product=product, **v))

    await db.flush()
    audit.record(db, ctx.tenant_id, ctx.user_id, "product.created", "Product", product.id)
    await db.commit()
    return product


async def list_products(
    db: AsyncSession,
    ctx: TenantContext,
    status_filter: str | None = None,
) -> list[Product]:
    stmt = tenant_query(Product, ctx.tenant_id).options(
        selectinload(Product.variants),
        selectinload(Product.images),
    )
    if status_filter:
        stmt = stmt.where(Product.status == status_filter)
    stmt = stmt.order_by(Product.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars())


async def get_product(
    db: AsyncSession,
    ctx: TenantContext,
    product_id: UUID,
) -> Product:
    stmt = (
        tenant_query(Product, ctx.tenant_id)
        .where(Product.id == product_id)
        .options(selectinload(Product.variants), selectinload(Product.images))
    )
    product = (await db.execute(stmt)).scalar_one_or_none()
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    return product


async def update_product(
    db: AsyncSession,
    ctx: TenantContext,
    product_id: UUID,
    data: dict,
) -> Product:
    product = await get_product(db, ctx, product_id)
    for key, value in data.items():
        setattr(product, key, value)
    audit.record(
        db, ctx.tenant_id, ctx.user_id, "product.updated", "Product",
        product.id, changes={k: {"new": v} for k, v in data.items()},
    )
    await db.commit()
    return product


# --- Variants ---

async def _get_variant(
    db: AsyncSession, ctx: TenantContext, variant_id: UUID,
) -> Variant:
    stmt = tenant_query(Variant, ctx.tenant_id).where(Variant.id == variant_id)
    variant = (await db.execute(stmt)).scalar_one_or_none()
    if variant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Variant not found")
    return variant


async def create_variant(
    db: AsyncSession,
    ctx: TenantContext,
    product_id: UUID,
    data: dict,
) -> Variant:
    await get_product(db, ctx, product_id)
    variant = Variant(tenant_id=ctx.tenant_id, product_id=product_id, **data)
    db.add(variant)
    await db.flush()
    audit.record(db, ctx.tenant_id, ctx.user_id, "variant.created", "Variant", variant.id)
    await db.commit()
    return variant


async def update_variant(
    db: AsyncSession,
    ctx: TenantContext,
    variant_id: UUID,
    data: dict,
) -> Variant:
    variant = await _get_variant(db, ctx, variant_id)
    for key, value in data.items():
        setattr(variant, key, value)
    audit.record(
        db, ctx.tenant_id, ctx.user_id, "variant.updated", "Variant",
        variant.id, changes={k: {"new": v} for k, v in data.items()},
    )
    await db.commit()
    return variant


async def delete_variant(
    db: AsyncSession,
    ctx: TenantContext,
    variant_id: UUID,
) -> None:
    variant = await _get_variant(db, ctx, variant_id)
    await db.delete(variant)
    audit.record(db, ctx.tenant_id, ctx.user_id, "variant.deleted", "Variant", variant_id)
    await db.commit()
