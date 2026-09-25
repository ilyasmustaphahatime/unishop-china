from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.enums import AccountStatus
from app.common.public_handles import generate_public_handle
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
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return session.scalar(statement)

    def create(self, session: Session, *, user_id: str) -> UserProfile:
        for _ in range(8):
            try:
                with session.begin_nested():
                    profile = UserProfile(user_id=user_id, public_handle=generate_public_handle())
                    session.add(profile)
                    session.flush()
                return profile
            except IntegrityError as exc:
                # Retry only a random-handle collision, never unrelated integrity failures.
                if (getattr(exc.orig, "args", (None,))[0] != 1062
                        or "uq_user_profiles_public_handle" not in str(exc.orig)):
                    raise
        raise RuntimeError("Public handle allocation unavailable.")

    def get_active_public(
        self,
        session: Session,
        public_handle: str,
    ) -> tuple[UserProfile, User] | None:
        row = session.execute(
            select(UserProfile, User)
            .join(User, User.id == UserProfile.user_id)
            .where(
                UserProfile.public_handle == public_handle,
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
