from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.enums import UserRoleType
from app.models.user_role import UserRole


class UserRoleRepository:
    def list_roles_for_user(self, session: Session, user_id: str) -> list[UserRoleType]:
        statement = (
            select(UserRole.role)
            .where(UserRole.user_id == user_id)
            .order_by(UserRole.role)
        )
        return list(session.scalars(statement))

    def create_role(
        self,
        session: Session,
        *,
        user_id: str,
        role: UserRoleType,
    ) -> UserRole:
        user_role = UserRole(user_id=user_id, role=role)
        session.add(user_role)
        session.flush()
        return user_role
