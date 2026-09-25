"""Use pre-existing MySQL read snapshots, as authentication dependencies do."""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import engine
from app.models import User, UserProfile
from app.schemas.profile import ProfileUpdateRequest
from app.services.profile_service import ProfileService
from tests.integration.test_profile_concurrency import create_user, remove_user, with_session


@pytest.mark.parametrize("existing", [False, True])
def test_own_profile_reads_latest_committed_row_after_authentication_snapshot(existing):
    user_id = create_user()
    service = ProfileService()
    try:
        if existing:
            with_session(lambda session: service.get_or_create_own(session, user_id=user_id))
        with Session(engine) as stale:
            # Authentication has already established a consistent-read snapshot.
            assert stale.scalar(select(User.id).where(User.id == user_id)) == user_id
            stale.scalar(select(UserProfile).where(UserProfile.user_id == user_id))
            latest = with_session(lambda session: service.update_own(
                session, user_id=user_id,
                request=ProfileUpdateRequest(display_name="Committed Name", city="Qingdao")))
            result = service.get_or_create_own(stale, user_id=user_id)
            assert result.public_handle == latest.public_handle
            assert result.display_name == latest.display_name
            assert result.city == latest.city
    finally:
        remove_user(user_id)


def test_stale_snapshot_cannot_complete_onboarding_after_required_field_is_cleared():
    user_id = create_user()
    service = ProfileService()
    try:
        with_session(lambda session: service.update_own(
            session, user_id=user_id,
            request=ProfileUpdateRequest(display_name="Original Name", city="Qingdao")))
        with Session(engine) as stale:
            assert stale.scalar(select(User.id).where(User.id == user_id)) == user_id
            stale.scalar(select(UserProfile).where(UserProfile.user_id == user_id))
            with_session(lambda session: service.update_own(
                session, user_id=user_id, request=ProfileUpdateRequest(city=None)))
            from app.services.profile_service import OnboardingIncompleteError
            with pytest.raises(OnboardingIncompleteError):
                service.complete_onboarding(stale, user_id=user_id)
        with Session(engine) as session:
            profile = session.scalar(select(UserProfile).where(UserProfile.user_id == user_id))
            assert profile.city is None
            assert not profile.onboarding_completed
    finally:
        remove_user(user_id)


def test_expired_model_cannot_silently_rename_handle(db_session):
    from tests.integration.test_public_handles import add_user

    user = add_user(db_session)
    profile = UserProfile(user_id=user.id)
    db_session.add(profile)
    db_session.flush()
    db_session.expire(profile, ["public_handle"])
    with pytest.raises(ValueError, match="cannot be renamed"):
        profile.public_handle = "user-renamed"


@pytest.mark.parametrize("code,expected_calls", [(1213, 3), (1062, 1), (1205, 1)])
def test_profile_transaction_retries_only_deadlocks_and_is_bounded(code, expected_calls):
    from pymysql.err import OperationalError as DriverError
    from sqlalchemy.exc import OperationalError

    class Repository:
        calls = 0

        def get_by_id_for_update(self, session, user_id):
            self.calls += 1
            raise OperationalError("synthetic operation", {}, DriverError(code, "controlled"))

    repository = Repository()
    service = ProfileService(user_repository=repository)
    with Session(engine) as session, pytest.raises(OperationalError):
        service.get_or_create_own(session, user_id="synthetic-owner")
    assert repository.calls == expected_calls


def test_global_error_retains_referrer_and_private_cache_headers():
    from fastapi.testclient import TestClient
    from app.core.config import settings
    from app.main import create_app

    app = create_app(settings.model_copy(update={"app_debug": False}))

    @app.get("/api/v1/profile/audit-error")
    def controlled_error():
        raise RuntimeError("controlled test failure")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/profile/audit-error")
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert response.headers.get("cache-control") == "no-store"
    assert response.headers.get("pragma") == "no-cache"
    assert response.headers.get("referrer-policy") == "no-referrer"
