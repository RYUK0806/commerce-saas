"""
Tenant module models — the multi-tenancy foundation.

Three tables:
- Tenant: a business account (one per paying customer)
- User: a person who can log in (synced from Clerk)
- Membership: connects users to tenants with a role

Why three tables instead of two?
A user might eventually belong to multiple tenants (an agency
managing several clients). The membership table makes this possible
without duplicating user records.

Why store users in our DB when Clerk handles auth?
Clerk owns authentication (who are you?). Our DB owns authorization
(what can you do?). We need users in our DB so we can:
- Associate them with tenants via memberships
- Reference them in audit logs, orders, campaigns
- Query them without calling Clerk's API every time
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Tenant(Base):
    """
    A business account on the platform.

    Each tenant gets completely isolated data — products, inventory,
    orders, channels, campaigns. The tenant_id column on every
    data table traces back to this row.

    Maps to a Clerk Organization. When a business signs up and
    creates an org in Clerk, we create a matching Tenant row.
    """

    __tablename__ = "tenants"

    # Business identity
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Business name displayed in the dashboard",
    )

    slug: Mapped[str] = mapped_column(
        String(63),
        unique=True,
        nullable=False,
        comment="URL-safe identifier, e.g. 'acme-foods'",
    )

    # Clerk organization ID — links this tenant to Clerk's org
    clerk_org_id: Mapped[str | None] = mapped_column(
        String(255),
        unique=True,
        nullable=True,
        comment="Clerk organization ID (org_xxx)",
    )

    # Status
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        comment="Disabled tenants can't access the platform",
    )

    # Optional metadata
    logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Relationships
    memberships: Mapped[list["Membership"]] = relationship(
        back_populates="tenant",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Tenant {self.slug}>"


class User(Base):
    """
    A person who can log in to the platform.

    Synced from Clerk — Clerk is the source of truth for auth,
    our DB is the source of truth for what they can do here.

    A user can be a member of one or more tenants (businesses).
    """

    __tablename__ = "users"

    # Clerk user ID — the link between our DB and Clerk
    clerk_user_id: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        comment="Clerk user ID (user_xxx)",
    )

    # Profile info (synced from Clerk, can be updated)
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
    )

    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Account status
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
    )

    # Relationships
    memberships: Mapped[list["Membership"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User {self.email}>"


class Membership(Base):
    """
    Connects a user to a tenant with a specific role.

    This is the table that get_tenant() queries in dependencies.py.
    It answers: "which business is this user acting for, and what
    can they do there?"

    Roles:
    - owner: full access, can delete the tenant, manage billing
    - admin: manage products, channels, users (can't delete tenant)
    - member: day-to-day operations (add products, manage orders)
    - viewer: read-only access to dashboard and reports

    The unique constraint on (tenant_id, user_id) prevents a user
    from having two roles in the same tenant.
    """

    __tablename__ = "memberships"

    # Foreign keys
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Clerk user ID — denormalized here so get_tenant() can query
    # by clerk_user_id without joining the users table.
    # This avoids an extra JOIN on every single authenticated request.
    clerk_user_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Denormalized from users.clerk_user_id for fast lookup",
    )

    # Role within this tenant
    role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="member",
        server_default="member",
        comment="owner | admin | member | viewer",
    )

    # Can be deactivated without deleting the row (preserves audit trail)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
    )

    # When they joined this tenant
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship(back_populates="memberships")
    user: Mapped["User"] = relationship(back_populates="memberships")

    # Constraints
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_membership_tenant_user"),
    )

    def __repr__(self) -> str:
        return f"<Membership user={self.clerk_user_id} tenant={self.tenant_id} role={self.role}>"
