"""Immutable proposal terms; closure fields are changed only by the service."""
from datetime import datetime
from decimal import Decimal
import secrets

from sqlalchemy import CHAR, CheckConstraint, Computed, DateTime, ForeignKeyConstraint, Index, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.core.database import Base
from app.models.base import UUIDPrimaryKeyMixin


class Offer(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "offers"
    __table_args__ = (
        UniqueConstraint("public_ref", name="uq_offers_public_ref"),
        UniqueConstraint("id", "conversation_id", name="uq_offers_id_conversation"),
        UniqueConstraint("id", "product_listing_id", name="uq_offers_id_product"),
        UniqueConstraint("conversation_id", "proposer_role", "client_offer_id", name="uq_offers_client_id"),
        UniqueConstraint("conversation_id", "active_slot", name="uq_offers_pending"),
        UniqueConstraint("parent_offer_id", name="uq_offers_parent"),
        ForeignKeyConstraint(["conversation_id", "product_listing_id"],
                             ["conversations.id", "conversations.product_listing_id"],
                             name="fk_offers_conversation_product", ondelete="RESTRICT"),
        ForeignKeyConstraint(["product_listing_id"], ["product_listings.id"],
                             name="fk_offers_product", ondelete="RESTRICT"),
        ForeignKeyConstraint(["parent_offer_id", "conversation_id"], ["offers.id", "offers.conversation_id"],
                             name="fk_offers_parent_conversation", ondelete="RESTRICT"),
        CheckConstraint("REGEXP_LIKE(public_ref, '^of-[0-9a-f]{32}$', 'c')", name="ck_offers_ref"),
        CheckConstraint("REGEXP_LIKE(client_offer_id, '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', 'c')", name="ck_offers_client"),
        CheckConstraint("amount > 0 AND amount <= 9999999999.99 AND currency = 'CNY'", name="ck_offers_money"),
        CheckConstraint("proposer_role IN ('BUYER','SELLER') AND (parent_offer_id IS NOT NULL OR proposer_role = 'BUYER')", name="ck_offers_role"),
        CheckConstraint("parent_offer_id IS NULL OR parent_offer_id <> id", name="ck_offers_parent"),
        CheckConstraint("status IN ('PENDING','ACCEPTED','REJECTED','WITHDRAWN','COUNTERED','EXPIRED','CANCELLED')", name="ck_offers_status"),
        CheckConstraint("TIMESTAMPDIFF(MICROSECOND, created_at, expires_at) = 86400000000 AND (closed_at IS NULL OR closed_at >= created_at)", name="ck_offers_dates"),
        CheckConstraint(
            "(status = 'PENDING' AND closed_at IS NULL AND closed_by_role IS NULL AND closure_reason IS NULL) OR "
            "(status IN ('ACCEPTED','REJECTED','COUNTERED','WITHDRAWN') AND closed_at IS NOT NULL AND closed_at < expires_at "
            "AND closed_by_role IS NOT NULL AND closed_by_role IN ('BUYER','SELLER') AND closure_reason IS NULL "
            "AND ((status = 'WITHDRAWN' AND closed_by_role = proposer_role) OR (status <> 'WITHDRAWN' AND closed_by_role <> proposer_role))) OR "
            "(status = 'EXPIRED' AND closed_at IS NOT NULL AND closed_at = expires_at AND closed_by_role IS NULL AND closure_reason IS NOT NULL AND closure_reason = 'EXPIRED') OR "
            "(status = 'CANCELLED' AND closed_at IS NOT NULL AND closed_by_role IS NULL AND closure_reason IS NOT NULL AND closure_reason = 'PRODUCT_UNAVAILABLE')",
            name="ck_offers_closure"),
        Index("ix_offers_conversation_created", "conversation_id", "created_at", "public_ref"),
        Index("ix_offers_product_status", "product_listing_id", "status", "public_ref"),
        Index("ix_offers_created", "created_at", "public_ref"),
    )
    public_ref: Mapped[str] = mapped_column(String(35, collation="ascii_bin"), default=lambda: "of-" + secrets.token_hex(16), nullable=False)
    conversation_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    product_listing_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    parent_offer_id: Mapped[str | None] = mapped_column(CHAR(36))
    proposer_role: Mapped[str] = mapped_column(String(6), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="CNY", nullable=False)
    client_offer_id: Mapped[str] = mapped_column(String(36, collation="ascii_bin"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="PENDING", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime().with_variant(DATETIME(fsp=6), "mysql"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime().with_variant(DATETIME(fsp=6), "mysql"), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime().with_variant(DATETIME(fsp=6), "mysql"))
    closed_by_role: Mapped[str | None] = mapped_column(String(6))
    closure_reason: Mapped[str | None] = mapped_column(String(32))
    active_slot: Mapped[int | None] = mapped_column(Computed("CASE WHEN status = 'PENDING' THEN 1 ELSE NULL END", persisted=True))

    @validates("public_ref", "conversation_id", "product_listing_id", "parent_offer_id", "proposer_role", "amount", "currency", "client_offer_id", "created_at", "expires_at")
    def immutable_proposal(self, key, value):
        if key in self.__dict__ and self.__dict__[key] != value:
            raise ValueError("Proposal terms cannot be changed.")
        return value
