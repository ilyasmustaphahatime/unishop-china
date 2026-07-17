from typing import TYPE_CHECKING

from sqlalchemy import CHAR, Enum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.enums import UserRoleType
from app.core.database import Base
from app.models.base import UUIDCreatedAtMixin

if TYPE_CHECKING:
    from app.models.user import User


class UserRole(UUIDCreatedAtMixin, Base):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role", name="uq_user_roles_user_id_role"),)

    user_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[UserRoleType] = mapped_column(
        Enum(
            UserRoleType,
            name="user_role_type_enum",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="roles")
