from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.common.enums import AccountStatus
from app.models.profile import SUPPORTED_PROFILE_CITIES, UserProfile
from app.models.user import User
from app.repositories.profile_repository import ProfileRepository
from app.repositories.user_repository import UserRepository
from app.schemas.profile import ProfileUpdateRequest


class ProfileUnavailableError(Exception):
    """The authenticated account can no longer use marketplace profile features."""


class OnboardingIncompleteError(Exception):
    """Required server-side profile fields are missing."""


@dataclass(frozen=True, slots=True)
class OwnProfileResult:
    public_id: str
    display_name: str | None
    bio: str | None
    city: str | None
    onboarding_completed: bool
    member_since: datetime
    created_at: datetime
    updated_at: datetime
    email_verified: bool
    phone_verified: bool


@dataclass(frozen=True, slots=True)
class PublicProfileResult:
    public_id: str
    display_name: str
    bio: str | None
    city: str
    member_since: datetime
    email_verified: bool
    phone_verified: bool


class ProfileService:
    """Own profile lifecycle with user-row serialization for all mutations."""

    def __init__(
        self,
        *,
        profile_repository: ProfileRepository | None = None,
        user_repository: UserRepository | None = None,
    ) -> None:
        self.profile_repository = profile_repository or ProfileRepository()
        self.user_repository = user_repository or UserRepository()

    def get_or_create_own(self, session: Session, *, user_id: str) -> OwnProfileResult:
        with self._transaction(session):
            user = self._active_user_for_update(session, user_id)
            profile = self._profile_for_update_or_create(session, user.id)
            return self._own_result(profile, user)

    def update_own(
        self,
        session: Session,
        *,
        user_id: str,
        request: ProfileUpdateRequest,
    ) -> OwnProfileResult:
        with self._transaction(session):
            user = self._active_user_for_update(session, user_id)
            profile = self._profile_for_update_or_create(session, user.id)
            values = {field: getattr(request, field) for field in request.model_fields_set}
            self.profile_repository.update_fields(profile, values=values)
            if not self._has_required_onboarding_fields(profile):
                profile.onboarding_completed = False
            session.flush()
            return self._own_result(profile, user)

    def complete_onboarding(
        self,
        session: Session,
        *,
        user_id: str,
    ) -> OwnProfileResult:
        with self._transaction(session):
            user = self._active_user_for_update(session, user_id)
            profile = self._profile_for_update_or_create(session, user.id)
            if not self._has_required_onboarding_fields(profile):
                raise OnboardingIncompleteError
            profile.onboarding_completed = True
            session.flush()
            return self._own_result(profile, user)

    def get_public(self, session: Session, *, public_id: str) -> PublicProfileResult | None:
        row = self.profile_repository.get_active_public(session, public_id)
        if row is None:
            return None
        profile, user = row
        if profile.display_name is None or profile.city is None:
            return None
        return PublicProfileResult(
            public_id=profile.public_id,
            display_name=profile.display_name,
            bio=profile.bio,
            city=profile.city,
            member_since=user.created_at,
            email_verified=user.email_verified,
            phone_verified=user.phone_verified,
        )

    def _active_user_for_update(self, session: Session, user_id: str) -> User:
        user = self.user_repository.get_by_id_for_update(session, user_id)
        if user is None or user.account_status is not AccountStatus.ACTIVE:
            raise ProfileUnavailableError
        return user

    def _profile_for_update_or_create(self, session: Session, user_id: str) -> UserProfile:
        profile = self.profile_repository.get_by_user_id(
            session,
            user_id,
            for_update=True,
        )
        if profile is None:
            profile = self.profile_repository.create(session, user_id=user_id)
        return profile

    @staticmethod
    def _has_required_onboarding_fields(profile: UserProfile) -> bool:
        return (
            profile.display_name is not None
            and 2 <= len(profile.display_name) <= 50
            and profile.city in SUPPORTED_PROFILE_CITIES
        )

    @staticmethod
    def _own_result(profile: UserProfile, user: User) -> OwnProfileResult:
        return OwnProfileResult(
            public_id=profile.public_id,
            display_name=profile.display_name,
            bio=profile.bio,
            city=profile.city,
            onboarding_completed=profile.onboarding_completed,
            member_since=user.created_at,
            created_at=profile.created_at,
            updated_at=profile.updated_at,
            email_verified=user.email_verified,
            phone_verified=user.phone_verified,
        )

    @staticmethod
    @contextmanager
    def _transaction(session: Session) -> Iterator[None]:
        if session.in_transaction():
            with session.begin_nested():
                yield
            session.commit()
            return
        with session.begin():
            yield
