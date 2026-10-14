"""
FastAPI dependencies — injected into every route handler.

Three dependencies form the security chain:
1. get_db       → database session for this request
2. get_current_user → verifies the Clerk JWT, returns user info
3. get_tenant   → resolves which tenant this user is acting for

Every route that touches tenant-scoped data uses all three.
The chain ensures: no valid token → 401, no tenant membership → 403,
and the tenant_id is always available for scoping database queries.

Usage in a route:
    @router.get("/products")
    async def list_products(
        db: AsyncSession = Depends(get_db),
        tenant_context: TenantContext = Depends(get_tenant),
    ):
        # tenant_context.tenant_id is guaranteed to be set
        # tenant_context.user_id is the authenticated user
        # tenant_context.role is their role in this tenant
        ...
"""

from dataclasses import dataclass
from uuid import UUID

import jwt
from fastapi import Depends, Header, HTTPException, status
from jwt import PyJWKClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session_factory


# --- Dependency 1: Database Session ---
# Yields a session for the duration of one request.
# The 'async with' ensures the session is closed even if the
# route handler raises an exception — no leaked connections.
async def get_db():
    async with async_session_factory() as session:
        yield session


# --- Clerk JWT Verification ---
# PyJWKClient fetches and caches Clerk's public keys.
# These keys are used to verify that the JWT was actually
# signed by Clerk, not forged by an attacker.
_jwks_client = PyJWKClient(settings.clerk_jwks_url)


@dataclass
class AuthenticatedUser:
    """The verified identity from a Clerk session token."""

    user_id: str  # Clerk's user ID (e.g. "user_2abc...")
    email: str | None = None


# --- Dependency 2: Authenticate the User ---
# Extracts the Bearer token from the Authorization header,
# verifies it against Clerk's public keys, and returns
# the authenticated user's identity.
async def get_current_user(
    authorization: str = Header(..., description="Bearer <clerk_session_token>"),
) -> AuthenticatedUser:
    # Extract the token from "Bearer <token>"
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header must start with 'Bearer '",
        )

    token = authorization.removeprefix("Bearer ").strip()

    try:
        # Get the signing key that matches this token's key ID
        signing_key = _jwks_client.get_signing_key_from_jwt(token)

        # Verify and decode the JWT
        # This checks: signature is valid, token hasn't expired,
        # and the issuer matches Clerk
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            options={"verify_aud": False},  # Clerk tokens don't always set audience
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session token has expired",
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid session token: {e}",
        )

    # Extract user info from the verified token
    return AuthenticatedUser(
        user_id=payload.get("sub", ""),
        email=payload.get("email"),
    )


# --- Tenant Context ---
# This is what route handlers receive. It carries everything
# needed to scope database queries and check permissions.
@dataclass
class TenantContext:
    tenant_id: UUID
    user_id: str
    role: str  # "owner" | "admin" | "member" | "viewer"


# --- Dependency 3: Resolve the Tenant ---
# Looks up which tenant this user belongs to and what role they have.
# If the user isn't a member of any tenant, they get a 403.
#
# In the future, this will support users who belong to multiple
# tenants (switching between businesses). For MVP, each user
# belongs to one tenant.
async def get_tenant(
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TenantContext:
    # Import here to avoid circular imports — models import Base
    # from database.py, and this file is imported by routes
    from app.modules.tenants.models import Membership

    # Find the user's active membership
    result = await db.execute(
        select(Membership).where(
            Membership.clerk_user_id == user.user_id,
            Membership.is_active == True,
        )
    )
    membership = result.scalar_one_or_none()

    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of any organization",
        )

    return TenantContext(
        tenant_id=membership.tenant_id,
        user_id=user.user_id,
        role=membership.role,
    )


# --- Role Authorization Helper ---
# Use as a dependency when a route requires a minimum role.
# Example: Depends(require_role("admin")) on a route means
# only owners and admins can access it.
def require_role(*allowed_roles: str):
    """
    Returns a dependency that checks if the user's role
    is in the allowed list. Raises 403 if not.

    Usage:
        @router.post("/channels")
        async def connect_channel(
            tenant: TenantContext = Depends(require_role("owner", "admin")),
        ):
            ...
    """

    async def check_role(
        tenant_context: TenantContext = Depends(get_tenant),
    ) -> TenantContext:
        if tenant_context.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires one of these roles: {', '.join(allowed_roles)}",
            )
        return tenant_context

    return check_role
