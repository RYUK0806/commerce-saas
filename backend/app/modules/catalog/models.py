"""
Catalog module models — products, variants, and images.

The key distinction your spec makes clear:

  Product  = what the business sells (Anva A2 Bilona Cow Ghee)
  Variant  = a specific sellable unit (1 litre jar, 500ml jar)
  SKU      = the variant's unique stock-keeping code (ANVA-GHEE-1L)

A Product has one or more Variants.
A Variant has exactly one SKU.
A Variant maps to one or more channel Listings (Amazon, Google, etc.)
  — but listings live in the channels module, not here.

Inventory tracks quantities per Variant (via SKU), not per Product.
You don't have "45 jars of ghee" — you have "45 jars of the 1L variant."

All three tables are tenant-scoped: every query MUST filter by tenant_id.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Product(Base):
    """
    A product in the catalog — the top-level "thing" a business sells.

    Examples: "Anva A2 Bilona Cow Ghee", "Premium Moisturizer",
    "USB-C Cable 3-pack"

    A product holds the shared info (name, brand, description, category).
    The sellable specifics (size, weight, price, SKU) live on Variants.
    """

    __tablename__ = "products"

    # --- Tenant isolation ---
    # Every query must include WHERE tenant_id = :tenant_id
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="The business this product belongs to",
    )

    # --- Product identity ---
    name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Product name shown in the dashboard",
    )

    brand: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Brand name (a tenant can have multiple brands)",
    )

    category: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Product category, e.g. 'Cooking Oils', 'Skincare'",
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Full product description (can be AI-assisted)",
    )

    # --- Status ---
    # draft: being set up, not visible anywhere
    # active: available for listing on channels
    # archived: removed from sale but kept for history
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="draft",
        server_default="draft",
        comment="draft | active | archived",
    )

    # --- Flexible attributes ---
    # Different product categories need different fields.
    # Ghee needs "cow breed" and "process type".
    # Electronics needs "wattage" and "voltage".
    # JSONB lets each product store category-specific attributes
    # without us adding columns for every possible field.
    attributes: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        default=dict,
        comment="Category-specific attributes as key-value pairs",
    )

    # --- Tax & shipping ---
    hsn_code: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="HSN/HS code for tax classification (India: GST)",
    )

    tax_rate: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2),
        nullable=True,
        comment="Tax percentage, e.g. 12.00 for 12% GST",
    )

    # --- Relationships ---
    variants: Mapped[list["Variant"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="Variant.sort_order",
    )

    images: Mapped[list["ProductImage"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductImage.sort_order",
    )

    __table_args__ = (
        # Index for the most common query: "list all products for this tenant"
        # tenant_id + status covers filtered listing pages
        {"comment": "Tenant-scoped product catalog"},
    )

    def __repr__(self) -> str:
        return f"<Product {self.name}>"


class Variant(Base):
    """
    A specific sellable unit of a product.

    Product "Anva A2 Ghee" might have variants:
      - 1 litre jar   (SKU: ANVA-GHEE-1L,  price: ₹899)
      - 500ml jar     (SKU: ANVA-GHEE-500, price: ₹499)
      - 200ml jar     (SKU: ANVA-GHEE-200, price: ₹249)

    Each variant has its own SKU, price, weight, and barcode.
    Inventory is tracked per variant, not per product.
    Channel listings map to variants, not products.
    """

    __tablename__ = "variants"

    # --- Tenant isolation (denormalized for query performance) ---
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    # --- Parent product ---
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )

    # --- Variant identity ---
    sku: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Stock Keeping Unit — unique within a tenant",
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Variant label, e.g. '1 Litre Jar', 'Pack of 3'",
    )

    # --- Pricing ---
    # Using Numeric (not Float!) for money — floats lose precision.
    # 0.1 + 0.2 = 0.30000000000000004 with float.
    # Numeric stores exact decimal values.
    price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        comment="Selling price in the tenant's currency",
    )

    compare_at_price: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
        comment="Original price before discount (for strikethrough display)",
    )

    cost_price: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
        comment="What you paid for it — used for margin calculations",
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="INR",
        server_default="INR",
        comment="ISO 4217 currency code",
    )

    # --- Physical attributes ---
    weight_grams: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Weight in grams (for shipping calculations)",
    )

    barcode: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="EAN/UPC barcode — needed for Amazon listings",
    )

    # --- Status ---
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        comment="Inactive variants can't be listed or sold",
    )

    # --- Display order ---
    sort_order: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        comment="Controls variant order in the UI",
    )

    # --- Flexible attributes ---
    attributes: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        default=dict,
        comment="Variant-specific attributes (color, material, etc.)",
    )

    # --- Relationships ---
    product: Mapped["Product"] = relationship(back_populates="variants")

    __table_args__ = (
        # SKU must be unique within a tenant — two businesses can
        # both use SKU "GHEE-1L", but one business can't have
        # two variants with the same SKU.
        UniqueConstraint("tenant_id", "sku", name="uq_variant_tenant_sku"),
    )

    def __repr__(self) -> str:
        return f"<Variant {self.sku}>"


class ProductImage(Base):
    """
    An image attached to a product.

    Images are stored in S3. This table holds the reference URL
    and metadata. Images belong to the product (not the variant)
    because typically all variants of a product share the same
    photos. If you need variant-specific images later, add a
    nullable variant_id column.
    """

    __tablename__ = "product_images"

    # --- Tenant isolation ---
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    # --- Parent product ---
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )

    # --- Image data ---
    url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="S3 URL of the image",
    )

    alt_text: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Alt text for accessibility and SEO",
    )

    # --- Display ---
    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        comment="The main image shown in product lists",
    )

    sort_order: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        comment="Controls image order in galleries",
    )

    def __repr__(self) -> str:
        return f"<ProductImage product={self.product_id} primary={self.is_primary}>"
