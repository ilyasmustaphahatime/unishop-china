"""A private, unique user/product association; product data stays canonical."""
from datetime import datetime

from sqlalchemy import CHAR, DateTime, ForeignKey, Index
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import utc_now


class ProductFavorite(Base):
    __tablename__ = "product_favorites"
    __table_args__ = (
        Index("ix_product_favorites_user_time", "user_id", "favorited_at", "product_listing_id"),
        Index("ix_product_favorites_listing", "product_listing_id"),
    )

    user_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("users.id", name="fk_product_favorites_user", ondelete="CASCADE"),
        primary_key=True,
    )
    product_listing_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("product_listings.id", name="fk_product_favorites_listing",
                             ondelete="CASCADE"), primary_key=True,
    )
    favorited_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True).with_variant(DATETIME(fsp=6), "mysql"),
        default=utc_now, nullable=False,
    )
