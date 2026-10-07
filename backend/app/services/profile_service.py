from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.common.enums import AccountStatus
from app.models.profile import UserProfile
from app.core.transactions import retry_deadlock, transaction
from app.repositories.catalog_repository import CityRepository
from app.services.catalog_service import CityService
from app.models.user import User
from app.repositories.seller_verification_repository import SellerVerificationRepository
from app.repositories.profile_repository import ProfileRepository
from app.repositories.user_repository import UserRepository
from app.schemas.profile import ProfileUpdateRequest


class ProfileUnavailableError(Exception):
    """The authenticated account can no longer use marketplace profile features."""


class OnboardingIncompleteError(Exception):
    """Required server-side profile fields are missing."""


@dataclass(frozen=True, slots=True)
class OwnProfileResult:
    public_handle: str
    display_name: str | None
    bio: str | None
    city: str | None
    city_slug: str | None
    city_active: bool
    onboarding_completed: bool
    member_since: datetime
    created_at: datetime
    updated_at: datetime
    email_verified: bool
    phone_verified: bool


@dataclass(frozen=True, slots=True)
class PublicProfileResult:
    public_handle: str
    display_name: str
    bio: str | None
    city: str
    member_since: datetime
    email_verified: bool
    phone_verified: bool
    seller_verified: bool


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

    @retry_deadlock
    def get_or_create_own(self, session: Session, *, user_id: str) -> OwnProfileResult:
        with self._transaction(session):
            user = self._active_user_for_update(session, user_id)
            profile = self._profile_for_update_or_create(session, user.id)
            return self._own_result(session, profile, user)

    @retry_deadlock
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
            values = {field: getattr(request, field) for field in request.model_fields_set - {"city"}}
            if "city" in request.model_fields_set:
                city = CityService().resolve_profile_city(session, request.city) if request.city is not None else None
                profile.city_id = city.id if city else None
                profile.city = city.name_en if city else None
            self.profile_repository.update_fields(profile, values=values)
            if not self._has_required_onboarding_fields(profile):
                profile.onboarding_completed = False
            session.flush()
            return self._own_result(session, profile, user)

    @retry_deadlock
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
            # Already-complete profiles stay complete when an admin retires a city.
            # First completion, however, requires a current active reference.
            city = CityRepository().by_id(session, profile.city_id, lock=True)
            if not profile.onboarding_completed and (city is None or not city.is_active):
                raise OnboardingIncompleteError
            profile.onboarding_completed = True
            session.flush()
            return self._own_result(session, profile, user)

    def get_public(self, session: Session, *, public_handle: str) -> PublicProfileResult | None:
        row = self.profile_repository.get_active_public(session, public_handle)
        if row is None:
            return None
        profile, user = row
        city = CityRepository().by_id(session, profile.city_id) if profile.city_id else None
        if profile.display_name is None or city is None:
            return None
        return PublicProfileResult(
            public_handle=profile.public_handle,
            display_name=profile.display_name,
            bio=profile.bio,
            city=city.name_en,
            member_since=user.created_at,
            email_verified=user.email_verified,
            phone_verified=user.phone_verified,
            seller_verified=bool(user.email_verified and user.phone_verified
                                 and SellerVerificationRepository().has_verified_attempt(session, user.id)),
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
            # A current read must bypass the authentication transaction's older
            # REPEATABLE READ snapshot, even after the owning user lock is held.
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
            and profile.city_id is not None
        )

    @staticmethod
    def _own_result(session: Session, profile: UserProfile, user: User) -> OwnProfileResult:
        city = CityRepository().by_id(session, profile.city_id, lock=True) if profile.city_id else None
        return OwnProfileResult(
            public_handle=profile.public_handle,
            display_name=profile.display_name,
            bio=profile.bio,
            city=city.name_en if city else None,
            city_slug=city.slug if city else None,
            city_active=bool(city and city.is_active),
            onboarding_completed=profile.onboarding_completed,
            member_since=user.created_at,
            created_at=profile.created_at,
            updated_at=profile.updated_at,
            email_verified=user.email_verified,
            phone_verified=user.phone_verified,
        )

    _transaction = staticmethod(transaction)
