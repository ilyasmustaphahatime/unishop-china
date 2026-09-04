from uuid import uuid4

import pytest
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.models import User, UserProfile


def create_user(session: Session, suffix: str) -> User:
    user = User(email=f"profile-model-{suffix}@example.test", password_hash="hash")
    session.add(user)
    session.flush()
    return user


def test_profile_has_one_to_one_opaque_public_id_defaults(db_session: Session) -> None:
    user = create_user(db_session, "defaults")
    profile = UserProfile(user_id=user.id)
    db_session.add(profile)
    db_session.flush()

    assert profile.id
    assert profile.public_id
    assert profile.public_id != profile.id
    assert profile.onboarding_completed is False


def test_duplicate_user_profile_is_rejected(db_session: Session) -> None:
    user = create_user(db_session, "duplicate-user")
    db_session.add_all([UserProfile(user_id=user.id), UserProfile(user_id=user.id)])

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_duplicate_public_id_is_rejected(db_session: Session) -> None:
    first = create_user(db_session, "duplicate-public-a")
    second = create_user(db_session, "duplicate-public-b")
    public_id = str(uuid4())
    db_session.add_all(
        [
            UserProfile(user_id=first.id, public_id=public_id),
            UserProfile(user_id=second.id, public_id=public_id),
        ]
    )

    with pytest.raises(IntegrityError):
        db_session.flush()


@pytest.mark.parametrize(
    "values",
    [
        {"display_name": " "},
        {"display_name": "x"},
        {"display_name": "x" * 51},
        {"bio": "x" * 301},
        {"city": "Not a supported city"},
    ],
)
def test_database_rejects_invalid_profile_values(
    db_session: Session,
    values: dict[str, str],
) -> None:
    user = create_user(db_session, str(uuid4()))
    db_session.add(UserProfile(user_id=user.id, **values))

    with pytest.raises(DBAPIError):
        db_session.flush()


def test_profile_requires_existing_user(db_session: Session) -> None:
    db_session.add(UserProfile(user_id=str(uuid4())))

    with pytest.raises(IntegrityError):
        db_session.flush()
