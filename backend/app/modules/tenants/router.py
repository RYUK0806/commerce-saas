"""
Tenant routes — onboarding and membership management.

POST /tenants uses get_current_user (no tenant yet).
All other routes use get_tenant (caller must be a member).
"""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import AuthenticatedUser, TenantContext, get_current_user, get_db, get_tenant
from app.modules.tenants import service
from app.modules.tenants.models import Membership

router = APIRouter(prefix="/tenants", tags=["tenants"])


# --- Schemas ---

class TenantCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(max_length=63, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")


class MemberAdd(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    clerk_user_id: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=1, max_length=255)
    role: str = Field(default="member", pattern=r"^(owner|admin|member|viewer)$")


class RoleUpdate(BaseModel):
    role: str = Field(pattern=r"^(owner|admin|member|viewer)$")


# --- Routes ---

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_tenant(
    body: TenantCreate,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant = await service.create_tenant_with_owner(db, user, body.name, body.slug)
    return {"id": tenant.id, "name": tenant.name, "slug": tenant.slug}


@router.get("/members")
async def list_members(
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Membership).where(
            Membership.tenant_id == ctx.tenant_id,
            Membership.is_active == True,
        )
    )
    return [
        {"id": m.id, "clerk_user_id": m.clerk_user_id, "role": m.role, "joined_at": m.joined_at}
        for m in result.scalars()
    ]


@router.post("/members", status_code=status.HTTP_201_CREATED)
async def add_member(
    body: MemberAdd,
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    m = await service.add_member(db, ctx, body.clerk_user_id, body.email, body.role)
    return {"id": m.id, "clerk_user_id": m.clerk_user_id, "role": m.role}


@router.patch("/members/{membership_id}/role")
async def change_role(
    membership_id: UUID,
    body: RoleUpdate,
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    m = await service.change_role(db, ctx, membership_id, body.role)
    return {"id": m.id, "clerk_user_id": m.clerk_user_id, "role": m.role}


@router.delete("/members/{membership_id}", status_code=status.HTTP_200_OK)
async def deactivate_member(
    membership_id: UUID,
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    await service.deactivate_member(db, ctx, membership_id)
    return {"detail": "Member removed"}
