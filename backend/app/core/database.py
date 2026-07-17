import logging
from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import build_database_url, settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


DATABASE_URL = build_database_url(settings)


def get_database_url() -> URL:
    """Return the shared, validated URL used by the app and Alembic."""
    return DATABASE_URL


engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
    pool_size=5,
    max_overflow=10,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def check_database_connection() -> bool:
    """Execute a safe liveness query without leaking connection details."""
    try:
        with engine.connect() as connection:
            return connection.scalar(text("SELECT 1")) == 1
    except SQLAlchemyError as exc:
        error_code = getattr(getattr(exc, "orig", None), "args", (None,))[0]
        logger.warning(
            "Database connection check failed (exception=%s, code=%s).",
            type(exc).__name__,
            error_code,
        )
        return False
