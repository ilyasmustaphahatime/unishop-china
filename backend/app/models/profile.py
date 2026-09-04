from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

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
    bio: Mapped[str | None] = mapped_column(String(300))
    city: Mapped[str | None] = mapped_column(String(32))
    onboarding_completed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("0"),
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="profile")
