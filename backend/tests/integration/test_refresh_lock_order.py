"""Real InnoDB proof that session writers acquire User before refresh rows."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.core.database import engine
from app.core.session_security import hash_refresh_token
from app.models import RefreshToken, User
from app.models.base import utc_now
from app.repositories.token_repository import RefreshTokenRepository
from app.services.refresh_session_service import RefreshSessionService
from scripts.personalization_http_checks import database_fingerprint
from tests.integration.test_phase_5e_integrated_auth_security import (
    cleanup_user, create_committed_security_fixture, phase_settings,
)


@pytest.mark.parametrize("operation", ["refresh", "logout", "logout-all"])
def test_blocked_account_writer_does_not_hold_refresh_lock(operation):
    baseline = database_fingerprint()
    user_id = None
    try:
        user_id, _, raw, csrf = create_committed_security_fixture("lock-order")
        attempted = Event()
        def run():
            with Session(engine) as db:
                def capture(conn, cursor, statement, parameters, context, executemany):
                    sql = statement.upper()
                    if "FROM USERS" in sql and "FOR UPDATE" in sql:
                        attempted.set()
                event.listen(db.connection(), "before_cursor_execute", capture)
                service = RefreshSessionService(phase_settings())
                if operation == "refresh":
                    service.rotate_session(db, raw_refresh_token=raw, csrf_cookie=csrf, csrf_header=csrf)
                elif operation == "logout":
                    service.logout_current(db, raw_refresh_token=raw, csrf_cookie=csrf, csrf_header=csrf)
                else:
                    service.logout_all(db, user_id=user_id)
        with ThreadPoolExecutor(max_workers=1) as pool:
            with Session(engine) as blocker, blocker.begin():
                blocker.scalar(select(User).where(User.id == user_id).with_for_update())
                future = pool.submit(run)
                assert attempted.wait(10), "Session writer never attempted the account lock."
                with Session(engine) as probe, probe.begin():
                    # NOWAIT would fail if the blocked writer held a refresh row.
                    assert probe.scalar(select(RefreshToken.id).where(
                        RefreshToken.token_hash == hash_refresh_token(raw)
                    ).with_for_update(nowait=True))
            future.result(timeout=20)
    finally:
        cleanup_user(user_id)
    assert database_fingerprint() == baseline


def test_active_family_count_uses_current_state_after_old_snapshot():
    baseline = database_fingerprint()
    user_id = None
    try:
        user_id, _, _, _ = create_committed_security_fixture("family-snapshot")
        with Session(engine) as reader:
            assert len(list(reader.scalars(select(RefreshToken.id).where(
                RefreshToken.user_id == user_id)))) == 1
            with Session(engine) as writer, writer.begin():
                RefreshSessionService(phase_settings()).create_login_session(writer, user_id=user_id)
            reader.scalar(select(User.id).where(User.id == user_id).with_for_update())
            assert RefreshTokenRepository().count_active_families(reader, user_id=user_id, now=utc_now()) == 2
    finally:
        cleanup_user(user_id)
    assert database_fingerprint() == baseline
