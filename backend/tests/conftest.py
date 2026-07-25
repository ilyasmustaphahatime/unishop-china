from collections.abc import Generator

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401 -- configure all authentication relationships
from app.core.config import settings
from app.core.database import engine
from app.models import (
    PasswordResetCode,
    PhoneVerificationCode,
    RefreshToken,
    User,
    UserRole,
)

TRACKED_TEST_TABLES = (
    User,
    UserRole,
    PhoneVerificationCode,
    RefreshToken,
    PasswordResetCode,
)


def _database_snapshot() -> tuple[tuple[int, ...], frozenset[str], frozenset[str]]:
    with Session(engine) as audit_session:
        counts = tuple(
            int(audit_session.scalar(select(func.count()).select_from(model)) or 0)
            for model in TRACKED_TEST_TABLES
        )
        user_ids = frozenset(audit_session.scalars(select(User.id)))
        role_ids = frozenset(audit_session.scalars(select(UserRole.id)))
    return counts, user_ids, role_ids


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Run each model test inside a transaction that is always rolled back."""
    if settings.app_env.lower() != "development":
        pytest.fail("Authentication model tests may only use the development database.")
    if engine.url.database != "unishop_china":
        pytest.fail("Authentication model tests require the unishop_china database.")

    baseline = _database_snapshot()
    connection = engine.connect()
    outer_transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")

    try:
        yield session
    finally:
        session.close()
        if outer_transaction.is_active:
            outer_transaction.rollback()
        connection.close()
        assert _database_snapshot() == baseline, (
            "A database test changed pre-existing development data or left test records behind."
        )
