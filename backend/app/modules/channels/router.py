"""
Channel routes — marketplace connections and listings.

Channel management requires owner or admin role.
"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import TenantContext, get_db, require_role
from app.modules.channels import service

router = APIRouter(prefix="/channels", tags=["channels"])


# --- Schemas ---

class ChannelCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    platform: str = Field(max_length=50)
    name: str = Field(min_length=1, max_length=255)
    external_account_id: str | None = Field(default=None, max_length=255)
    marketplace_id: str | None = Field(default=None, max_length=50)
    encrypted_refresh_token: str | None = None
    encrypted_access_token: str | None = None
    config: dict | None = None


class ChannelUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=255)
    status: str | None = Field(default=None, pattern=r"^(pending|connected|disconnected|error)$")
    status_message: str | None = None
    encrypted_refresh_token: str | None = None
    encrypted_access_token: str | None = None
    access_token_expires_at: datetime | None = None
    config: dict | None = None
    is_active: bool | None = None


class ListingCreate(BaseModel):
    variant_id: UUID
    external_listing_id: str | None = Field(default=None, max_length=255)
    external_url: str | None = None


class ListingUpdate(BaseModel):
    status: str | None = Field(default=None, pattern=r"^(draft|pending|active|error|suppressed|inactive)$")
    status_message: str | None = None
    external_listing_id: str | None = None
    external_url: str | None = None
    last_synced_price: str | None = None
    last_synced_quantity: int | None = None
    last_synced_at: datetime | None = None
    channel_data: dict | None = None


# --- Helpers ---

def _channel_out(c) -> dict:
    return {
        "id": c.id,
        "platform": c.platform,
        "name": c.name,
        "external_account_id": c.external_account_id,
        "status": c.status,
        "status_message": c.status_message,
        "last_sync_at": c.last_sync_at,
        "is_active": c.is_active,
        "created_at": c.created_at,
    }


def _listing_out(l) -> dict:
    return {
        "id": l.id,
        "channel_id": l.channel_id,
        "variant_id": l.variant_id,
        "external_listing_id": l.external_listing_id,
        "external_url": l.external_url,
        "status": l.status,
        "status_message": l.status_message,
        "last_synced_price": l.last_synced_price,
        "last_synced_quantity": l.last_synced_quantity,
        "last_synced_at": l.last_synced_at,
    }


# --- Channel routes ---

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_channel(
    body: ChannelCreate,
    ctx: TenantContext = Depends(require_role("owner", "admin")),
    db: AsyncSession = Depends(get_db),
):
    channel = await service.create_channel(db, ctx, body.model_dump(exclude_unset=True))
    return _channel_out(channel)


@router.get("")
async def list_channels(
    ctx: TenantContext = Depends(require_role("owner", "admin")),
    db: AsyncSession = Depends(get_db),
):
    return [_channel_out(c) for c in await service.list_channels(db, ctx)]


@router.get("/{channel_id}")
async def get_channel(
    channel_id: UUID,
    ctx: TenantContext = Depends(require_role("owner", "admin")),
    db: AsyncSession = Depends(get_db),
):
    return _channel_out(await service.get_channel(db, ctx, channel_id))


@router.patch("/{channel_id}")
async def update_channel(
    channel_id: UUID,
    body: ChannelUpdate,
    ctx: TenantContext = Depends(require_role("owner", "admin")),
    db: AsyncSession = Depends(get_db),
):
    data = body.model_dump(exclude_unset=True)
    if not data:
        return _channel_out(await service.get_channel(db, ctx, channel_id))
    return _channel_out(await service.update_channel(db, ctx, channel_id, data))


# --- Listing routes ---

@router.post("/{channel_id}/listings", status_code=status.HTTP_201_CREATED)
async def create_listing(
    channel_id: UUID,
    body: ListingCreate,
    ctx: TenantContext = Depends(require_role("owner", "admin")),
    db: AsyncSession = Depends(get_db),
):
    return _listing_out(await service.create_listing(db, ctx, channel_id, body.model_dump()))


@router.get("/{channel_id}/listings")
async def list_listings(
    channel_id: UUID,
    ctx: TenantContext = Depends(require_role("owner", "admin")),
    db: AsyncSession = Depends(get_db),
):
    return [_listing_out(l) for l in await service.list_listings(db, ctx, channel_id)]


@router.patch("/listings/{listing_id}")
async def update_listing(
    listing_id: UUID,
    body: ListingUpdate,
    ctx: TenantContext = Depends(require_role("owner", "admin")),
    db: AsyncSession = Depends(get_db),
):
    data = body.model_dump(exclude_unset=True)
    if not data:
        return _listing_out(await service.update_listing(db, ctx, listing_id, {}))
    return _listing_out(await service.update_listing(db, ctx, listing_id, data))
