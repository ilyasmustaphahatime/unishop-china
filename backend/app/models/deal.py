"""An immutable agreement, not a payment or delivery record."""
from datetime import datetime
import secrets

from sqlalchemy import CHAR, CheckConstraint, DateTime, ForeignKeyConstraint, Index, String, UniqueConstraint, inspect
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.core.database import Base
from app.models.base import UUIDPrimaryKeyMixin


class Deal(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "deals"
    __table_args__ = (
        UniqueConstraint("public_ref", name="uq_deals_public_ref"),
        UniqueConstraint("accepted_offer_id", name="uq_deals_offer"),
        UniqueConstraint("product_listing_id", name="uq_deals_product"),
        ForeignKeyConstraint(["accepted_offer_id", "product_listing_id"], ["offers.id", "offers.product_listing_id"], name="fk_deals_offer_product", ondelete="RESTRICT"),
        ForeignKeyConstraint(["product_listing_id"], ["product_listings.id"], name="fk_deals_product", ondelete="RESTRICT"),
        CheckConstraint("REGEXP_LIKE(public_ref, '^dl-[0-9a-f]{32}$', 'c')", name="ck_deals_ref"),
        CheckConstraint("CHAR_LENGTH(TRIM(product_title_snapshot)) BETWEEN 3 AND 120", name="ck_deals_title"),
        CheckConstraint("product_condition_snapshot IN ('new','like_new','good','fair')", name="ck_deals_condition"),
        Index("ix_deals_agreed", "agreed_at", "public_ref"),
    )
    public_ref: Mapped[str] = mapped_column(String(35, collation="ascii_bin"), default=lambda: "dl-" + secrets.token_hex(16), nullable=False)
    accepted_offer_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    product_listing_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    agreed_at: Mapped[datetime] = mapped_column(DateTime().with_variant(DATETIME(fsp=6), "mysql"), nullable=False)
    product_title_snapshot: Mapped[str] = mapped_column(String(120), nullable=False)
    product_condition_snapshot: Mapped[str] = mapped_column(String(16), nullable=False)

    @validates("public_ref", "accepted_offer_id", "product_listing_id", "agreed_at", "product_title_snapshot", "product_condition_snapshot")
    def immutable_agreement(self, key, value):
        # An unloaded persisted snapshot must not become writable after expiry.
        if inspect(self).has_identity and key not in self.__dict__:
            raise ValueError("Agreement cannot be changed.")
        if key in self.__dict__ and self.__dict__[key] != value:
            raise ValueError("Agreement cannot be changed.")
        return value
