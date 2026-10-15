"""
Channels service — marketplace connections and listings.

Credentials are encrypted before storage (see security.py).
"""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import tenant_query
from app.dependencies import TenantContext
from app.modules.audit import service as audit
from app.modules.channels.models import Channel, Listing
from app.security import encrypt_value


# --- Channels ---

async def create_channel(
    db: AsyncSession,
    ctx: TenantContext,
    data: dict,
) -> Channel:
    _encrypt_tokens(data)
    channel = Channel(tenant_id=ctx.tenant_id, **data)
    db.add(channel)
    await db.flush()
    audit.record(db, ctx.tenant_id, ctx.user_id, "channel.created", "Channel", channel.id)
    await db.commit()
    return channel


async def list_channels(
    db: AsyncSession,
    ctx: TenantContext,
) -> list[Channel]:
    stmt = tenant_query(Channel, ctx.tenant_id).order_by(Channel.created_at.desc())
    return list((await db.execute(stmt)).scalars())


async def get_channel(
    db: AsyncSession,
    ctx: TenantContext,
    channel_id: UUID,
) -> Channel:
    stmt = (
        tenant_query(Channel, ctx.tenant_id)
        .where(Channel.id == channel_id)
        .options(selectinload(Channel.listings))
    )
    channel = (await db.execute(stmt)).scalar_one_or_none()
    if channel is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Channel not found")
    return channel


async def update_channel(
    db: AsyncSession,
    ctx: TenantContext,
    channel_id: UUID,
    data: dict,
) -> Channel:
    channel = await get_channel(db, ctx, channel_id)
    _encrypt_tokens(data)
    for key, value in data.items():
        setattr(channel, key, value)
    audit.record(
        db, ctx.tenant_id, ctx.user_id, "channel.updated", "Channel", channel.id,
        changes={k: {"new": "(redacted)" if "token" in k else v} for k, v in data.items()},
    )
    await db.commit()
    return channel


# --- Listings ---

async def create_listing(
    db: AsyncSession,
    ctx: TenantContext,
    channel_id: UUID,
    data: dict,
) -> Listing:
    await get_channel(db, ctx, channel_id)
    listing = Listing(tenant_id=ctx.tenant_id, channel_id=channel_id, **data)
    db.add(listing)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Variant already listed on this channel")
    audit.record(db, ctx.tenant_id, ctx.user_id, "listing.created", "Listing", listing.id)
    await db.commit()
    return listing


async def list_listings(
    db: AsyncSession,
    ctx: TenantContext,
    channel_id: UUID,
) -> list[Listing]:
    await get_channel(db, ctx, channel_id)
    stmt = (
        tenant_query(Listing, ctx.tenant_id)
        .where(Listing.channel_id == channel_id)
        .order_by(Listing.created_at.desc())
    )
    return list((await db.execute(stmt)).scalars())


async def update_listing(
    db: AsyncSession,
    ctx: TenantContext,
    listing_id: UUID,
    data: dict,
) -> Listing:
    stmt = tenant_query(Listing, ctx.tenant_id).where(Listing.id == listing_id)
    listing = (await db.execute(stmt)).scalar_one_or_none()
    if listing is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Listing not found")
    for key, value in data.items():
        setattr(listing, key, value)
    audit.record(
        db, ctx.tenant_id, ctx.user_id, "listing.updated", "Listing", listing.id,
        changes={k: {"new": v} for k, v in data.items()},
    )
    await db.commit()
    return listing


def _encrypt_tokens(data: dict) -> None:
    """Encrypt credential fields in-place before they reach the model."""
    for key in ("encrypted_refresh_token", "encrypted_access_token"):
        if key in data and data[key] is not None:
            data[key] = encrypt_value(data[key])
