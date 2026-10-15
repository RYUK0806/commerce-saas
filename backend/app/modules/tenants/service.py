"""
Tenant service — onboarding, membership management.

Services commit their own transaction (see audit/service.py).
"""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import AuthenticatedUser, TenantContext
from app.modules.audit import service as audit
from app.modules.tenants.models import Membership, Tenant, User

_ROLES = ("owner", "admin", "member", "viewer")
_MANAGE_ROLES = ("owner", "admin")


async def create_tenant_with_owner(
    db: AsyncSession,
    user: AuthenticatedUser,
    tenant_name: str,
    slug: str,
) -> Tenant:
    """Create a tenant with the caller as owner, creating their User row if new."""
    if user.email is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session token has no email claim — add it in Clerk's session token settings",
        )

    db_user = await db.scalar(select(User).where(User.clerk_user_id == user.user_id))
    if db_user is None:
        db_user = User(clerk_user_id=user.user_id, email=user.email)
        db.add(db_user)
    elif await db.scalar(
        select(Membership.id).where(Membership.user_id == db_user.id, Membership.is_active == True)
    ):
        # shortcut: one tenant per user (MVP); lift when tenant switching exists
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already belong to an organization",
        )

    tenant = Tenant(name=tenant_name, slug=slug)
    db.add(tenant)
    db.add(Membership(tenant=tenant, user=db_user, clerk_user_id=user.user_id, role="owner"))

    try:
        # Flush assigns tenant.id for the audit row and surfaces unique violations
        await db.flush()
        audit.record(db, tenant.id, user.user_id, "tenant.created", "Tenant", tenant.id)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        # slug, or this email already used by another Clerk user
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That organization URL or email is already in use",
        )

    return tenant


def _require_manage(ctx: TenantContext) -> None:
    if ctx.role not in _MANAGE_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Requires owner or admin role")


async def add_member(
    db: AsyncSession,
    ctx: TenantContext,
    clerk_user_id: str,
    email: str,
    role: str = "member",
) -> Membership:
    """Invite a user to the tenant. Creates their User row if new."""
    _require_manage(ctx)
    if role not in _ROLES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Invalid role: {role}")

    db_user = await db.scalar(select(User).where(User.clerk_user_id == clerk_user_id))
    if db_user is None:
        db_user = User(clerk_user_id=clerk_user_id, email=email)
        db.add(db_user)

    membership = Membership(
        tenant_id=ctx.tenant_id, user=db_user, clerk_user_id=clerk_user_id, role=role,
    )
    db.add(membership)

    try:
        await db.flush()
        audit.record(db, ctx.tenant_id, ctx.user_id, "membership.created", "Membership", membership.id)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "User is already a member of this organization")

    return membership


async def change_role(
    db: AsyncSession,
    ctx: TenantContext,
    membership_id: UUID,
    new_role: str,
) -> Membership:
    """Change a member's role. Only owners can create other owners."""
    _require_manage(ctx)
    if new_role not in _ROLES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Invalid role: {new_role}")
    if new_role == "owner" and ctx.role != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only owners can grant owner role")

    membership = await db.scalar(
        select(Membership).where(
            Membership.id == membership_id,
            Membership.tenant_id == ctx.tenant_id,
            Membership.is_active == True,
        )
    )
    if membership is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Membership not found")

    old_role = membership.role
    if old_role == new_role:
        return membership

    membership.role = new_role
    audit.record(
        db, ctx.tenant_id, ctx.user_id, "membership.role_changed", "Membership",
        membership.id, changes={"role": {"old": old_role, "new": new_role}},
    )
    await db.commit()
    return membership


async def deactivate_member(
    db: AsyncSession,
    ctx: TenantContext,
    membership_id: UUID,
) -> Membership:
    """Soft-delete a membership. Owners can't deactivate themselves."""
    _require_manage(ctx)

    membership = await db.scalar(
        select(Membership).where(
            Membership.id == membership_id,
            Membership.tenant_id == ctx.tenant_id,
            Membership.is_active == True,
        )
    )
    if membership is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Membership not found")
    if membership.clerk_user_id == ctx.user_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot remove yourself")

    membership.is_active = False
    audit.record(db, ctx.tenant_id, ctx.user_id, "membership.deactivated", "Membership", membership.id)
    await db.commit()
    return membership
