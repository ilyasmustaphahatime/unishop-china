"""Shared whole-transaction boundary and the existing bounded InnoDB retry policy."""
from contextlib import contextmanager
from functools import wraps

from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session


@contextmanager
def commit_request_transaction(db: Session):
    """Commit a request that may already have an authentication read transaction.

    Body failures roll back the operation's savepoint, preserving caller setup;
    commit failures explicitly recover the Session. Do not use this inside a
    caller-owned workflow that must defer its final commit.
    """
    if db.in_transaction():
        with db.begin_nested():
            yield
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise
    else:
        with db.begin():
            yield


@contextmanager
def transaction(db: Session):
    """Existing profile/seller/catalog unit: also roll back outer state on failure."""
    try:
        with commit_request_transaction(db):
            yield
    except Exception:
        db.rollback()
        raise


def retry_deadlock(operation):
    """Retry only whole transactions already rolled back by InnoDB (1213).

    Savepoint cleanup can wrap 1213 in 1305; inspect causes without logging SQL.
    Never retry integrity errors, lock timeouts or external side effects.
    """
    @wraps(operation)
    def run(self, session: Session, *args, **kwargs):
        for attempt in range(3):
            try:
                return operation(self, session, *args, **kwargs)
            except DBAPIError as error:
                current = error
                seen = set()
                deadlock = False
                while current is not None and id(current) not in seen:
                    seen.add(id(current))
                    if isinstance(current, DBAPIError):
                        deadlock |= getattr(current.orig, "args", (None,))[0] == 1213
                    current = current.__cause__ or current.__context__
                if not deadlock or attempt == 2:
                    raise
                session.rollback()
    return run
