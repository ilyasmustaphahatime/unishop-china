from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, local
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.common.public_handles import generate_public_handle
from app.core.database import engine
from app.models import User, UserProfile
from app.repositories.profile_repository import ProfileRepository
from app.services.profile_service import ProfileService
from tests.integration.test_profile_concurrency import create_user, remove_user, with_session
from tests.integration.test_profile_routes import (
    active_user as active_user,
    client as client,
    clear_profile_rate_limiters as clear_profile_rate_limiters,
)


def add_user(session):
    user = User(email=f"handles-{uuid4()}@example.test", password_hash="synthetic-unused")
    session.add(user)
    session.flush()
    return user


def test_database_enforces_handle_uniqueness_and_normalization(db_session):
    a, b = add_user(db_session), add_user(db_session)
    first = UserProfile(user_id=a.id, public_handle="User-Example")
    db_session.add(first)
    db_session.flush()
    assert first.public_handle == "user-example"
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(UserProfile(user_id=b.id, public_handle="USER-EXAMPLE"))
        db_session.flush()


@pytest.mark.parametrize("handle", [None, "ADMIN", "admin", "Abc", "ab", "a" * 31,
                                          "a..b", "a/b", "a\\b", "%2Fadmin", "abc ", "-abc"])
def test_direct_database_writes_cannot_bypass_handle_constraints(db_session, handle):
    user = add_user(db_session)
    profile = UserProfile(user_id=user.id)
    db_session.add(profile)
    db_session.flush()
    with pytest.raises(DBAPIError), db_session.begin_nested():
        db_session.execute(text("UPDATE user_profiles SET public_handle=:handle WHERE id=:id"),
                           {"handle": handle, "id": profile.id})


def test_handle_is_immutable_in_model_and_api(client, active_user):
    profile = client.get("/api/v1/profile/me").json()
    assert "public_id" not in profile
    assert client.patch("/api/v1/profile/me", json={"public_handle": "user-other"}).status_code == 422
    assert client.post("/api/v1/profile/onboarding/complete",
                       json={"public_handle": "user-other"}).status_code == 422
    with Session(engine) as session:
        row = session.scalar(select(UserProfile).where(UserProfile.user_id == active_user.id))
        with pytest.raises(ValueError, match="cannot be renamed"):
            row.public_handle = "user-renamed"
    assert client.get("/api/v1/profile/me").json()["public_handle"] == profile["public_handle"]


def test_guessed_handle_has_no_write_authority_or_internal_id_fallback(client, active_user):
    profile = client.patch("/api/v1/profile/me",
                           json={"display_name": "Public Person", "city": "Qingdao"}).json()
    client.post("/api/v1/profile/onboarding/complete", json={})
    handle = profile["public_handle"]
    with Session(engine) as session:
        row = session.scalar(select(UserProfile).where(UserProfile.user_id == active_user.id))
        identifiers = (row.id, row.user_id, row.public_id)
    path = "/api/v1/profiles/by-handle/" + handle
    public = client.get(path).json()
    assert set(public) == {"public_handle", "display_name", "bio", "city", "member_since",
                           "email_verified", "phone_verified"}
    assert client.get(path.upper().replace("/API/V1/PROFILES/BY-HANDLE/",
                                          "/api/v1/profiles/by-handle/")).json() == public
    assert client.patch(path, json={"bio": "attack"}).status_code == 405
    assert client.get("/api/v1/profiles/by-handle/%75" + handle[1:]).status_code == 404
    for value in (*identifiers, "42"):
        assert client.get("/api/v1/profiles/" + value).status_code == 404
        assert client.get("/api/v1/profiles/by-handle/" + value).status_code == 422


def test_other_users_handle_never_selects_private_write_target(client):
    other_id = create_user()
    try:
        other = with_session(lambda session: ProfileService().get_or_create_own(
            session, user_id=other_id))
        assert client.patch("/api/v1/profile/me", json={
            "public_handle": other.public_handle, "bio": "attacker update",
        }).status_code == 422
        with Session(engine) as session:
            profile = session.scalar(select(UserProfile).where(UserProfile.user_id == other_id))
            assert profile.bio is None
    finally:
        remove_user(other_id)


def test_hidden_states_and_unknown_handle_have_identical_missing_response(client, active_user):
    from app.common.enums import AccountStatus

    handle = client.get("/api/v1/profile/me").json()["public_handle"]
    missing = client.get("/api/v1/profiles/by-handle/user-unknown")
    assert missing.status_code == 404
    assert client.get("/api/v1/profiles/by-handle/" + handle).json() == missing.json()
    for state in (AccountStatus.SUSPENDED, AccountStatus.BANNED, AccountStatus.DELETED):
        with Session(engine) as session, session.begin():
            user = session.get(User, active_user.id)
            user.account_status = state
            profile = session.scalar(select(UserProfile).where(UserProfile.user_id == active_user.id))
            profile.display_name = "Hidden Person"
            profile.city = "Qingdao"
            profile.onboarding_completed = True
        response = client.get("/api/v1/profiles/by-handle/" + handle)
        assert response.status_code == missing.status_code
        assert response.json() == missing.json()


def test_collision_retry_preserves_outer_transaction(db_session, monkeypatch):
    first, second = add_user(db_session), add_user(db_session)
    db_session.add(UserProfile(user_id=first.id, public_handle="user-existing"))
    db_session.flush()
    candidates = iter(("user-existing", "user-new-handle"))
    monkeypatch.setattr("app.repositories.profile_repository.generate_public_handle",
                        lambda: next(candidates))
    profile = ProfileRepository().create(db_session, user_id=second.id)
    assert profile.public_handle == "user-new-handle"
    assert db_session.get(User, first.id) is not None


def test_retry_exhaustion_rolls_back_without_extra_profiles(db_session, monkeypatch):
    first, second = add_user(db_session), add_user(db_session)
    db_session.add(UserProfile(user_id=first.id, public_handle="user-existing"))
    db_session.flush()
    monkeypatch.setattr("app.repositories.profile_repository.generate_public_handle",
                        lambda: "user-existing")
    with pytest.raises(RuntimeError, match="allocation unavailable"):
        ProfileRepository().create(db_session, user_id=second.id)
    assert db_session.scalar(select(UserProfile).where(UserProfile.user_id == second.id)) is None
    assert db_session.get(User, first.id) is not None


def test_concurrent_users_retry_same_generated_handle_safely(monkeypatch):
    ids = [create_user(), create_user()]
    barrier = Barrier(2)
    state = local()
    shared = generate_public_handle()

    def candidate():
        if not getattr(state, "called", False):
            state.called = True
            barrier.wait(timeout=10)
            return shared
        return generate_public_handle()

    monkeypatch.setattr("app.repositories.profile_repository.generate_public_handle", candidate)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda uid: with_session(
                lambda session: ProfileService().get_or_create_own(session, user_id=uid)), ids))
        assert len({row.public_handle for row in results}) == 2
    finally:
        for user_id in ids:
            remove_user(user_id)
