from collections.abc import Generator

import pytest
from sqlalchemy.orm import Session

import app.models  # noqa: F401 -- configure all authentication relationships
from app.core.config import settings
from app.core.database import engine


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Run each model test inside a transaction that is always rolled back."""
    if settings.app_env.lower() != "development":
        pytest.fail("Authentication model tests may only use the development database.")
    if engine.url.database != "unishop_china":
        pytest.fail("Authentication model tests require the unishop_china database.")

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
