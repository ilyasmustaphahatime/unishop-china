from datetime import datetime
from enum import Enum as PythonEnum
import secrets

from sqlalchemy import CHAR, CheckConstraint, Computed, DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
from app.models.base import UUIDTimestampMixin, UUIDCreatedAtMixin


class VerificationStatus(str, PythonEnum):
    PENDING = "PENDING"
    UNDER_REVIEW = "UNDER_REVIEW"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


class EvidenceType(str, PythonEnum):
    SELFIE = "SELFIE"
    WECHAT_PROOF = "WECHAT_PROOF"
    HANDWRITTEN_CODE = "HANDWRITTEN_CODE"


class SellerVerification(UUIDTimestampMixin, Base):
    __tablename__ = "seller_verifications"
    __table_args__ = (
        UniqueConstraint("review_reference", name="uq_seller_review_reference"),
        UniqueConstraint("user_id", "active_slot", name="uq_seller_active_user"),
        CheckConstraint("(status = 'PENDING' AND submitted_at IS NULL AND reviewed_at IS NULL) OR "
                        "(status = 'UNDER_REVIEW' AND submitted_at IS NOT NULL AND reviewed_at IS NULL) OR "
                        "(status IN ('VERIFIED','REJECTED') AND submitted_at IS NOT NULL AND reviewed_at IS NOT NULL)",
                        name="ck_seller_transition_dates"),
        CheckConstraint("(status = 'REJECTED' AND rejection_reason IS NOT NULL) OR "
                        "(status <> 'REJECTED' AND rejection_reason IS NULL)", name="ck_seller_rejection"),
    )
    user_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    review_reference: Mapped[str] = mapped_column(String(32), default=lambda: secrets.token_hex(16))
    status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus, name="seller_verification_status", validate_strings=True),
        default=VerificationStatus.PENDING, index=True)
    active_slot: Mapped[int | None] = mapped_column(
        Computed("CASE WHEN status <> 'REJECTED' THEN 1 ELSE NULL END", persisted=True))
    handwritten_challenge: Mapped[str] = mapped_column(String(12), default=lambda: secrets.token_hex(6).upper())
    rejection_reason: Mapped[str | None] = mapped_column(String(500))
    reviewed_by: Mapped[str | None] = mapped_column(CHAR(36), ForeignKey("users.id", ondelete="SET NULL"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SellerEvidence(UUIDTimestampMixin, Base):
    __tablename__ = "seller_evidence"
    __table_args__ = (
        UniqueConstraint("verification_id", "evidence_type", name="uq_seller_evidence_type"),
        UniqueConstraint("storage_key", name="uq_seller_evidence_storage"),
        CheckConstraint("size > 0 AND size <= 5242880", name="ck_seller_evidence_size"),
        CheckConstraint("mime_type IN ('image/jpeg','image/png')", name="ck_seller_evidence_mime"),
    )
    verification_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("seller_verifications.id", ondelete="CASCADE"), index=True)
    evidence_type: Mapped[EvidenceType] = mapped_column(
        Enum(EvidenceType, name="seller_evidence_type", validate_strings=True))
    storage_key: Mapped[str] = mapped_column(String(64))
    file_hash: Mapped[str] = mapped_column(String(64))
    mime_type: Mapped[str] = mapped_column(String(32))
    size: Mapped[int]


class SellerVerificationAudit(UUIDCreatedAtMixin, Base):
    """Transactional metadata only; no documents, credentials or free-form reasons."""
    __tablename__ = "seller_verification_audit"
    verification_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("seller_verifications.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[str | None] = mapped_column(CHAR(36), ForeignKey("users.id", ondelete="SET NULL"))
    event: Mapped[str] = mapped_column(String(32))
