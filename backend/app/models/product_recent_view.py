"""Bounded private viewing history, one timestamp per user/product pair."""
from datetime import datetime

from sqlalchemy import CHAR, DateTime, ForeignKey, Index
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import utc_now


class ProductRecentView(Base):
    __tablename__ = "product_recent_views"
    __table_args__ = (
        Index("ix_product_recent_views_user_time", "user_id", "last_viewed_at",
              "product_listing_id"),
        Index("ix_product_recent_views_listing", "product_listing_id"),
    )

    user_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("users.id", name="fk_product_recent_views_user", ondelete="CASCADE"),
        primary_key=True,
    )
    product_listing_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("product_listings.id", name="fk_product_recent_views_listing",
                             ondelete="CASCADE"), primary_key=True,
    )
    last_viewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True).with_variant(DATETIME(fsp=6), "mysql"),
        default=utc_now, nullable=False,
    )
