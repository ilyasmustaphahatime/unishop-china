"""One explicit seller-consent state per conversation, never a public contact field."""
from datetime import datetime

from sqlalchemy import CHAR, CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import utc_now


class WeChatShareRequest(Base):
    __tablename__ = "wechat_share_requests"
    __table_args__ = (
        CheckConstraint("status IN ('PENDING','APPROVED','DENIED','REVOKED')",
                        name="ck_wechat_shares_status"),
        CheckConstraint("(status = 'APPROVED' AND contact_ciphertext IS NOT NULL) OR "
                        "(status <> 'APPROVED' AND contact_ciphertext IS NULL)",
                        name="ck_wechat_shares_ciphertext"),
        CheckConstraint("(status = 'PENDING' AND decided_at IS NULL AND revoked_at IS NULL) OR "
                        "(status IN ('APPROVED','DENIED') AND decided_at IS NOT NULL "
                        "AND revoked_at IS NULL) OR (status = 'REVOKED' AND revoked_at IS NOT NULL)",
                        name="ck_wechat_shares_timestamps"),
    )

    conversation_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("conversations.id", name="fk_wechat_shares_conversation",
                             ondelete="CASCADE"), primary_key=True,
    )
    status: Mapped[str] = mapped_column(String(16), default="PENDING", nullable=False)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True).with_variant(DATETIME(fsp=6), "mysql"),
        default=utc_now, nullable=False,
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True).with_variant(DATETIME(fsp=6), "mysql"), nullable=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True).with_variant(DATETIME(fsp=6), "mysql"), nullable=True,
    )
    contact_ciphertext: Mapped[str | None] = mapped_column(String(2048), nullable=True)
