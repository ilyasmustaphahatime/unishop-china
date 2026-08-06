from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CHAR, CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import UUIDCreatedAtMixin

if TYPE_CHECKING:
    from app.models.user import User


class RefreshToken(UUIDCreatedAtMixin, Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        CheckConstraint(
            "revocation_reason IS NULL OR revocation_reason IN "
            "('rotated', 'logout', 'logout_all', 'reuse_detected', "
            "'inactive_account', 'session_limit', 'expired_cleanup')",
            name="ck_refresh_tokens_revocation_reason",
        ),
    )

    user_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
    )
    family_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, index=True)
    csrf_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    family_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    revocation_reason: Mapped[str | None] = mapped_column(String(32))
    replaced_by_token_id: Mapped[str | None] = mapped_column(
        CHAR(36),
        ForeignKey("refresh_tokens.id", ondelete="SET NULL"),
        index=True,
    )

    user: Mapped["User"] = relationship(back_populates="refresh_tokens")
