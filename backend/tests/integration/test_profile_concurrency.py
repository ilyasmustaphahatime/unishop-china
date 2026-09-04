from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.database import engine
from app.models import User, UserProfile
from app.repositories.profile_repository import ProfileRepository
from app.schemas.profile import ProfileUpdateRequest
from app.services.profile_service import OnboardingIncompleteError, ProfileService


def create_user() -> str:
    user_id = str(uuid4())
    now = datetime.now(timezone.utc)
    with Session(engine) as session, session.begin():
        session.add(
            User(
                id=user_id,
                email=f"phase6-concurrency-{user_id}@example.test",
                password_hash="not-used",
                created_at=now,
                updated_at=now,
            )
        )
    return user_id


def remove_user(user_id: str) -> None:
    with Session(engine) as session, session.begin():
        session.execute(delete(User).where(User.id == user_id))


def with_session(operation):
    with Session(engine) as session:
        return operation(session)


def test_concurrent_first_profile_creation_produces_exactly_one_profile() -> None:
    user_id = create_user()
    service = ProfileService()
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(
                    with_session,
                    lambda session: service.get_or_create_own(session, user_id=user_id),
                )
                for _ in range(2)
            ]
            results = [future.result(timeout=10) for future in futures]

        with Session(engine) as session:
            count = session.scalar(
                select(func.count()).select_from(UserProfile).where(UserProfile.user_id == user_id)
            )
        assert count == 1
        assert len({result.public_id for result in results}) == 1
    finally:
        remove_user(user_id)


def test_concurrent_updates_leave_one_valid_complete_row() -> None:
    user_id = create_user()
    service = ProfileService()
    try:
        with_session(lambda session: service.get_or_create_own(session, user_id=user_id))
        requests = [
            ProfileUpdateRequest(display_name="First Writer", city="Beijing"),
            ProfileUpdateRequest(display_name="Second Writer", city="Shanghai"),
        ]
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    lambda request: with_session(
                        lambda session: service.update_own(
                            session,
                            user_id=user_id,
                            request=request,
                        )
                    ),
                    requests,
                )
            )
        assert {result.display_name for result in results} == {"First Writer", "Second Writer"}
        with Session(engine) as session:
            profile = session.scalar(select(UserProfile).where(UserProfile.user_id == user_id))
            assert profile is not None
            assert profile.display_name in {"First Writer", "Second Writer"}
            assert profile.city in {"Beijing", "Shanghai"}
    finally:
        remove_user(user_id)


def test_concurrent_onboarding_is_idempotent() -> None:
    user_id = create_user()
    service = ProfileService()
    try:
        with_session(
            lambda session: service.update_own(
                session,
                user_id=user_id,
                request=ProfileUpdateRequest(display_name="Ready User", city="Qingdao"),
            )
        )
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = [
                future.result(timeout=10)
                for future in [
                    executor.submit(
                        with_session,
                        lambda session: service.complete_onboarding(
                            session,
                            user_id=user_id,
                        ),
                    )
                    for _ in range(2)
                ]
            ]
        assert all(result.onboarding_completed for result in results)
        assert len({result.public_id for result in results}) == 1
    finally:
        remove_user(user_id)


def test_update_racing_onboarding_never_leaves_invalid_completion() -> None:
    user_id = create_user()
    service = ProfileService()
    try:
        with_session(
            lambda session: service.update_own(
                session,
                user_id=user_id,
                request=ProfileUpdateRequest(display_name="Initially Ready", city="Shenzhen"),
            )
        )

        def complete() -> None:
            try:
                with_session(
                    lambda session: service.complete_onboarding(session, user_id=user_id)
                )
            except OnboardingIncompleteError:
                pass

        def invalidate() -> None:
            with_session(
                lambda session: service.update_own(
                    session,
                    user_id=user_id,
                    request=ProfileUpdateRequest(display_name=None),
                )
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            list(executor.map(lambda operation: operation(), [complete, invalidate]))

        with Session(engine) as session:
            profile = session.scalar(select(UserProfile).where(UserProfile.user_id == user_id))
            assert profile is not None
            assert profile.display_name is None
            assert profile.onboarding_completed is False
    finally:
        remove_user(user_id)


class FailingProfileRepository(ProfileRepository):
    def update_fields(
        self,
        profile: UserProfile,
        *,
        values: dict[str, str | None],
    ) -> None:
        super().update_fields(profile, values=values)
        raise RuntimeError("controlled failure")


def test_profile_update_rolls_back_after_controlled_failure() -> None:
    user_id = create_user()
    service = ProfileService()
    try:
        with_session(
            lambda session: service.update_own(
                session,
                user_id=user_id,
                request=ProfileUpdateRequest(display_name="Original Name", city="Guangzhou"),
            )
        )
        failing = ProfileService(profile_repository=FailingProfileRepository())
        try:
            with_session(
                lambda session: failing.update_own(
                    session,
                    user_id=user_id,
                    request=ProfileUpdateRequest(display_name="Corrupt Name"),
                )
            )
        except RuntimeError:
            pass
        else:
            raise AssertionError("Controlled mutation failure was not raised.")

        with Session(engine) as session:
            profile = session.scalar(select(UserProfile).where(UserProfile.user_id == user_id))
            assert profile is not None
            assert profile.display_name == "Original Name"
            assert profile.city == "Guangzhou"
    finally:
        remove_user(user_id)
