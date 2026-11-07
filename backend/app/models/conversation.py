"""Private product conversation identities; history survives lifecycle changes."""
from datetime import datetime
import secrets

from sqlalchemy import CHAR, CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import UUIDPrimaryKeyMixin, utc_now


class Conversation(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("public_ref", name="uq_conversations_public_ref"),
        UniqueConstraint("buyer_user_id", "seller_user_id", "product_listing_id",
                         name="uq_conversations_participants_product"),
        CheckConstraint("buyer_user_id <> seller_user_id", name="ck_conversations_distinct_users"),
        CheckConstraint("REGEXP_LIKE(public_ref, '^cv-[0-9a-f]{32}$', 'c')",
                        name="ck_conversations_public_ref"),
        Index("ix_conversations_buyer_activity", "buyer_user_id", "activity_at", "public_ref"),
        Index("ix_conversations_seller_activity", "seller_user_id", "activity_at", "public_ref"),
        Index("ix_conversations_product", "product_listing_id"),
    )

    public_ref: Mapped[str] = mapped_column(
        String(35, collation="ascii_bin"), default=lambda: "cv-" + secrets.token_hex(16),
        nullable=False,
    )
    buyer_user_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("users.id", name="fk_conversations_buyer", ondelete="RESTRICT"),
        nullable=False,
    )
    seller_user_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("users.id", name="fk_conversations_seller", ondelete="RESTRICT"),
        nullable=False,
    )
    product_listing_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("product_listings.id", name="fk_conversations_product",
                             ondelete="RESTRICT"), nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True).with_variant(DATETIME(fsp=6), "mysql"),
        default=utc_now, nullable=False,
    )
    activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True).with_variant(DATETIME(fsp=6), "mysql"),
        default=utc_now, nullable=False,
    )
