from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import CHAR, DateTime
from sqlalchemy.orm import Mapped, mapped_column

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class UUIDTimestampMixin:
    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=lambda: str(uuid4()))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
