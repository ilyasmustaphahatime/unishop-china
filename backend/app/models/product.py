"""Listing core: no media, orders, or speculative marketplace fields."""
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, validates
from app.common.product_slugs import generate_product_slug, validate_product_slug
from app.core.database import Base
from app.models.base import UUIDTimestampMixin


class ProductStatus(StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    PAUSED = "PAUSED"
    ARCHIVED = "ARCHIVED"


class ProductCondition(StrEnum):
    NEW = "new"
    LIKE_NEW = "like_new"
    GOOD = "good"
    FAIR = "fair"


class ProductListing(UUIDTimestampMixin, Base):
    __tablename__ = "product_listings"
    __table_args__ = (
        UniqueConstraint("public_slug", name="uq_product_listings_public_slug"),
        CheckConstraint("REGEXP_LIKE(public_slug, '^item-[0-9a-f]{24}$', 'c')", name="ck_product_listing_slug"),
        CheckConstraint("CHAR_LENGTH(TRIM(title)) BETWEEN 3 AND 120", name="ck_product_listing_title"),
        CheckConstraint("CHAR_LENGTH(TRIM(description)) BETWEEN 10 AND 5000", name="ck_product_listing_description"),
        CheckConstraint("price > 0 AND price <= 9999999999.99", name="ck_product_listing_price"),
        CheckConstraint("currency = 'CNY'", name="ck_product_listing_currency"),
        CheckConstraint("`condition` IN ('new','like_new','good','fair')", name="ck_product_listing_condition"),
        CheckConstraint("status IN ('DRAFT','PUBLISHED','PAUSED','ARCHIVED')", name="ck_product_listing_status"),
        CheckConstraint("(status = 'DRAFT' AND published_at IS NULL) OR "
                        "(status IN ('PUBLISHED','PAUSED') AND published_at IS NOT NULL) OR status = 'ARCHIVED'",
                        name="ck_product_listing_publication"),
        Index("ix_product_listings_owner_updated", "seller_user_id", "updated_at", "id"),
        Index("ix_product_listings_city", "city_id"),
        Index("ix_product_listings_category", "category_id"),
        Index("ix_product_listings_browse_newest", "status", "published_at", "public_slug"),
        Index("ix_product_listings_browse_price", "status", "price", "public_slug"),
        Index("ix_product_listings_city_newest", "status", "city_id", "published_at", "public_slug"),
        Index("ix_product_listings_city_price", "status", "city_id", "price", "public_slug"),
        Index("ix_product_listings_category_newest", "status", "category_id", "published_at", "public_slug"),
        Index("ix_product_listings_category_price", "status", "category_id", "price", "public_slug"),
        Index("ix_product_listings_search_ngram", "title", "description",
              mysql_prefix="FULLTEXT", mysql_with_parser="ngram"),
    )
    seller_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", name="fk_product_listings_seller", ondelete="RESTRICT"), nullable=False, active_history=True)
    public_slug: Mapped[str] = mapped_column(String(29, collation="ascii_bin"), default=generate_product_slug, nullable=False, active_history=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="CNY", server_default="CNY", nullable=False)
    condition: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=ProductStatus.DRAFT, server_default="DRAFT", nullable=False)
    city_id: Mapped[str] = mapped_column(ForeignKey("cities.id", name="fk_product_listings_city", ondelete="RESTRICT"), nullable=False)
    category_id: Mapped[str] = mapped_column(ForeignKey("categories.id", name="fk_product_listings_category", ondelete="RESTRICT"), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @validates("public_slug", "seller_user_id")
    def immutable_identity(self, key: str, value: str) -> str:
        if key == "public_slug":
            value = validate_product_slug(value)
        previous = self.__dict__.get(key)
        if previous is not None and previous != value:
            raise ValueError("Listing identity cannot be changed.")
        return value
