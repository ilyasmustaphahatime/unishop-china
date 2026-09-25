from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.common.public_handles import generate_public_handle, normalize_public_handle

from app.core.database import Base
from app.models.base import UUIDTimestampMixin, generate_uuid

if TYPE_CHECKING:
    from app.models.user import User


SUPPORTED_PROFILE_CITIES = (
    "Qingdao",
    "Beijing",
    "Shanghai",
    "Shenzhen",
    "Guangzhou",
    "Hangzhou",
)


class UserProfile(UUIDTimestampMixin, Base):
    """Marketplace-facing data kept separate from authentication state."""

    __tablename__ = "user_profiles"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_profiles_user_id"),
        UniqueConstraint("public_id", name="uq_user_profiles_public_id"),
        UniqueConstraint("public_handle", name="uq_user_profiles_public_handle"),
        CheckConstraint(
            "REGEXP_LIKE(public_handle, '^[a-z0-9][a-z0-9_-]{1,28}[a-z0-9]$', 'c') "
            "AND public_handle NOT IN "
            "('about','account','admin','api','assets','auth','categories','chat','cities',"
            "'dev','help','login','logout','messages','notifications','products','profile',"
            "'profiles','register','search','seller','sellers','settings','static','support','users')",
            name="ck_user_profiles_public_handle",
        ),
        CheckConstraint(
            "display_name IS NULL OR "
            "CHAR_LENGTH(TRIM(display_name)) BETWEEN 2 AND 50",
            name="ck_user_profiles_display_name_length",
        ),
        CheckConstraint(
            "bio IS NULL OR CHAR_LENGTH(bio) <= 300",
            name="ck_user_profiles_bio_length",
        ),
        CheckConstraint(
            "city IS NULL OR city IN "
            "('Qingdao','Beijing','Shanghai','Shenzhen','Guangzhou','Hangzhou')",
            name="ck_user_profiles_supported_city",
        ),
    )

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    public_id: Mapped[str] = mapped_column(
        String(36),
        default=generate_uuid,
        nullable=False,
    )
    display_name: Mapped[str | None] = mapped_column(String(50))
    public_handle: Mapped[str] = mapped_column(
        String(30), default=generate_public_handle, nullable=False, active_history=True,
    )
    bio: Mapped[str | None] = mapped_column(String(300))
    city: Mapped[str | None] = mapped_column(String(32))
    onboarding_completed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("0"),
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="profile")

    @validates("public_handle")
    def validate_public_handle(self, key: str, value: str) -> str:
        normalized = normalize_public_handle(value)
        previous = self.__dict__.get(key)
        if previous is not None and previous != normalized:
            raise ValueError("Public handles cannot be renamed.")
        return normalized
