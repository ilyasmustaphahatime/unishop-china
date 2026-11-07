"""Durable plain-text messages with database-backed sender-scoped idempotency."""
from datetime import datetime
import secrets

from sqlalchemy import CHAR, CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import UUIDPrimaryKeyMixin, utc_now


class Message(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("public_ref", name="uq_messages_public_ref"),
        UniqueConstraint("conversation_id", "sender_user_id", "client_message_id",
                         name="uq_messages_client_id"),
        CheckConstraint("REGEXP_LIKE(public_ref, '^msg-[0-9a-f]{32}$', 'c')",
                        name="ck_messages_public_ref"),
        CheckConstraint("REGEXP_LIKE(client_message_id, "
                        "'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', 'c')",
                        name="ck_messages_client_id"),
        CheckConstraint("CHAR_LENGTH(content) BETWEEN 1 AND 2000 AND OCTET_LENGTH(content) <= 8000",
                        name="ck_messages_content_size"),
        Index("ix_messages_conversation_time", "conversation_id", "created_at", "public_ref"),
        Index("ix_messages_sender", "sender_user_id"),
    )

    public_ref: Mapped[str] = mapped_column(
        String(36, collation="ascii_bin"), default=lambda: "msg-" + secrets.token_hex(16),
        nullable=False,
    )
    conversation_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("conversations.id", name="fk_messages_conversation", ondelete="CASCADE"),
        nullable=False,
    )
    sender_user_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("users.id", name="fk_messages_sender", ondelete="RESTRICT"),
        nullable=False,
    )
    client_message_id: Mapped[str] = mapped_column(String(36, collation="ascii_bin"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True).with_variant(DATETIME(fsp=6), "mysql"),
        default=utc_now, nullable=False,
    )
