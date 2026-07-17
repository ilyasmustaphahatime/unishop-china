from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import CHAR, DateTime
from sqlalchemy.orm import Mapped, mapped_column


def generate_uuid() -> str:
    return str(uuid4())


def utc_now() -> datetime:
    """Return an aware UTC value; MySQL DATETIME values are interpreted as UTC."""
    return datetime.now(timezone.utc)


class UUIDPrimaryKeyMixin:
    id: Mapped[str] = mapped_column(
        CHAR(36),
        primary_key=True,
        default=generate_uuid,
        nullable=False,
    )


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )


class UUIDCreatedAtMixin(UUIDPrimaryKeyMixin, CreatedAtMixin):
    pass


class UUIDTimestampMixin(UUIDPrimaryKeyMixin, CreatedAtMixin):
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )
