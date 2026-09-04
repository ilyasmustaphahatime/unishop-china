from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.enums import AccountStatus
from app.models.profile import UserProfile
from app.models.user import User


class ProfileRepository:
    def get_by_user_id(
        self,
        session: Session,
        user_id: str,
        *,
        for_update: bool = False,
    ) -> UserProfile | None:
        statement = select(UserProfile).where(UserProfile.user_id == user_id)
        if for_update:
            statement = statement.with_for_update()
        return session.scalar(statement)

    def create(self, session: Session, *, user_id: str) -> UserProfile:
        profile = UserProfile(user_id=user_id)
        session.add(profile)
        session.flush()
        return profile

    def get_active_public(
        self,
        session: Session,
        public_id: str,
    ) -> tuple[UserProfile, User] | None:
        row = session.execute(
            select(UserProfile, User)
            .join(User, User.id == UserProfile.user_id)
            .where(
                UserProfile.public_id == public_id,
                UserProfile.onboarding_completed.is_(True),
                User.account_status == AccountStatus.ACTIVE,
            )
        ).one_or_none()
        return (row[0], row[1]) if row is not None else None

    def update_fields(
        self,
        profile: UserProfile,
        *,
        values: dict[str, str | None],
    ) -> None:
        for field, value in values.items():
            setattr(profile, field, value)
