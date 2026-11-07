"""Consent-state persistence. No decryption, transport errors or commits here."""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import WeChatShareRequest


class WeChatShareRepository:
    def for_update(self, db: Session, conversation_id: str) -> WeChatShareRequest | None:
        # Call only after participant authorization and the conversation row lock.
        return db.scalar(select(WeChatShareRequest).where(
            WeChatShareRequest.conversation_id == conversation_id,
        ).with_for_update().execution_options(populate_existing=True))

    def create(self, db: Session, conversation_id: str, at: datetime) -> WeChatShareRequest:
        row = WeChatShareRequest(conversation_id=conversation_id, status="PENDING", requested_at=at)
        db.add(row)
        db.flush()
        return row
