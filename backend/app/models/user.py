from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.enums import AccountStatus
from app.core.database import Base
from app.models.base import UUIDTimestampMixin

if TYPE_CHECKING:
    from app.models.password_reset_code import PasswordResetCode
    from app.models.phone_verification_code import PhoneVerificationCode
    from app.models.refresh_token import RefreshToken
    from app.models.user_role import UserRole


class User(UUIDTimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "email IS NOT NULL OR phone_number IS NOT NULL",
            name="ck_users_email_or_phone_required",
        ),
    )

    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    phone_number: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    phone_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("0"),
        nullable=False,
    )
    email_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("0"),
        nullable=False,
    )
    account_status: Mapped[AccountStatus] = mapped_column(
        Enum(
            AccountStatus,
            name="account_status_enum",
            native_enum=True,
            validate_strings=True,
        ),
        default=AccountStatus.ACTIVE,
        server_default=AccountStatus.ACTIVE.value,
        nullable=False,
        index=True,
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    roles: Mapped[list["UserRole"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    phone_verification_codes: Mapped[list["PhoneVerificationCode"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    password_reset_codes: Mapped[list["PasswordResetCode"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
