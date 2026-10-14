"""
Channels module models — marketplace connections and listings.

Two tables:

  Channel    = a connected marketplace account (Amazon Seller Central)
  Listing    = a variant published to a channel (one Amazon ASIN)

The adapter pattern:
  Channel stores the connection (credentials, status, config).
  The adapter code (channels/adapters/amazon.py) knows HOW to talk
  to that marketplace. The model doesn't care whether it's Amazon,
  Google, or a future marketplace — it just stores the connection.

Credential security:
  OAuth tokens (refresh_token, access_token) are encrypted at rest
  using Fernet (see security.py). The database never holds plaintext
  tokens. encrypt_value() before saving, decrypt_value() before using.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Channel(Base):
    """
    A connected marketplace account.

    When a business connects their Amazon Seller Central account,
    we create a Channel row. It holds:
    - Which marketplace (amazon, google_merchant, etc.)
    - Encrypted OAuth credentials
    - Sync status and last sync time
    - Channel-specific config

    One tenant can have multiple channels (Amazon US + Amazon India,
    or Amazon + Google Merchant).
    """

    __tablename__ = "channels"

    # --- Tenant isolation ---
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    # --- Channel identity ---
    platform: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="amazon | google_merchant | shopify (future)",
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Display name, e.g. 'Amazon India', 'Amazon US'",
    )

    # --- Marketplace account info ---
    # The seller/merchant ID on that platform
    external_account_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Seller ID on the marketplace (Amazon merchant ID, etc.)",
    )

    marketplace_id: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Amazon marketplace ID (e.g. A21TJRUUN4KGV for India)",
    )

    # --- Credentials (ENCRYPTED) ---
    # These are Fernet-encrypted strings. Never store plaintext tokens.
    # Use security.encrypt_value() before saving.
    # Use security.decrypt_value() before using.
    encrypted_refresh_token: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Fernet-encrypted OAuth refresh token",
    )

    encrypted_access_token: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Fernet-encrypted OAuth access token (short-lived)",
    )

    access_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the access token expires — refresh before this",
    )

    # --- Connection status ---
    # connected: credentials are valid, sync is working
    # disconnected: credentials expired or were revoked
    # error: last sync failed, needs attention
    # pending: OAuth flow started but not completed
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
        comment="pending | connected | disconnected | error",
    )

    status_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Human-readable status detail, e.g. error message",
    )

    # --- Sync tracking ---
    last_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last successful sync with this channel",
    )

    last_order_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last successful order import from this channel",
    )

    # --- Channel-specific config ---
    config: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        default=dict,
        comment="Platform-specific settings (fulfillment type, sync interval, etc.)",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
    )

    # --- Relationships ---
    listings: Mapped[list["Listing"]] = relationship(
        back_populates="channel",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Channel {self.platform}:{self.name} status={self.status}>"


class Listing(Base):
    """
    A variant published to a specific channel.

    This is the bridge between YOUR inventory and THE MARKETPLACE.

    Your Variant (SKU: ANVA-GHEE-1L) can have:
    - A Listing on Amazon India (ASIN: B0XXXXX)
    - A Listing on Amazon US (ASIN: B0YYYYY)
    - A Listing on Google Merchant (offer ID: ghee-1l)

    Each listing tracks:
    - The external ID on that platform (ASIN, offer ID)
    - What was last synced (price, quantity, title)
    - Whether the listing is live, pending, or has errors

    The UniqueConstraint on (channel_id, variant_id) prevents
    listing the same variant twice on the same channel.
    The constraint on (channel_id, external_listing_id) prevents
    two variants mapping to the same ASIN on the same channel.
    """

    __tablename__ = "listings"

    # --- Tenant isolation ---
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    # --- Which channel and which variant ---
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
    )

    variant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("variants.id", ondelete="CASCADE"),
        nullable=False,
    )

    # --- External identity ---
    external_listing_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="ID on the marketplace (Amazon ASIN, Google offer ID)",
    )

    external_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Direct link to the listing on the marketplace",
    )

    # --- Listing status ---
    # draft: created locally, not yet pushed
    # pending: push requested, waiting for marketplace confirmation
    # active: live on the marketplace
    # error: push failed, see status_message
    # suppressed: marketplace removed it (policy, missing info, etc.)
    # inactive: manually paused by the user
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="draft",
        server_default="draft",
        comment="draft | pending | active | error | suppressed | inactive",
    )

    status_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Error details or marketplace feedback",
    )

    # --- Last synced values ---
    # What we last successfully sent to the marketplace.
    # Comparing these to current variant data tells us what
    # needs syncing next.
    last_synced_price: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Price as last sent to the channel",
    )

    last_synced_quantity: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Stock quantity as last sent to the channel",
    )

    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # --- Channel-specific data ---
    channel_data: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        default=dict,
        comment="Platform-specific listing data (Amazon category, Google attributes)",
    )

    # --- Relationships ---
    channel: Mapped["Channel"] = relationship(back_populates="listings")

    variant: Mapped["Variant"] = relationship(
        "app.modules.catalog.models.Variant",
    )

    __table_args__ = (
        # One listing per variant per channel
        UniqueConstraint(
            "channel_id", "variant_id",
            name="uq_listing_channel_variant",
        ),
        # One external ID per channel (can't map two variants to same ASIN)
        UniqueConstraint(
            "channel_id", "external_listing_id",
            name="uq_listing_channel_external_id",
        ),
    )

    def __repr__(self) -> str:
        return f"<Listing channel={self.channel_id} external={self.external_listing_id}>"
